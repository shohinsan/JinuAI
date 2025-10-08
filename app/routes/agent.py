
from io import BytesIO
from typing import List, Optional
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from starlette.datastructures import Headers

from app.services.agent.agent_service import AgentService
from app.utils.delegate import (
    AgentRepositoryDep,
    AgentServiceDep,
    CurrentUser,
)
from app.utils.models import (
    ImageCategory,
    ImageRequest,
    ImageResponse,
)
router = APIRouter()


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
    *,
    current_user: CurrentUser,
    agent_service: AgentServiceDep,
    collection: str = Query("all"),
    style_subcategory: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
):
    """List uploaded assets for the current user by collection."""
    collection = (collection or "all").strip().lower()
    
    list_handlers = {
        "all": lambda: agent_service.get_user_assets(current_user.id, skip, limit),
        "media": lambda: agent_service.get_user_media(current_user.id, skip, limit),
        "models": lambda: agent_service.get_model_assets(current_user.id, skip, limit),
        "style": lambda: agent_service.get_style_assets(style_subcategory, skip, limit),
    }

    if collection not in list_handlers:
        raise HTTPException(status_code=400, detail="Invalid collection")

    assets = list_handlers[collection]()
    return {
        "total": len(assets),
        "assets": [
            {
                "id": str(asset.id),
                "created_at": asset.created_at.isoformat(),
            }
            for asset in assets
        ],
    }


@router.get("/media/{asset_id}")
async def get_media_asset(
    asset_id: str,
    *,
    current_user: CurrentUser,
    agent_service: AgentServiceDep,
):
    """Get a specific media asset by ID."""
    asset = agent_service.resolve_asset_by_identifier(asset_id, current_user.id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    return {
        "id": str(asset.id),
        "asset_type": asset.asset_type,
        "session_id": asset.session_id,
        "prompt": asset.prompt,
        "created_at": asset.created_at.isoformat(),
    }


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
    return StreamingResponse(
        BytesIO(data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={asset.id}.bin"},
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

