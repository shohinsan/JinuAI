import asyncio
import base64
import logging
import mimetypes
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlmodel import Session

from app.utils.agent_helpers import (
    SYSTEM_AGENT_AUTHOR,
    append_session_event,
    ensure_session_exists,
    fetch_refined_prompt,
    finish_session_turn,
    generate_image_bytes,
    prepare_upload_payloads,
    resolve_prompt_and_category,
    run_root_agent,
    start_session_turn,
)
from app.utils.config import get_banana_session_service, settings
from app.utils.delegate import CurrentUser
from app.utils.minio_storage import (
    fetch_object_by_path,
    fetch_user_media_object,
    list_model_assets,
    list_style_assets,
    list_user_media_objects,
    upload_model_asset,
    upload_style_asset,
    upload_user_media,
)
from app.utils.models import (
    Asset,
    AssetType,
    ImageCategory,
    ImageMimeType,
    ImageRequest,
    ImageResponse,
    ImageSize,
    ImageStatus,
    PromptSearchResult,
    UserMediaItem,
)
from app.utils.sqldb import engine

router = APIRouter()
logger = logging.getLogger(__name__)

LOCAL_MEDIA_ROOT = os.path.join(os.getcwd(), "generated-img")
LOCAL_MEDIA_ROOT_ABS = os.path.abspath(LOCAL_MEDIA_ROOT)


async def _persist_local_media(
    filename: str,
    data: bytes,
    *,
    subdir: str | None = None,
) -> str:
    """Write bytes to the local generated-img folder and return the relative path."""

    def _write() -> str:
        base_dir = LOCAL_MEDIA_ROOT if subdir is None else os.path.join(LOCAL_MEDIA_ROOT, subdir)
        os.makedirs(base_dir, exist_ok=True)
        path = os.path.join(base_dir, filename)
        with open(path, "wb") as file_obj:
            file_obj.write(data)
        return path

    path = await asyncio.to_thread(_write)
    return os.path.relpath(path, LOCAL_MEDIA_ROOT)


async def _read_local_media(relative_path: str) -> bytes | None:
    """Read bytes from local storage, returning None when not found."""

    def _read() -> bytes | None:
        normalized = os.path.normpath(relative_path).lstrip(os.sep)
        candidate = os.path.abspath(os.path.join(LOCAL_MEDIA_ROOT, normalized))
        if not candidate.startswith(LOCAL_MEDIA_ROOT_ABS):
            return None
        try:
            with open(candidate, "rb") as file_obj:
                return file_obj.read()
        except FileNotFoundError:
            return None

    return await asyncio.to_thread(_read)


ALLOWED_UPLOAD_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}
_STYLE_SUBDIR_PREFIX = "styles"
_MODEL_SUBDIR = "models"
_UPLOAD_COLLECTIONS = {"media", "models", "styles"}


def _generate_media_filename(upload: UploadFile) -> str:
    """Generate a unique filename preserving image extension when possible."""
    original_ext = os.path.splitext(upload.filename or "")[1].lower()
    content_type = (upload.content_type or "").lower()

    if original_ext not in {".png", ".jpg", ".jpeg"}:
        if content_type in {"image/jpeg", "image/jpg"}:
            original_ext = ".jpg"
        elif content_type == "image/png":
            original_ext = ".png"
        else:
            original_ext = ".png"

    if original_ext == ".jpeg":
        original_ext = ".jpg"

    return f"{uuid.uuid4().hex}{original_ext}"


def _validate_upload_type(upload: UploadFile) -> None:
    """Ensure uploaded images use supported content types."""
    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Only PNG and JPEG images are accepted.",
        )


def _create_asset_record(
    session: Session,
    *,
    object_path: str,
    filename: str,
    asset_type: AssetType,
    mime_type: str,
    file_size: int,
    user_id: uuid.UUID,
    session_id: str | None = None,
    style_subcategory: str | None = None,
    source_model_ids: list[uuid.UUID] | None = None,
    source_style_id: uuid.UUID | None = None,
    refined_prompt: str | None = None,
) -> Asset:
    """Create and persist an Asset record to the database."""
    asset = Asset(
        object_path=object_path,
        bucket_name=settings.MINIO_BUCKET_NAME,
        asset_type=asset_type,
        style_subcategory=style_subcategory,
        filename=filename,
        mime_type=mime_type,
        file_size=file_size,
        user_id=user_id,
        session_id=session_id,
        source_model_ids=source_model_ids,
        source_style_id=source_style_id,
        refined_prompt=refined_prompt,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


@router.get(
    "/prompt/search",
    response_model=list[PromptSearchResult],
)
async def search_prompts(
    q: str | None = Query(
        default=None,
        description="Substring to match against refined prompts or session titles.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of prompt results to return.",
    ),
    *,
    current_user: CurrentUser,
):
    session_service = get_banana_session_service()

    sessions_response = await session_service.list_sessions(
        app_name=settings.GOOGLE_AGENT_NAME,
        user_id=str(current_user.id),
    )

    normalized_query = q.lower().strip() if q else None
    results: list[PromptSearchResult] = []

    for session in sorted(
        sessions_response.sessions,
        key=lambda s: s.last_update_time,
        reverse=True,
    ):
        raw_prompt = session.state.get("refined_prompt")
        refined_prompt = raw_prompt.strip() if isinstance(raw_prompt, str) else None

        raw_title = session.state.get("title")
        title = raw_title.strip() if isinstance(raw_title, str) else None

        raw_status = session.state.get("status")
        status: ImageStatus | None = None
        if isinstance(raw_status, ImageStatus):
            status = raw_status
        elif isinstance(raw_status, str):
            try:
                status = ImageStatus(raw_status)
            except ValueError:
                try:
                    status = ImageStatus(raw_status.lower())
                except ValueError:
                    status = None

        if normalized_query:
            haystacks = []
            if refined_prompt:
                haystacks.append(refined_prompt.lower())
            if title:
                haystacks.append(title.lower())
            if not any(normalized_query in hay for hay in haystacks):
                continue

        results.append(
            PromptSearchResult(
                session_id=session.id,
                refined_prompt=refined_prompt,
                title=title,
                status=status,
                last_update_time=session.last_update_time,
            )
        )

        if len(results) >= limit:
            break

    return results


@router.post("/prompt", response_model=ImageResponse)
async def preview_refined_prompt(
    prompt: str | None = Form(None),
    files: list[UploadFile] = File(...),
    size: str | None = Form(None),
    style: str | None = Form(None),
    aspect_ratio: str | None = Form(None),
    output_format: ImageMimeType | None = Form(ImageMimeType.PNG),
    session_id: str | None = Form(None),
    category: ImageCategory | None = Form(None),
    model_filename: str | None = Form(None),
    *,
    current_user: CurrentUser,
    db: Session = Depends(lambda: Session(engine)),
):
    request = ImageRequest(
        prompt=prompt,
        files=list(files),
        size=size,
        style=style,
        aspect_ratio=aspect_ratio,
        output_format=output_format,
        session_id=session_id,
        category=category,
        model_filename=model_filename,
    )

    user_id = str(current_user.id)

    session_id = session_id or str(uuid.uuid4())

    session = await ensure_session_exists(user_id, session_id)
    session_id = session.id

    requires_model_asset = request.category == ImageCategory.FIT
    resolved_model_filename: str | None = None

    if requires_model_asset:
        if not request.model_filename:
            raise HTTPException(
                status_code=400,
                detail="model_filename is required when category is 'fit'.",
            )
        if len(request.files) > 2:
            raise HTTPException(
                status_code=400,
                detail="You may upload at most 2 user images when category is 'fit'.",
            )

    file_payloads = await prepare_upload_payloads(request.files)

    if requires_model_asset:
        lookup_name = (request.model_filename or "").strip()

        def _match_model(objects):
            if not objects:
                return None
            for obj in objects:
                if obj.filename == lookup_name:
                    return obj
            if "." not in lookup_name:
                for obj in objects:
                    if obj.filename.rsplit(".", 1)[0] == lookup_name:
                        return obj
            return None

        model_bytes: bytes | None = None
        if settings.minio_enabled:
            model_objects = await list_model_assets()
            selected_model = _match_model(model_objects)
            if not selected_model:
                raise HTTPException(status_code=404, detail="Selected model asset was not found.")

            resolved_model_filename = selected_model.filename
            model_bytes = await fetch_object_by_path(selected_model.object_path)
            if model_bytes is None:
                raise HTTPException(status_code=500, detail="Unable to load selected model asset.")
        else:
            candidate_name = lookup_name
            candidate_path = os.path.join(_MODEL_SUBDIR, "static", candidate_name) if candidate_name else None
            if candidate_path:
                model_bytes = await _read_local_media(candidate_path)
                if model_bytes is not None:
                    resolved_model_filename = candidate_name

            if model_bytes is None and "." not in lookup_name:
                static_dir = os.path.join(LOCAL_MEDIA_ROOT, _MODEL_SUBDIR, "static")
                if os.path.isdir(static_dir):
                    for candidate in os.listdir(static_dir):
                        if os.path.splitext(candidate)[0] == lookup_name:
                            candidate_path = os.path.join(_MODEL_SUBDIR, "static", candidate)
                            model_bytes = await _read_local_media(candidate_path)
                            if model_bytes is not None:
                                resolved_model_filename = candidate
                                break

            if model_bytes is None:
                raise HTTPException(status_code=404, detail="Selected model asset was not found locally.")

        effective_model_filename = resolved_model_filename or lookup_name
        model_mime = mimetypes.guess_type(effective_model_filename)[0] or ImageMimeType.PNG.value
        file_payloads.append((model_bytes, model_mime))

        if len(file_payloads) > 3:
            raise HTTPException(
                status_code=400,
                detail="A maximum of 3 images (including the selected model) is supported.",
            )

    resolved_prompt, category, normalized_style = resolve_prompt_and_category(request)

    size = request.size or ImageSize.MEDIUM
    output_format = request.output_format or ImageMimeType.PNG

    title_source = request.prompt or resolved_prompt
    session_title = (title_source or "Image request")[:200]

    session = await start_session_turn(session, title=session_title)

    user_event_metadata = {
        "category": category.value if category else None,
        "size": size.value if isinstance(size, ImageSize) else str(size),
        "style": normalized_style,
        "aspect_ratio": request.aspect_ratio.value if request.aspect_ratio else None,
        "model_filename": resolved_model_filename,
    }
    user_event_metadata = {
        key: value
        for key, value in user_event_metadata.items()
        if value is not None
    }

    text_for_agent = "\n\n".join(
        filter(
            None,
            [
                *(
                    f"ImageCategory: {category.value}" if category else [],
                    (
                        f"ImageSize: {size.value}"
                        if isinstance(size, ImageSize)
                        else f"ImageSize: {size}"
                    )
                    if size
                    else [],
                    (
                        f"AspectRatio: {request.aspect_ratio.value}"
                        if request.aspect_ratio
                        else []
                    ),
                    f"Style: {normalized_style}" if normalized_style else [],
                ),
                resolved_prompt.strip() if resolved_prompt else None,
            ],
        )
    )

    session = await append_session_event(
        session,
        author="user",
        text=text_for_agent,
        custom_metadata=user_event_metadata or None,
    )

    try:
        await run_root_agent(user_id, session_id, text_for_agent)

        refined_prompt = (
            await fetch_refined_prompt(user_id, session_id, resolved_prompt)
        ).strip()

        final_bytes = await generate_image_bytes(
            file_payloads=file_payloads,
            refined_prompt=refined_prompt,
            aspect_ratio=request.aspect_ratio,
            output_format=output_format,
        )
    except asyncio.CancelledError:
        session = await finish_session_turn(
            session,
            status=ImageStatus.FAILED,
            title=session_title,
            interrupted=True,
        )
        await append_session_event(
            session,
            author=SYSTEM_AGENT_AUTHOR,
            text="Image generation cancelled by user",
            custom_metadata={
                "status": ImageStatus.FAILED.value,
                "reason": "cancelled_by_user",
            },
            turn_complete=True,
            interrupted=True,
        )
        raise
    except Exception as exc:
        session = await finish_session_turn(
            session,
            status=ImageStatus.FAILED,
            title=session_title,
        )
        await append_session_event(
            session,
            author=SYSTEM_AGENT_AUTHOR,
            text=f"Image generation failed: {exc}",
            custom_metadata={"status": ImageStatus.FAILED.value},
            turn_complete=True,
        )
        raise
    else:
        session = await finish_session_turn(
            session,
            status=ImageStatus.COMPLETED,
            title=session_title,
        )

    # Persist generated image locally when MinIO is unavailable
    filename = f"{uuid.uuid4().hex}.{output_format.name.lower()}"
    if not settings.minio_enabled:
        await _persist_local_media(filename, final_bytes)

    minio_object_path = await upload_user_media(
        user_id=user_id,
        filename=filename,
        data=final_bytes,
        content_type=output_format.value,
    )
    if not minio_object_path:
        if settings.minio_enabled:
            logger.error("MinIO upload failed for %s", filename)
            raise HTTPException(status_code=500, detail="Failed to persist generated media")
        logger.debug("MinIO upload skipped or failed for %s", filename)

    # Create Asset record for the generated image
    resolved_object_path = minio_object_path or filename
    _create_asset_record(
        db,
        object_path=resolved_object_path,
        filename=filename,
        asset_type=AssetType.MEDIA,
        mime_type=output_format.value,
        file_size=len(final_bytes),
        user_id=current_user.id,
        session_id=session_id,
        refined_prompt=refined_prompt,
    )

    session = await append_session_event(
        session,
        author=SYSTEM_AGENT_AUTHOR,
        text="Image generation completed",
        custom_metadata={
            "status": ImageStatus.COMPLETED.value,
            "output_path": filename,
            "media_object": minio_object_path,
        },
        turn_complete=True,
    )

    encoded_image = f"data:{output_format.value};base64,{base64.b64encode(final_bytes).decode()}"

    return ImageResponse(
        status=ImageStatus.COMPLETED if refined_prompt else ImageStatus.PENDING,
        refined_prompt=refined_prompt,
        size=size.value if isinstance(size, ImageSize) else str(size),
        style=request.style,
        aspect_ratio=request.aspect_ratio.value if request.aspect_ratio else None,
        session_id=session.id,
        category=category.value if category else None,
        user_id=user_id,
        output_file=encoded_image,
        media_object_path=minio_object_path,
    )


@router.post("/media", response_model=list[UserMediaItem])
async def upload_media_items(
    files: list[UploadFile] = File(...),
    collection: str | None = Form("media"),
    style_name: str | None = Form(None),
    *,
    current_user: CurrentUser,
    db: Session = Depends(lambda: Session(engine)),
) -> list[UserMediaItem]:
    """Persist uploaded images to user media, shared styles, or model catalogs."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one image file is required.")

    normalized_collection = (
        collection.strip().lower() if collection and collection.strip() else "media"
    )
    if normalized_collection not in _UPLOAD_COLLECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported collection '{collection}'. Expected one of {_UPLOAD_COLLECTIONS}.",
        )

    normalized_style = (
        style_name.strip().lower() if style_name and style_name.strip() else None
    )
    if normalized_collection == "styles" and not normalized_style:
        raise HTTPException(
            status_code=400,
            detail="'style_name' is required when uploading to the styles collection.",
        )

    user_id = str(current_user.id)
    uploaded_items: list[UserMediaItem] = []

    for upload in files:
        _validate_upload_type(upload)
        payload = await upload.read()
        if not payload:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename or 'Uploaded file'} is empty.",
            )

        filename = _generate_media_filename(upload)
        content_type = upload.content_type or "image/png"
        now = datetime.now(UTC)

        if normalized_collection == "styles":
            try:
                object_path = await upload_style_asset(
                    style=normalized_style,
                    filename=filename,
                    data=payload,
                    content_type=content_type,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            if settings.minio_enabled and not object_path:
                raise HTTPException(status_code=500, detail="Failed to persist style asset")

            local_path = None
            if not settings.minio_enabled:
                local_path = await _persist_local_media(
                    filename,
                    payload,
                    subdir=f"{_STYLE_SUBDIR_PREFIX}/{normalized_style}",
                )

            resolved_path = object_path or local_path or filename
            
            # Create Asset record
            _create_asset_record(
                db,
                object_path=resolved_path,
                filename=filename,
                asset_type=AssetType.STYLE,
                mime_type=content_type,
                file_size=len(payload),
                user_id=current_user.id,
                style_subcategory=normalized_style,
            )
            
            uploaded_items.append(
                UserMediaItem(
                    filename=filename,
                    object_path=resolved_path,
                    local_path=local_path,
                    collection="styles",
                    style=normalized_style,
                    size=len(payload),
                    last_modified=now,
                )
            )
            continue

        if normalized_collection == "models":
            object_path = await upload_model_asset(
                filename=filename,
                data=payload,
                content_type=content_type,
            )
            if settings.minio_enabled and not object_path:
                raise HTTPException(status_code=500, detail="Failed to persist model asset")

            local_path = None
            if not settings.minio_enabled:
                local_path = await _persist_local_media(
                    filename,
                    payload,
                    subdir=os.path.join(_MODEL_SUBDIR, "static"),
                )

            resolved_path = object_path or local_path or filename
            
            # Create Asset record
            _create_asset_record(
                db,
                object_path=resolved_path,
                filename=filename,
                asset_type=AssetType.MODEL,
                mime_type=content_type,
                file_size=len(payload),
                user_id=current_user.id,
            )
            
            uploaded_items.append(
                UserMediaItem(
                    filename=filename,
                    object_path=resolved_path,
                    local_path=local_path,
                    collection="models",
                    size=len(payload),
                    last_modified=now,
                )
            )
            continue

        object_path = await upload_user_media(
            user_id=user_id,
            filename=filename,
            data=payload,
            content_type=content_type,
        )
        if settings.minio_enabled and not object_path:
            raise HTTPException(status_code=500, detail="Failed to persist media asset")

        local_path = None
        if not settings.minio_enabled:
            local_path = await _persist_local_media(filename, payload)

        resolved_path = object_path or local_path or filename
        
        # Create Asset record
        _create_asset_record(
            db,
            object_path=resolved_path,
            filename=filename,
            asset_type=AssetType.MEDIA,
            mime_type=content_type,
            file_size=len(payload),
            user_id=current_user.id,
        )
        
        uploaded_items.append(
            UserMediaItem(
                filename=filename,
                object_path=resolved_path,
                local_path=local_path,
                collection="media",
                size=len(payload),
                last_modified=now,
            )
        )

    return uploaded_items


@router.get("/media", response_model=list[UserMediaItem])
async def list_generated_media(*, current_user: CurrentUser) -> list[UserMediaItem]:
    """Return previously generated media entries for the authenticated user."""
    user_id = str(current_user.id)
    media_objects = await list_user_media_objects(user_id=user_id)

    items = [
        UserMediaItem(
            filename=obj.filename,
            object_path=obj.object_path,
            collection=obj.collection or "media",
            style=obj.style,
            size=obj.size,
            last_modified=obj.last_modified,
        )
        for obj in media_objects
    ]

    if settings.minio_enabled:
        model_objects = await list_model_assets()
        style_objects = await list_style_assets()

        items += [
            UserMediaItem(
                filename=obj.filename,
                object_path=obj.object_path,
                collection=obj.collection or "models",
                style=obj.style,
                size=obj.size,
                last_modified=obj.last_modified,
            )
            for obj in model_objects
        ]

        items += [
            UserMediaItem(
                filename=obj.filename,
                object_path=obj.object_path,
                collection=obj.collection or "styles",
                style=obj.style,
                size=obj.size,
                last_modified=obj.last_modified,
            )
            for obj in style_objects
        ]

        items.sort(
            key=lambda item: item.last_modified or datetime.fromtimestamp(0, tz=UTC),
            reverse=True,
        )

    if not items and not settings.minio_enabled:
        local_dir = LOCAL_MEDIA_ROOT_ABS
        if os.path.isdir(local_dir):
            discovered: list[tuple[str, os.stat_result]] = []
            for root, _, files in os.walk(local_dir):
                for name in files:
                    full_path = os.path.join(root, name)
                    discovered.append((full_path, os.stat(full_path)))

            for path, stat_result in sorted(
                discovered, key=lambda item: item[1].st_mtime, reverse=True
            ):
                rel_path = os.path.relpath(path, LOCAL_MEDIA_ROOT)
                parts = rel_path.split(os.sep)
                inferred_collection = parts[0] if len(parts) > 1 else "media"
                if inferred_collection not in _UPLOAD_COLLECTIONS:
                    inferred_collection = "media"

                inferred_style = None
                if (
                    inferred_collection == "styles"
                    and len(parts) > 2
                ):
                    inferred_style = parts[1]

                last_modified = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)
                items.append(
                    UserMediaItem(
                        filename=os.path.basename(path),
                        object_path=rel_path,
                        local_path=rel_path,
                        collection=inferred_collection,
                        style=inferred_style,
                        size=stat_result.st_size,
                        last_modified=last_modified,
                    )
                )

    return items


@router.get("/media/{filename}")
async def get_generated_media(
    filename: str,
    *,
    current_user: CurrentUser,
) -> Response:
    """Fetch a generated media file for the authenticated user."""
    user_id = str(current_user.id)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    requested_name = filename
    resolved_filename = filename
    media_bytes = await fetch_user_media_object(user_id=user_id, filename=filename)

    def _match_identifier(objects):
        if not objects:
            return None
        for obj in objects:
            if obj.filename == requested_name:
                return obj
        if "." not in requested_name:
            for obj in objects:
                base = obj.filename.rsplit(".", 1)[0]
                if base == requested_name:
                    return obj
        return None

    if (media_bytes is None or "." not in requested_name) and settings.minio_enabled:
        media_objects = await list_user_media_objects(user_id=user_id)
        media_match = _match_identifier(media_objects)
        if media_match:
            candidate_bytes = await fetch_user_media_object(
                user_id=user_id,
                filename=media_match.filename,
            )
            if candidate_bytes is not None:
                media_bytes = candidate_bytes
                resolved_filename = media_match.filename

    if media_bytes is None and settings.minio_enabled:
        model_objects = await list_model_assets()
        model_match = _match_identifier(model_objects)
        if model_match:
            candidate_bytes = await fetch_object_by_path(model_match.object_path)
            if candidate_bytes is not None:
                media_bytes = candidate_bytes
                resolved_filename = model_match.filename

    if media_bytes is None and settings.minio_enabled:
        style_objects = await list_style_assets()
        style_match = _match_identifier(style_objects)
        if style_match:
            candidate_bytes = await fetch_object_by_path(style_match.object_path)
            if candidate_bytes is not None:
                media_bytes = candidate_bytes
                resolved_filename = style_match.filename

    if media_bytes is None:
        if not settings.minio_enabled:
            media_bytes = await _read_local_media(resolved_filename)
            if media_bytes is None and "." not in requested_name:
                base_name = requested_name
                found = False
                for root, _, files in os.walk(LOCAL_MEDIA_ROOT):
                    if found:
                        break
                    for candidate_name in files:
                        if os.path.splitext(candidate_name)[0] != base_name:
                            continue
                        rel_path = os.path.relpath(os.path.join(root, candidate_name), LOCAL_MEDIA_ROOT)
                        candidate_bytes = await _read_local_media(rel_path)
                        if candidate_bytes is not None:
                            media_bytes = candidate_bytes
                            resolved_filename = candidate_name
                            found = True
                            break
        if media_bytes is None:
            raise HTTPException(status_code=404, detail="Media not found")

    final_filename = resolved_filename or requested_name
    content_type = mimetypes.guess_type(final_filename)[0] or "application/octet-stream"
    headers = {"Content-Disposition": f"inline; filename={final_filename}"}
    return Response(content=media_bytes, media_type=content_type, headers=headers)
