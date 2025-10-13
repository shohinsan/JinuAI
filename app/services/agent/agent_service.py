import base64
import os
import re
import uuid
from mimetypes import guess_extension
from fastapi import HTTPException
from pathlib import Path
import asyncio
from app.services.agent.agent_repository import AgentRepository
from app.utils.agent_helpers import (
    SYSTEM_AGENT_AUTHOR,
    append_session_event,
    ensure_session_exists,
    fetch_prompt,
    finish_session_turn,
    generate_image_bytes,
    get_input_prompt_and_category,
    prepare_upload_payloads,
    run_root_agent,
    start_session_turn,
)
from app.utils.config import settings
from app.utils.storage import (
    fetch_object_by_path,
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
    ImageStatus,
)


class AgentService:
    """Service for AI agent-based image generation workflows and asset management."""

    def __init__(self, repository: AgentRepository):
        self.repository = repository

    # ===== Utility Methods =====

    @staticmethod
    def generate_storage_filename(
        original_filename: str | None,
        content_type: str | None,
    ) -> str:
        """Create a unique filename preserving a sensible extension."""
        from app.utils.models import ImageMimeType

        suffix = ""
        if original_filename:
            suffix = Path(original_filename).suffix.lower()

        if not suffix and content_type:
            # Map MIME types to extensions
            if content_type in (ImageMimeType.JPEG.value, "image/jpg"):
                suffix = ".jpg"
            elif content_type == ImageMimeType.PNG.value:
                suffix = ".png"
            elif content_type == "image/webp":
                suffix = ".webp"
            else:
                guessed = guess_extension(content_type)
                if guessed:
                    suffix = guessed.lower()

        if suffix and not suffix.startswith("."):
            suffix = f".{suffix.lstrip('.')}"

        if not suffix:
            suffix = ".bin"

        return f"{uuid.uuid4().hex}{suffix}"

    # ===== Asset Management Methods =====

    async def upload_and_track_media(
        self,
        *,
        asset_id: uuid.UUID | None = None,
        user_id: uuid.UUID,
        filename: str,
        data: bytes,
        content_type: str | None = None,
        mime_type: str | None = None,
        session_id: str | None = None,
        prompt: str | None = None,
        source_model_ids: list[uuid.UUID] | None = None,
        source_style_id: uuid.UUID | None = None,
    ) -> Asset:
        """Upload media to MinIO and create database record."""
        resolved_content_type = content_type or mime_type or "application/octet-stream"

        # Upload to MinIO
        object_path = await upload_user_media(
            user_id=str(user_id),
            filename=filename,
            data=data,
            content_type=resolved_content_type,
        )

        if not object_path and settings.minio_enabled:
            raise RuntimeError("Failed to upload media to MinIO")

        # Fallback to filename if MinIO is disabled
        resolved_path = object_path or filename

        # Create database record
        asset = self.repository.create_asset(
            asset_id=asset_id,
            object_path=resolved_path,
            bucket_name=settings.MINIO_BUCKET_NAME,
            filename=filename,
            asset_type=AssetType.MEDIA,
            user_id=user_id,
            session_id=session_id,
            prompt=prompt,
            source_model_ids=source_model_ids,
            source_style_id=source_style_id,
        )

        return asset

    async def upload_and_track_model(
        self,
        *,
        asset_id: uuid.UUID | None = None,
        user_id: uuid.UUID,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> Asset:
        """Upload model reference asset to MinIO and create database record."""
        # Upload to MinIO
        object_path = await upload_model_asset(
            filename=filename,
            data=data,
            content_type=content_type,
        )

        if not object_path and settings.minio_enabled:
            raise RuntimeError("Failed to upload model to MinIO")

        resolved_path = object_path or filename

        # Create database record
        asset = self.repository.create_asset(
            asset_id=asset_id,
            object_path=resolved_path,
            bucket_name=settings.MINIO_BUCKET_NAME,
            filename=filename,
            asset_type=AssetType.MODEL,
            user_id=user_id,
        )

        return asset

    async def upload_and_track_style(
        self,
        *,
        asset_id: uuid.UUID | None = None,
        user_id: uuid.UUID,
        filename: str,
        data: bytes,
        content_type: str,
        style_subcategory: str,
    ) -> Asset:
        """Upload style asset to MinIO and create database record."""
        # Upload to MinIO
        object_path = await upload_style_asset(
            style=style_subcategory,
            filename=filename,
            data=data,
            content_type=content_type,
        )

        if not object_path and settings.minio_enabled:
            raise RuntimeError("Failed to upload style to MinIO")

        resolved_path = object_path or filename

        # Create database record
        asset = self.repository.create_asset(
            asset_id=asset_id,
            object_path=resolved_path,
            bucket_name=settings.MINIO_BUCKET_NAME,
            filename=filename,
            asset_type=AssetType.STYLE,
            user_id=user_id,
        )

        return asset

    async def fetch_asset_bytes(self, asset: Asset) -> bytes:
        """Retrieve raw bytes for an asset, preferring MinIO storage."""

        if asset.object_path and settings.minio_enabled:
            data = await fetch_object_by_path(asset.object_path)
            if data is not None:
                return data

        if asset.asset_type == AssetType.MEDIA:
            local_path = Path.cwd() / "generated-img" / asset.filename
            if local_path.exists():
                return local_path.read_bytes()

        raise FileNotFoundError(
            f"Unable to locate stored bytes for asset {asset.id}"
        )

    def get_user_assets(
        self,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        asset_type: AssetType | None = None,
    ) -> list[Asset]:
        """Retrieve user assets optionally filtered by type."""
        return self.repository.list_user_assets(
            user_id=user_id,
            asset_type=asset_type,
            limit=limit,
            offset=skip,
        )

    def get_user_media(
        self,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Asset]:
        """Retrieve media assets for a user."""
        return self.get_user_assets(
            user_id=user_id,
            skip=skip,
            limit=limit,
            asset_type=AssetType.MEDIA,
        )

    def get_session_assets(
        self, session_id: str, user_id: uuid.UUID | None = None
    ) -> list[Asset]:
        """Retrieve all assets associated with a session."""
        return self.repository.list_assets_by_session(
            session_id=session_id, user_id=user_id
        )

    def get_style_assets(
        self,
        *,
        style_subcategory: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Asset]:
        """Retrieve style assets, optionally filtered by subcategory."""
        return self.repository.list_style_assets(
            style_subcategory=style_subcategory,
            limit=limit,
            offset=skip,
        )

    def get_model_assets(
        self,
        *,
        user_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Asset]:
        """Retrieve model reference assets."""
        if user_id is not None:
            return self.get_user_assets(
                user_id=user_id,
                skip=skip,
                limit=limit,
                asset_type=AssetType.MODEL,
            )
        return self.repository.list_model_assets(
            limit=limit,
            offset=skip,
            user_id=None,
        )

    def get_asset_for_user(self, asset_id: uuid.UUID, user_id: uuid.UUID) -> Asset | None:
        """Retrieve an asset if it belongs to the user and is active."""
        asset = self.repository.get_asset_by_id(asset_id)
        if not asset:
            return None

        if asset.user_id != user_id or not asset.is_active:
            return None

        return asset

    async def load_model_assets(
        self,
        *,
        model_asset_ids: str,
        user_id: uuid.UUID,
    ) -> list[tuple[bytes, str]]:
        """
        Load multiple model assets by comma/space-separated IDs.
        
        Returns list of (data, content_type) tuples ready for upload.
        Raises HTTPException if any asset is not found or inaccessible.
        """
        
        asset_ids = [token for token in re.split(r"[\s,]+", model_asset_ids) if token]
        loaded_assets = []
        
        for asset_id in asset_ids:
            asset_uuid = uuid.UUID(asset_id)  # Let ValueError propagate
            asset = self.get_asset_for_user(asset_uuid, user_id)
            
            if not asset:
                raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
            
            blob = await self.fetch_asset_bytes(asset)
            loaded_assets.append((blob, "application/octet-stream"))
        
        return loaded_assets

    def resolve_asset_by_identifier(
        self,
        identifier: str,
        user_id: uuid.UUID,
    ) -> Asset | None:
        """Resolve an asset for a user by UUID, filename, or object path.

        Supports flexible matching:
        - Direct UUID match
        - Exact filename or object_path match
        - Partial filename match (with extension guessing)
        - Partial path match
        """
        return self.repository.resolve_asset_by_identifier(identifier, user_id)

    def delete_asset(self, asset_id: uuid.UUID) -> Asset | None:
        """Soft delete an asset."""
        return self.repository.soft_delete_asset(asset_id)

    def toggle_asset_visibility(
        self, asset_id: uuid.UUID, is_public: bool
    ) -> Asset | None:
        """Update asset public visibility."""
        return self.repository.update_asset_visibility(asset_id, is_public)

    # ===== Image Generation Methods =====

    async def generate_image(
        self,
        *,
        request: ImageRequest,
        user_id: uuid.UUID,
    ) -> ImageResponse:
        """
        Generate an image using AI agents and store the result.

        This method orchestrates the complete workflow:
        1. Session initialization
        2. File payload preparation
        3. Prompt refinement via agent
        4. Image generation
        5. Asset storage and tracking
        """
        session_id = request.session_id or str(uuid.uuid4())

        # Initialize or retrieve session
        session = await ensure_session_exists(str(user_id), session_id)
        session_id = session.id

        # Prepare uploaded files
        file_payloads = await prepare_upload_payloads(request.files)

        # Get input prompt and category
        input_prompt, category, normalized_style = get_input_prompt_and_category(
            request
        )

        output_format = ImageMimeType.PNG
        aspect_ratio = request.aspect_ratio

        # Create session title
        session_title = (input_prompt or "Image request")[:200]

        # Start session turn
        session = await start_session_turn(session, title=session_title)

        # Build metadata
        user_event_metadata = {
            "category": category.value if category else None,
            "style": normalized_style,
            "aspect_ratio": request.aspect_ratio.value if request.aspect_ratio else None,
        }
        user_event_metadata = {
            key: value for key, value in user_event_metadata.items() if value is not None
        }

        # Build agent input text
        text_for_agent = "\n\n".join(
            filter(
                None,
                [
                    *(
                        f"ImageCategory: {category.value}" if category else [],
                        f"Style: {normalized_style}" if normalized_style else [],
                    ),
                    input_prompt.strip() if input_prompt else None,
                ],
            )
        )

        # Log user event
        session = await append_session_event(
            session,
            author="user",
            text=text_for_agent,
            custom_metadata=user_event_metadata or None,
        )

        try:
            # Templates use the prompt as-is; other categories go through agent refinement
            prompt = input_prompt.strip()
            
            if category != ImageCategory.TEMPLATE:
                await run_root_agent(str(user_id), session_id, text_for_agent)
                prompt = (
                    await fetch_prompt(str(user_id), session_id, input_prompt)
                ).strip()

            # Generate image
            final_bytes = await generate_image_bytes(
                file_payloads=file_payloads,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
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

        # Save locally (for development/debugging)
        asset_id = uuid.uuid4()
        filename = f"{asset_id}.{output_format.name.lower()}"
        out_dir = os.path.join(os.getcwd(), "generated-img")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, filename)
        with open(out_path, "wb") as f:
            f.write(final_bytes)

        # Upload and track asset using merged methods
        asset = await self.upload_and_track_media(
            asset_id=asset_id,
            user_id=user_id,
            filename=filename,
            data=final_bytes,
            content_type=output_format.value,
            session_id=session_id,
            prompt=prompt,
        )

        # Log completion event
        session = await append_session_event(
            session,
            author=SYSTEM_AGENT_AUTHOR,
            text="Image generation completed",
            custom_metadata={
                "status": ImageStatus.COMPLETED.value,
                "output_path": filename,
                "asset_id": str(asset.id),
                "media_object": asset.object_path,
            },
            turn_complete=True,
        )

        # Encode image for response
        encoded_image = f"data:{output_format.value};base64,{base64.b64encode(final_bytes).decode()}"

        return ImageResponse(
            status=ImageStatus.COMPLETED if prompt else ImageStatus.PENDING,
            prompt=prompt,
            style=request.style,
            aspect_ratio=request.aspect_ratio.value if request.aspect_ratio else None,
            session_id=session.id,
            category=category.value if category else None,
            user_id=str(user_id),
            output_file=encoded_image,
            media_object_path=asset.object_path,
        )
