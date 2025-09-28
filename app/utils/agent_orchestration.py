import textwrap
from app.llm.openai_llm import OpenAIChatLlm
from openai import AsyncOpenAI
from google.adk.agents import Agent
from google.adk.runners import Runner
from app.utils.agent_guardrail import prompt_input_guardrail
from app.utils.agent_tool import style_function_tool
from app.utils.config import get_banana_session_service, settings

openai_compat_llm = OpenAIChatLlm(
    model="gemma3:12b",
    client=AsyncOpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    ),
)

creativity_agent = Agent(
    model=openai_compat_llm,
    name="creativity_agent",
    instruction=textwrap.dedent("""You are a creative agent that refines user prompts for image generation. \
    Craft a refined, realistic photograph based on the uploaded image.
    """
    ).strip(),
    tools=[],
    output_key="refined_prompt",
)

template_agent = Agent(
    model=openai_compat_llm,
    name="template_agent",
    instruction = textwrap.dedent("""You are a template agent that returns predefined style prompts directly from the inline presets. \
    When a user requests a particular style, use the `get_predefined_styles` tool to retrieve the exact prompt registered in code \
    and return it without any modifications or refinements. Simply output the retrieved prompt as your refined_prompt.
    """
    ).strip(),
    tools=[style_function_tool],
    output_key="refined_prompt",
)


lightbox_agent = Agent(
    model=openai_compat_llm,
    name="lightbox_agent",
    instruction=textwrap.dedent("""When refining prompts, always start with \
    "A high-resolution, studio-lit product photograph of a [product type] from the first image in the setting of the second image," \
    describing the product's visual features such as colors, materials, logos, and patterns, preserving its integrity and appearance, \
    including technical photography terms and quality specifications, maintaining original features without altering colors, \
    logos, or design elements, specifying details like color schemes, logo placement, and material texture, emphasizing \
    "retain design integrity and color accuracy as in source," adding negative guidance like "avoid plain backgrounds" or \
    "avoid changing colors/patterns," keeping prompts under 200 words, focusing on the final image's appearance, and never \
    outputting conversational text, only product image generation prompts referencing the first and second images.
    """
    ).strip(),
    tools=[],
    output_key="refined_prompt",
)


fit_agent = Agent(
    model=openai_compat_llm,
    name="fit_agent",
    instruction=textwrap.dedent("""When refining prompts, always start with "Create a new image by combining the [garment type] \
    from the first image onto the person shown in the second image," avoid inventing specifics by using neutral phrasing like \
    "as shown in the first image" and "retain original colors/logos/patterns as in source," only enumerate attributes \
    such as colors, logos, patterns, collar type, or sleeve length when explicitly given or extracted from images, \
    use "garment" if the type is uncertain, describe known visual features, include details about preserving \
    the person's identity and pose, incorporate technical photography terms and quality specifications, maintain \
    facial features, expression, hairstyle, and skin tone, preserve original pose and body posture, emphasize retaining \
    panel boundaries and color blocking as in the source, add negative guidance like "avoid plain white shirt," \
    "avoid removing logos," or "avoid changing colors/patterns," include any size hint like "ImageSize: <WxH>" \
    verbatim at the end, keep the refined prompt under 200 words, and focus on clearly specifying what the final image should look like.
    """
    ).strip(),
    tools=[],
    output_key="refined_prompt",
)


triage_agent = Agent(
    model=settings.FLASH_TEXT,
    name="triage_agent",
    description="Improves user prompts for optimal image generation results",
    instruction=textwrap.dedent("""You are the orchestration agent for image prompt refinement, reviewing metadata \
    hints to delegate to the correct specialist — `template_agent` for predefined style prompts (returns exact prompts from the inline preset list), \
    `lightbox_agent` for product, `fit_agent` for model, and `creativity_agent` for creative—always delegating before producing the final refined prompt.
    """
    ).strip(),
    global_instruction=textwrap.dedent("""You are not having a conversation with the user and not acting as \
    an assistant that responds to users; instead, you only output refined prompts for product image generation, \
    never asking questions or requesting clarification, never saying "I can't" or "I need more information," \
    and always producing a refined prompt even if the input is vague.
    """
    ).strip(),
    tools=[],
    sub_agents=[fit_agent, lightbox_agent, template_agent, creativity_agent],
    before_model_callback=prompt_input_guardrail,
    output_key="refined_prompt",
)


runner_image = Runner(
    app_name=settings.GOOGLE_AGENT_NAME,
    agent=triage_agent,
    session_service=get_banana_session_service(),
)
