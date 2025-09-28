import base64
import os
from typing import List, Optional
import uuid
from fastapi import APIRouter, File, Form, UploadFile
from app.utils.agent_helpers import (
    ensure_session_exists,
    fetch_refined_prompt,
    finish_session_turn,
    append_session_event,
    generate_image_bytes,
    prepare_upload_payloads,
    resolve_prompt_and_category,
    run_root_agent,
    start_session_turn,
    SYSTEM_AGENT_AUTHOR,
)
from app.utils.delegate import CurrentUser
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

    user_id = str(current_user.id)

    session_id = session_id or str(uuid.uuid4())

    session = await ensure_session_exists(user_id, session_id)
    session_id = session.id

    file_payloads = await prepare_upload_payloads(request.files)
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
                    f"ImageSize: {size.value}" if size else [],
                    f"AspectRatio: {request.aspect_ratio.value}" if request.aspect_ratio else [],
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
            output_format=output_format,
        )
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
        )
        raise
    else:
        session = await finish_session_turn(
            session,
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

    session = await append_session_event(
        session,
        author=SYSTEM_AGENT_AUTHOR,
        text="Image generation completed",
        custom_metadata={
            "status": ImageStatus.COMPLETED.value,
            "output_path": filename,
        },
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
    )
