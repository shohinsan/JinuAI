

import asyncio
import uuid
from io import BytesIO
from typing import Any, Optional, cast

from fastapi import UploadFile
from google import genai
from google.genai import types
from google.genai.types import (
    GenerateContentConfig,
    HarmBlockThreshold,
    HarmCategory,
    Part,
    SafetySetting,
)

from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.sessions import Session
from PIL import Image

from app.utils.agent_tool import get_predefined_styles
from app.utils.config import get_banana_session_service, settings
from app.utils.models import ImageCategory, ImageMimeType, ImageRequest, ImageStatus

SYSTEM_AGENT_AUTHOR = "triage_agent"

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
) -> Session:
    """Append an event to the session, optionally updating state.

    ADK expects the session object to carry the latest `last_update_time`. We
    re-fetch the session before and after appending to avoid stale-state errors
    when multiple events land quickly.
    """

    actions = EventActions(state_delta=state_delta or {})

    content = None
    if text:
        content = types.Content(
            role=author,
            parts=[types.Part.from_text(text=text)],
        )

    event = Event(
        author=author,
        invocation_id=str(uuid.uuid4()),
        actions=actions,
        content=content,
        custom_metadata=custom_metadata,
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
    )


async def finish_session_turn(
    session: Session,
    *,
    status: ImageStatus,
    title: str | None = None,
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
    )


async def prepare_upload_payloads(files: list[UploadFile]) -> list[tuple[bytes, str]]:
    # Read and validate uploaded files

    payloads = []
    for i, upload in enumerate(files, 1):
        data = await upload.read()
        await upload.seek(0)

        with Image.open(BytesIO(data)) as img:
            img_format = img.format

        mime = Image.MIME.get(img_format, upload.content_type or ImageMimeType.PNG.value)
        payloads.append((data, mime))

    return payloads


def resolve_prompt_and_category(
    request: ImageRequest,
) -> tuple[str, Optional[ImageCategory], Optional[str]]:
    # Use either the user-provided prompt or the style prompt (one or the other)

    resolved_prompt, resolved_category = (
        request.prompt or get_predefined_styles(request.style)[0],
        request.category
    )
    return resolved_prompt, resolved_category, None

async def generate_image_bytes(
    file_payloads: list[tuple[bytes, str]],
    refined_prompt: str,
    output_format: ImageMimeType = ImageMimeType.PNG,
) -> bytes:
    # Generate image bytes from the refined prompt and uploaded files

    client = cast(genai.Client, settings.google_genai_client)

    # Prepare contents: files + prompt
    contents = [
        Part.from_bytes(data=data, mime_type=mime or output_format.value)
        for data, mime in file_payloads
    ] + [Part.from_text(text=refined_prompt)]

    config = GenerateContentConfig(
        response_modalities=["IMAGE"],
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

    # Extract the first inline image bytes
    for candidate in response.candidates:
        for part in candidate.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return inline.data

    raise ValueError("Image generation response did not include inline image data")


async def fetch_refined_prompt(
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
        refined = (final_session.state.get("refined_prompt") or "").strip()
        if refined:
            return refined

    return fallback_prompt


async def run_root_agent(
    user_id: str,
    session_id: str,
    text_for_agent: str,
) -> Optional[str]:
    from app.utils.agent_orchestration import runner_image

    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=text_for_agent)],
    )

    final_text: Optional[str] = None

    async for event in runner_image.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        if event.error_message:
            raise RuntimeError(event.error_message)

        event_content = getattr(event, "content", None)
        if event_content and getattr(event_content, "parts", None):
            text_segments = [
                getattr(part, "text", "")
                for part in event_content.parts
                if getattr(part, "text", None)
            ]
            joined = "\n".join(segment.strip() for segment in text_segments if segment)
            if joined:
                final_text = joined

        if event.is_final_response():
            break

    return final_text
