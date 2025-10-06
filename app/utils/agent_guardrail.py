
import re
from typing import Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai.types import Content, HarmCategory, Part


BLOCKED_PROMPT_RESPONSE = (
    "I cannot process this request because it violates the safety policy."
)

def prompt_input_guardrail(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Lightweight guardrail to intercept disallowed prompts before model calls."""

    try:
        last_user_message_text = next(
            part.text
            for content in reversed(llm_request.contents or [])
            if content.role == "user"
            for part in (content.parts or [])
            if getattr(part, "text", None)
        )
    except StopIteration:
        return None

    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]+", " ", value.lower())).strip()

    sanitized = normalize(last_user_message_text)
    banned_tokens: tuple[tuple[str, HarmCategory], ...] = (
        ("child sexual", HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT),
        ("child abuse", HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT),
        ("csam", HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT),
        ("bestiality", HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT),
        ("extreme gore", HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT),
        ("decapitation", HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT),
        ("terrorist propaganda", HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT),
        ("self harm", HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT),
        ("suicide tutorial", HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT),
    )

    violation = next(
        (
            (token, category)
            for token, category in banned_tokens
            if normalize(token) in sanitized
        ),
        None,
    )

    if not violation and "BLOCK" not in last_user_message_text.upper():
        return None

    token, category = violation if violation else ("BLOCK", None)
    category_value = getattr(category, "value", None) if category else None

    callback_context.state["guardrail_violation_token"] = token
    if category_value:
        callback_context.state["guardrail_violation_category"] = category_value

    return LlmResponse(
        content=Content(
            role="model",
            parts=[Part.from_text(text=BLOCKED_PROMPT_RESPONSE)],
        )
    )
