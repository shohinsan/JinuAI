
import base64
from io import BytesIO
from mimetypes import guess_type
from pathlib import PurePosixPath
from typing import Any, List, Optional
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, Request
from fastapi.responses import StreamingResponse
from starlette.datastructures import Headers

from app.services.agent.agent_service import AgentService
from app.utils.delegate import (
    AgentRepositoryDep,
    AgentServiceDep,
    CurrentUser,
)
from app.utils.models import Asset, AssetType, ImageCategory, ImageRequest, ImageResponse
router = APIRouter()


def serialize_asset(
    asset: Asset,
    request: Request | None = None,
    *,
    data_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Serialize an Asset record for API responses."""
    asset_type = (
        asset.asset_type.value
        if isinstance(asset.asset_type, AssetType)
        else asset.asset_type
    )
    object_path = asset.object_path or ""
    filename = getattr(asset, "filename", "") or PurePosixPath(object_path).name
    content_type, _ = guess_type(filename or object_path)
    download_path = router.url_path_for(
        "download_media_asset", asset_id=str(asset.id)
    )
    download_url = (
        str(request.url_for("download_media_asset", asset_id=str(asset.id)))
        if request
        else download_path
    )

    payload = {
        "id": str(asset.id),
        "asset_type": asset_type,
        "session_id": asset.session_id,
        "object_path": asset.object_path,
        "bucket_name": asset.bucket_name,
        "prompt": asset.prompt,
        "created_at": asset.created_at.isoformat(),
        "filename": filename or None,
        "content_type": content_type,
        "download_url": download_url,
    }
    if data_bytes is not None:
        data_mime = content_type or "application/octet-stream"
        payload["data_url"] = (
            f"data:{data_mime};base64,{base64.b64encode(data_bytes).decode()}"
        )

    return payload


@router.post("/prompt", response_model=ImageResponse)
async def generate_image(
    prompt: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    style: Optional[str] = Form(None),
    aspect_ratio: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    category: Optional[ImageCategory] = Form(None),
    *,
    current_user: CurrentUser,
    agent_service: AgentServiceDep,
):
    """Generate an image using AI agents based on user prompt and uploaded files."""
    asset_ids = [
        (await f.read()).decode().strip()
        for f in files or []
        if f.content_type and f.content_type.startswith("text/")
    ]
    
    image_files = [
        f for f in files or []
        if not (f.content_type and f.content_type.startswith("text/"))
    ]

    if asset_ids:
        blobs = await agent_service.load_model_assets(
            model_asset_ids=",".join(asset_ids), user_id=current_user.id
        )
        image_files.extend(
            UploadFile(
                filename=f"model_{i}.bin",
                file=BytesIO(blob),
                headers=Headers({"content-type": mime}),
            )
            for i, (blob, mime) in enumerate(blobs)
        )

    if not image_files:
        raise HTTPException(status_code=400, detail="At least one image file is required")
    if len(image_files) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 images allowed")

    request = ImageRequest(
        prompt=prompt,
        files=image_files,
        style=style,
        aspect_ratio=aspect_ratio,
        session_id=session_id,
        category=category,
    )

    return await agent_service.generate_image(
        request=request,
        user_id=current_user.id,
    )


@router.post("/media")
async def upload_media(
    files: List[UploadFile] = File(...),
    collection: Optional[str] = Form("media"),
    style_subcategory: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    *,
    current_user: CurrentUser,
    agent_service: AgentServiceDep,
):
    """Upload media files to MinIO and track in database."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    collection = (collection or "media").strip().lower()
    if collection not in {"media", "models", "style"}:
        raise HTTPException(status_code=400, detail="Invalid collection")

    upload_handlers = {
        "media": agent_service.upload_and_track_media,
        "models": agent_service.upload_and_track_model,
        "style": agent_service.upload_and_track_style,
    }

    uploaded_assets = []
    for file in files:
        content = await file.read()
        filename = AgentService.generate_storage_filename(
            file.filename or "unknown",
            file.content_type or "application/octet-stream"
        )

        asset = await upload_handlers[collection](
            user_id=current_user.id,
            filename=filename,
            data=content,
            content_type=file.content_type or "application/octet-stream",
        )
        
        uploaded_assets.append({
            "id": str(asset.id),
            "created_at": asset.created_at.isoformat(),
        })

    return {
        "success": True,
        "uploaded": len(uploaded_assets),
        "assets": uploaded_assets,
    }


@router.get("/media")
async def list_user_media(
    request: Request,
    *,
    current_user: CurrentUser,
    agent_service: AgentServiceDep,
    collection: str = Query("all"),
    style_subcategory: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    include_data: bool = Query(False, description="Embed base64 previews when true"),
):
    """List uploaded assets for the current user by collection."""
    collection = (collection or "all").strip().lower()
    
    list_handlers = {
        "all": lambda: agent_service.get_user_assets(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
        ),
        "media": lambda: agent_service.get_user_media(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
        ),
        "models": lambda: agent_service.get_model_assets(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
        ),
        "style": lambda: agent_service.get_style_assets(
            style_subcategory=style_subcategory,
            skip=skip,
            limit=limit,
        ),
    }

    if collection not in list_handlers:
        raise HTTPException(status_code=400, detail="Invalid collection")

    assets = list_handlers[collection]()
    asset_data: dict[str, bytes | None] = {}

    if include_data:
        for asset in assets:
            try:
                data = await agent_service.fetch_asset_bytes(asset)
            except FileNotFoundError:
                data = None
            asset_data[str(asset.id)] = data

    serialized_assets = [
        serialize_asset(
            asset,
            request,
            data_bytes=asset_data.get(str(asset.id)),
        )
        for asset in assets
    ]

    return {
        "total": len(assets),
        "assets": serialized_assets,
    }


@router.get("/media/{asset_id}")
async def get_media_asset(
    asset_id: str,
    request: Request,
    *,
    current_user: CurrentUser,
    agent_service: AgentServiceDep,
    include_data: bool = Query(False, description="Embed a base64 preview when true"),
):
    """Get a specific media asset by ID."""
    asset = agent_service.resolve_asset_by_identifier(asset_id, current_user.id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    data_bytes = None
    if include_data:
        try:
            data_bytes = await agent_service.fetch_asset_bytes(asset)
        except FileNotFoundError:
            data_bytes = None

    return serialize_asset(asset, request, data_bytes=data_bytes)


@router.get("/media/{asset_id}/download", name="download_media_asset")
async def download_media_asset(
    asset_id: str,
    *,
    current_user: CurrentUser,
    agent_service: AgentServiceDep,
):
    """Stream the binary contents of a stored asset by its identifier."""
    asset = agent_service.resolve_asset_by_identifier(asset_id, current_user.id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    data = await agent_service.fetch_asset_bytes(asset)
    filename = getattr(asset, "filename", "") or PurePosixPath(
        asset.object_path or ""
    ).name or f"{asset.id}"
    media_type = guess_type(filename)[0] or "application/octet-stream"
    headers = {}
    if filename:
        headers["Content-Disposition"] = f'inline; filename="{filename}"'

    return StreamingResponse(
        BytesIO(data),
        media_type=media_type,
        headers=headers,
    )


@router.get("/prompt/search")
async def search_prompts(
    q: str,
    *,
    current_user: CurrentUser,
    agent_repository: AgentRepositoryDep,
    limit: int = 20,
):
    """Search through user's prompts and generated images."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    assets = agent_repository.search_assets_by_prompt(current_user.id, q, limit)
    return {
        "query": q,
        "total": len(assets),
        "results": [
            {
                "id": str(asset.id),
                "prompt": asset.prompt,
                "created_at": asset.created_at.isoformat(),
            }
            for asset in assets
        ],
    }
