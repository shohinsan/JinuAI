

import asyncio
import logging
import uuid
from io import BytesIO
from typing import Any, Optional, cast

from fastapi import UploadFile
from google import genai
from google.genai.errors import APIError
from google.genai.types import (
    Blob,
    GenerateContentConfig,
    HarmBlockThreshold,
    ImageConfig,
    HarmCategory,
    Content,
    Part,
    SafetySetting,
)

from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.sessions import Session
from PIL import Image

from app.utils.agent_tool import resolve_styles_for_tool
from app.utils.config import get_banana_session_service, settings
from app.utils.models import ImageAspectRatio, ImageCategory, ImageMimeType, ImageRequest, ImageStatus

SYSTEM_AGENT_AUTHOR = "triage_agent"

logger = logging.getLogger(__name__)
# Reduce noisy warnings from the Google GenAI SDK when responses include
# structured parts we don't need to inspect directly.
logging.getLogger("google.genai.types").setLevel(logging.ERROR)

async def ensure_session_exists(user_id: str, session_id: str) -> Session:
    """Return an existing session or create one if absent."""

    banana_session_service = get_banana_session_service()

    session = await banana_session_service.get_session(
        app_name=settings.GOOGLE_AGENT_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    if session is None:
        session = await banana_session_service.create_session(
            app_name=settings.GOOGLE_AGENT_NAME,
            user_id=user_id,
            session_id=session_id,
            state={
                "status": ImageStatus.PENDING.value,
                "turn_count": 0,
            },
        )

    return session


async def append_session_event(
    session: Session,
    *,
    author: str,
    text: str | None = None,
    state_delta: dict[str, Any] | None = None,
    custom_metadata: dict[str, Any] | None = None,
    turn_complete: bool | None = None,
    interrupted: bool | None = None,
) -> Session:
    """Append an event to the session, optionally updating state.

    ADK expects the session object to carry the latest `last_update_time`. We
    re-fetch the session before and after appending to avoid stale-state errors
    when multiple events land quickly.
    """

    actions = EventActions(state_delta=state_delta or {})

    content = None
    if text:
        role = "user" if author == "user" else "model"
        content = Content(
            role=role,
            parts=[Part.from_text(text=text)],
        )

    event = Event(
        author=author,
        invocation_id=str(uuid.uuid4()),
        actions=actions,
        content=content,
        custom_metadata=custom_metadata,
        turn_complete=turn_complete,
        interrupted=interrupted,
    )

    banana_session_service = get_banana_session_service()

    latest_session = await banana_session_service.get_session(
        app_name=session.app_name,
        user_id=session.user_id,
        session_id=session.id,
    )

    session_for_write = latest_session or session

    await banana_session_service.append_event(
        session=session_for_write,
        event=event,
    )

    refreshed = await banana_session_service.get_session(
        app_name=session.app_name,
        user_id=session.user_id,
        session_id=session.id,
    )

    return refreshed or session_for_write


async def start_session_turn(
    session: Session,
    *,
    title: str | None = None,
) -> Session:
    """Increment turn count and mark the session as processing."""

    existing_turns = int(session.state.get("turn_count", 0) or 0)
    state_delta: dict[str, object] = {
        "status": ImageStatus.PROCESSING.value,
        "turn_count": existing_turns + 1,
    }
    if title is not None:
        state_delta["title"] = title

    return await append_session_event(
        session,
        author=SYSTEM_AGENT_AUTHOR,
        state_delta=state_delta,
        text="Session turn started",
        custom_metadata={
            "status": ImageStatus.PROCESSING.value,
            "turn_count": state_delta["turn_count"],
        },
        turn_complete=False,
    )


async def finish_session_turn(
    session: Session,
    *,
    status: ImageStatus,
    title: str | None = None,
    interrupted: bool | None = None,
) -> Session:
    """Store the final status for the session turn."""

    state_delta: dict[str, object] = {"status": status.value}
    if title is not None:
        state_delta["title"] = title

    metadata: dict[str, Any] = {"status": status.value}
    if title is not None:
        metadata["title"] = title

    return await append_session_event(
        session,
        author=SYSTEM_AGENT_AUTHOR,
        state_delta=state_delta,
        text=f"Session turn {status.value.lower()}",
        custom_metadata=metadata,
        turn_complete=True,
        interrupted=interrupted,
    )


async def prepare_upload_payloads(files: list[UploadFile]) -> list[tuple[bytes, str]]:
    """Convert uploaded files into (bytes, mime_type) tuples for processing.
    
    Args:
        files: List of uploaded file objects
        
    Returns:
        List of (image_bytes, mime_type) tuples
    """
    payloads = []
    
    for upload_file in files:
        # Read file data
        file_bytes = await upload_file.read()
        await upload_file.seek(0)  # Reset file pointer

        # Detect image format using PIL
        with Image.open(BytesIO(file_bytes)) as img:
            image_format = img.format

        # Get MIME type from PIL's mapping or fall back to content_type
        mime_type = Image.MIME.get(
            image_format, 
            upload_file.content_type or ImageMimeType.PNG.value
        )
        
        payloads.append((file_bytes, mime_type))

    return payloads


def get_input_prompt_and_category(
    request: ImageRequest,
) -> tuple[str, Optional[ImageCategory], Optional[str]]:
    """Get the input prompt and category from the request.
    
    For template category: uses style-based template prompt (user prompt is ignored).
    For other categories: uses user-provided prompt, or falls back to style prompt.
    
    Args:
        request: The image generation request
        
    Returns:
        Tuple of (input_prompt, category, normalized_style)
    """
    style_info = resolve_styles_for_tool(request.style)
    style_prompt = (style_info or {}).get("prompt")
    style_category = (style_info or {}).get("category")
    normalized_style = (style_info or {}).get("normalized_style")

    category = request.category
    if category is None and style_category:
        normalized_style_category = str(style_category).strip().lower()
        if normalized_style_category == ImageCategory.TEMPLATE.value:
            category = ImageCategory.TEMPLATE
        elif normalized_style_category == ImageCategory.FIT.value:
            category = ImageCategory.FIT
        elif normalized_style_category in {
            ImageCategory.DEFAULT.value,
            "creativity",
            "creative",
        }:
            category = ImageCategory.DEFAULT
        elif normalized_style_category == "lightbox":
            category = ImageCategory.TEMPLATE

    # Templates always use predefined style prompt; others use user prompt with style fallback
    category = category or ImageCategory.DEFAULT

    should_use_template = category == ImageCategory.TEMPLATE
    user_prompt = None if should_use_template else request.prompt

    input_prompt = user_prompt or style_prompt or ""
    return input_prompt, category, normalized_style

async def generate_image_bytes(
    file_payloads: list[tuple[bytes, str]],
    prompt: str,
    aspect_ratio: Optional[ImageAspectRatio] = None,
    output_format: ImageMimeType = ImageMimeType.PNG,
) -> bytes:
    """Generate image bytes from the prompt and uploaded files.
    
    Args:
        file_payloads: List of (bytes, mime_type) tuples for input images
        prompt: The text prompt for generation
        aspect_ratio: Optional aspect ratio for the generated image
        output_format: Output image format (PNG or JPEG)
    
    Returns:
        bytes: The generated image data
    """
    client = cast(genai.Client, settings.google_genai_client)

    # Prepare contents: convert bytes to images using as_image(), then add prompt
    image_parts = []
    for data, mime in file_payloads:
        # Create Part from bytes using inline data (no file URI required)
        part = Part.from_bytes(data=data, mime_type=mime or output_format.value)
        image_parts.append(part)
    
    contents = image_parts + [Part.from_text(text=prompt)]

    # Build config with optional aspect ratio
    image_config = None
    if aspect_ratio:
        image_config = ImageConfig(aspect_ratio=aspect_ratio.value)
    
    config = GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=image_config,
        safety_settings=[
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
        ],
    )

    # Run generation
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model=settings.FLASH_IMAGE,
            contents=contents,
            config=config,
        )
    )

    # Extract image data from response (following Google's official pattern)
    for part in response.parts:
        if part.inline_data is not None:
            inline_data: Blob = part.inline_data
            image = inline_data.as_image()
            return image.image_bytes

    raise ValueError("Image generation response did not include inline image data")


async def fetch_prompt(
    user_id: str,
    session_id: str,
    fallback_prompt: str,
) -> str:
    banana_session_service = get_banana_session_service()

    final_session = await banana_session_service.get_session(
        app_name=settings.GOOGLE_AGENT_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    if final_session and final_session.state:
        prompt = final_session.state.get("prompt", "").strip()
        if prompt:
            return prompt

    return fallback_prompt


async def run_root_agent(
    user_id: str,
    session_id: str,
    text_for_agent: str,
) -> Optional[str]:
    """Run the root agent with the given text and extract the refined prompt.
    
    Args:
        user_id: The user identifier
        session_id: The session identifier
        text_for_agent: The text input for the agent
        
    Returns:
        The refined prompt text if available, None otherwise
    """
    from app.utils.agent_orchestration import runner_image

    content = Content(
        role="user",
        parts=[Part.from_text(text=text_for_agent)],
    )

    refined_text: Optional[str] = None

    try:
        async for event in runner_image.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            # Check for errors
            if event.error_message:
                raise RuntimeError(event.error_message)

            # Extract text from event content parts
            event_content = getattr(event, "content", None)
            if event_content:
                parts = getattr(event_content, "parts", None)
                if parts:
                    # Collect all text segments from parts
                    text_segments = [
                        part.text
                        for part in parts
                        if getattr(part, "text", None)
                    ]
                    # Join non-empty segments
                    joined_text = "\n".join(segment.strip() for segment in text_segments if segment)
                    if joined_text:
                        refined_text = joined_text

            # Stop when we get the final response
            if event.is_final_response():
                break

    except APIError as exc:
        logger.warning("Gemini agent run failed: %s", exc)
        return None

    return refined_text
