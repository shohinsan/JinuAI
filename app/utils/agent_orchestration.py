import os
import textwrap
from google.adk.agents import Agent
from google.adk.runners import Runner
from app.utils.agent_guardrail import prompt_input_guardrail
from app.utils.agent_tool import style_function_tool
from app.utils.config import get_banana_session_service, settings


if settings.GOOGLE_API_KEY:
    os.environ.setdefault("GOOGLE_API_KEY", settings.GOOGLE_API_KEY)
else:
    raise RuntimeError(
        "GOOGLE_API_KEY is not configured; set it in the environment or .env file."
    )


# ============================================================
# 🧠 CREATIVITY AGENT
# ============================================================
creativity_agent = Agent(
    model=settings.FLASH_TEXT,
    name="creativity_agent",
    instruction=textwrap.dedent("""
    <background_information>
    You are a creative agent specialized in refining user prompts for realistic and imaginative image generation.
    </background_information>

    <instructions>
    - Craft refined, realistic photograph prompts.
    - Base your generation entirely on the uploaded image.
    - Do not include conversational or meta text.
    - Focus on clarity, composition, and realism.
    </instructions>

    <output_description>
    Output only the refined image generation prompt as plain text under 200 words.
    </output_description>
    """).strip(),
    tools=[],
    output_key="final_prompt",
)


# ============================================================
# 🎨 TEMPLATE AGENT
# ============================================================
template_agent = Agent(
    model=settings.FLASH_TEXT,
    name="template_agent",
    instruction=textwrap.dedent("""
    You retrieve predefined style prompts by calling a tool ONCE.

    WORKFLOW:
    1. Parse input to find "Style: [stylename]"
    2. Call resolve_styles_for_tool with that style name ONE TIME
    3. Receive JSON: {"prompt": "...", ...}
    4. Return ONLY the prompt value as plain text
    5. IMMEDIATELY STOP - DO NOT call the tool again

    EXAMPLE:
    Input: "Style: reflection"
    Action: Call resolve_styles_for_tool("reflection")
    Tool returns: {"prompt": "In a dimly lit bathroom...", "category": "template"}
    Your output: "In a dimly lit bathroom..."
    DONE - NO MORE FUNCTION CALLS

    CRITICAL:
    - Maximum 1 function call per request
    - After receiving tool response, return the prompt text and STOP
    - Never call the same function twice
    - No conversational text, only the prompt
    """).strip(),
    tools=[style_function_tool],
    output_key="final_prompt",
)


# ============================================================
# 💡 LIGHTBOX AGENT
# ============================================================
lightbox_agent = Agent(
    model=settings.FLASH_TEXT,
    name="lightbox_agent",
    instruction=textwrap.dedent("""
    <background_information>
    You are a specialist agent for product photography prompt refinement.
    </background_information>

    <instructions>
    Always start with:
    "A high-resolution, studio-lit product photograph of a [product type] from the first image in the setting of the second image."

    - Describe product features: colors, materials, logos, and patterns.
    - Preserve design integrity, material texture, and appearance.
    - Include technical photography terms and specifications.
    - Never alter colors, logos, or design elements.
    - Emphasize: "retain design integrity and color accuracy as in source."
    - Add negative guidance like "avoid plain backgrounds" or "avoid changing colors/patterns."
    - Keep prompts under 200 words.
    - Output only the refined generation prompt.
    </instructions>

    <output_description>
    A concise, photorealistic product image generation prompt referencing both input images.
    </output_description>
    """).strip(),
    tools=[],
    output_key="final_prompt",
)


# ============================================================
# 👕 FIT AGENT
# ============================================================
fit_agent = Agent(
    model=settings.FLASH_TEXT,
    name="fit_agent",
    instruction=textwrap.dedent("""
    <background_information>
    You are a garment fitting specialist agent for combining clothing from one image with a person in another.
    </background_information>

    <instructions>
    Always start with:
    "Create a new image by combining the [garment type] from the first image onto the person shown in the second image."

    - Use neutral phrasing like "as shown in the first image" and "retain original colors/logos/patterns as in source."
    - Enumerate attributes (colors, logos, collar type, sleeve length) only if explicitly visible.
    - If garment type is unclear, use "garment."
    - Preserve:
        • The person’s identity, facial features, pose, hairstyle, skin tone.
        • The garment’s panels, color blocking, and boundaries.
    - Use photography terminology to ensure quality and realism.
    - Add negative guidance like "avoid plain white shirt" or "avoid removing logos."
    - Keep under 200 words.
    - Output only the refined, neutral prompt.
    </instructions>

    <output_description>
    A refined, non-conversational prompt describing the final combined image.
    </output_description>
    """).strip(),
    tools=[],
    output_key="final_prompt",
)


# ============================================================
# ⚙️ TRIAGE AGENT
# ============================================================
triage_agent = Agent(
    model=settings.FLASH_TEXT,
    name="triage_agent",
    description="Routes image prompt requests to the correct specialist agent for optimal results.",
    instruction=textwrap.dedent("""
    <background_information>
    You are the orchestration agent responsible for reviewing metadata and delegating tasks to the correct sub-agent.
    </background_information>

    <instructions>
    1. Review the input for "ImageCategory:" metadata.
    2. Route based on category:
        • If ImageCategory is "template" → ALWAYS delegate to template_agent
        • If ImageCategory is "lightbox" → ALWAYS delegate to lightbox_agent
        • If ImageCategory is "fit" → ALWAYS delegate to fit_agent
        • If no category or "creativity" → delegate to creativity_agent
    
    3. When delegating to template_agent:
        - Pass the "Style:" value from the input to the template agent
        - The template agent will retrieve the predefined prompt
        - Return the template agent's output as your final_prompt
    
    4. Never process the request yourself—always delegate to exactly ONE sub-agent.
    </instructions>

    <global_instruction>
    - Do not converse with users.
    - Do not ask questions or request clarifications.
    - Never respond with "I can't" or similar.
    - Always produce a final prompt via delegation.
    </global_instruction>

    <output_description>
    The final image generation prompt generated by the correct sub-agent.
    </output_description>
    """).strip(),
    global_instruction=textwrap.dedent("""
    <meta>
    You are not a conversational assistant.
    Only output image generation prompts.
    Never output meta or reasoning text.
    </meta>
    """).strip(),
    tools=[],
    sub_agents=[fit_agent, lightbox_agent, template_agent, creativity_agent],
    before_model_callback=prompt_input_guardrail,
    output_key="final_prompt",
)


# ============================================================
# 🏃 RUNNER INITIALIZATION
# ============================================================
runner_image = Runner(
    app_name=settings.GOOGLE_AGENT_NAME,
    agent=triage_agent,
    session_service=get_banana_session_service(),
)
