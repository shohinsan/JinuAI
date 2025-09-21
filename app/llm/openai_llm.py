from __future__ import annotations

from typing import AsyncGenerator, List

from openai import AsyncOpenAI
from google.genai import types

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse


class OpenAIChatLlm(BaseLlm):
    """Minimal BaseLlm adapter that calls an OpenAI-compatible Chat Completions API.

    Notes:
    - Supports text-only prompts; ignores tools and advanced configs.
    - Suitable for prompt refinement agents that only need plain text output.
    """

    def __init__(self, model: str, client: AsyncOpenAI) -> None:
        super().__init__(model=model)
        self._client = client

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        if stream:
            # Streaming not implemented for this minimal adapter.
            raise NotImplementedError("Streaming not supported in OpenAIChatLlm")

        messages: List[dict] = []

        # System instruction
        if llm_request.config and llm_request.config.system_instruction:
            messages.append(
                {"role": "system", "content": llm_request.config.system_instruction}
            )

        # Convert google.genai types.Content -> OpenAI chat messages (text only)
        for content in llm_request.contents or []:
            text_parts = []
            for part in content.parts or []:
                if getattr(part, "text", None):
                    text_parts.append(part.text)
            if not text_parts:
                continue
            role = "user" if content.role == "user" else "assistant"
            messages.append({"role": role, "content": "\n\n".join(text_parts)})

        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
        )

        text = ""
        if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
            text = resp.choices[0].message.content

        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=text or "")],
            )
        )

