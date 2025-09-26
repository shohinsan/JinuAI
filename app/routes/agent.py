import base64
import os
from typing import List, Optional
import uuid
from fastapi import APIRouter, File, Form, UploadFile
from app.utils.agent_helpers import (
    ensure_session_exists,
    fetch_refined_prompt,
    generate_image_bytes,
    prepare_upload_payloads,
    resolve_prompt_and_category,
    run_root_agent,
)
from app.utils.config import settings
from app.utils.delegate import AgentServiceDep, CurrentUser
from app.utils.models import (
    ImageCategory,
    ImageMimeType,
    ImageRequest,
    ImageResponse,
    ImageSize,
    ImageStatus,
)

router = APIRouter()

@router.post("/prompt", response_model=ImageResponse)
async def preview_refined_prompt(
    prompt: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    size: Optional[str] = Form(None),
    style: Optional[str] = Form(None),
    aspect_ratio: Optional[str] = Form(None),
    output_format: Optional[ImageMimeType] = Form(ImageMimeType.PNG),
    session_id: Optional[str] = Form(None),
    category: Optional[ImageCategory] = Form(None),
    *,
    current_user: CurrentUser,
    agent_service: AgentServiceDep,
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
    )

    user_uuid = current_user.id
    user_id = str(user_uuid)

    session_id = session_id or str(uuid.uuid4())

    await ensure_session_exists(user_id, session_id)

    file_payloads = await prepare_upload_payloads(request.files)
    resolved_prompt, category, normalized_style = resolve_prompt_and_category(request)

    size = request.size or ImageSize.MEDIUM
    output_format = request.output_format or ImageMimeType.PNG

    title_source = request.prompt or resolved_prompt
    session_title = (title_source or "Image request")[:200]

    agent_service.start_turn(
        app_name=settings.GOOGLE_AGENT_NAME,
        agent_name="triage_agent",
        session_id=session_id,
        user_id=user_uuid,
        title=session_title,
    )



    text_for_agent = "\n\n".join(
        filter(
            None,
            [
                *(
                    f"ImageCategory: {category.value}" if category else [],
                    f"ImageSize: {size.value}" if size else [],
                    f"AspectRatio: {request.aspect_ratio.value}" if request.aspect_ratio else [],
                    f"Style: {normalized_style}" if normalized_style else [],
                ),
                resolved_prompt.strip() if resolved_prompt else None,
            ],
        )
    )

    try:
        await run_root_agent(user_id, session_id, text_for_agent)

        refined_prompt = (
            await fetch_refined_prompt(user_id, session_id, resolved_prompt)
        ).strip()

        final_bytes = await generate_image_bytes(
            file_payloads=file_payloads,
            refined_prompt=refined_prompt,
            output_format=output_format,
        )
    except Exception:
        agent_service.finish_turn(
            app_name=settings.GOOGLE_AGENT_NAME,
            agent_name="triage_agent",
            session_id=session_id,
            user_id=user_uuid,
            status=ImageStatus.FAILED,
            title=session_title,
        )
        raise
    else:
        agent_service.finish_turn(
            app_name=settings.GOOGLE_AGENT_NAME,
            agent_name="triage_agent",
            session_id=session_id,
            user_id=user_uuid,
            status=ImageStatus.COMPLETED,
            title=session_title,
        )

    # Save the generated image to the generated-img folder
    out_dir = os.path.join(os.getcwd(), "generated-img")
    os.makedirs(out_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{output_format.name.lower()}"
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "wb") as f:
        f.write(final_bytes)

    encoded_image = f"data:{output_format.value};base64,{base64.b64encode(final_bytes).decode()}"

    return ImageResponse(
        status=ImageStatus.COMPLETED if refined_prompt else ImageStatus.PENDING,
        refined_prompt=refined_prompt,
        size=size.value if isinstance(size, ImageSize) else str(size),
        style=request.style,
        aspect_ratio=request.aspect_ratio.value if request.aspect_ratio else None,
        session_id=session_id,
        category=category.value if category else None,
        user_id=user_id,
        output_file=encoded_image,
    )
