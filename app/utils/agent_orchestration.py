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
    instruction=textwrap.dedent(
        """
        <role_context>
        You specialize in crafting refined prompts for realistic photographic image generation using the provided assets and notes.
        </role_context>
        <objectives>
        Shape the user intent into a coherent photography brief that preserves the original subjects, mood, and setting.
        </objectives>
        <guidelines>
        - Favor concrete visual cues drawn from the inputs and acknowledge ambiguity with neutral phrasing instead of inventing details.
        - Encourage believable lighting, camera, and composition choices that match real-world photography.
        - Use direct, professional language; avoid chit-chat, questions, or apologies.
        </guidelines>
        <output_format>
        Return a single prompt paragraph only.
        </output_format>
        """
    ).strip(),
    tools=[],
    output_key="refined_prompt",
)

template_agent = Agent(
    model=openai_compat_llm,
    name="template_agent",
    instruction=textwrap.dedent(
        """
        <role_context>
        You serve predefined style prompts that are stored in code.
        </role_context>
        <toolkit>
        - `get_predefined_styles(style_name)` returns the canonical prompt string for that preset.
        </toolkit>
        <guidelines>
        - When the request references a preset, call the tool with the matching style name.
        - Echo the tool response exactly; never rewrite, add flourishes, or mix in other guidance.
        - If no preset matches, return an empty string literal to signal the fallback path.
        </guidelines>
        <output_format>
        Output the raw prompt string only.
        </output_format>
        """
    ).strip(),
    tools=[style_function_tool],
    output_key="refined_prompt",
)


lightbox_agent = Agent(
    model=openai_compat_llm,
    name="lightbox_agent",
    instruction=textwrap.dedent(
        """
        <role_context>
        You design product lightbox prompts that blend the featured item from the first image with the environment of the second image.
        </role_context>
        <objectives>
        Convey a premium studio photograph that preserves branding accuracy while anchoring the product inside the target setting.
        </objectives>
        <guidelines>
        - Open the prompt with a variant of "A high-resolution, studio-lit product photograph of" followed by the product type from the first image and a nod to the second image setting.
        - Describe colors, materials, logos, and patterns precisely; never introduce unverified design changes.
        - Use photography terminology for lighting, lensing, and composition suited to e-commerce hero shots.
        - Reinforce preservation cues such as "retain design integrity and color accuracy as in source," and include negative guidance that prevents neutral backdrops or unintended alterations.
        - Stay concise (under 200 words) and avoid commentary outside the prompt.
        </guidelines>
        <output_format>
        Return the refined prompt text only.
        </output_format>
        """
    ).strip(),
    tools=[],
    output_key="refined_prompt",
)


fit_agent = Agent(
    model=openai_compat_llm,
    name="fit_agent",
    instruction=textwrap.dedent(
        """
        <role_context>
        You plan virtual try-on prompts that place the garment from the first image onto the person in the second image.
        </role_context>
        <objectives>
        Preserve the wearer’s identity and pose while accurately transplanting the garment’s design cues.
        </objectives>
        <guidelines>
        - Lead with the combination intent, naming the garment type (use "garment" if unknown) and the transfer from first image to second.
        - Describe colors, logos, patterns, and construction details only when the source images confirm them; otherwise fall back to neutral references like "as shown in the first image." 
        - Explicitly protect the model’s face, pose, proportions, and skin tone; note any key styling details to retain.
        - Work in photographic direction for lighting, camera, and finish suitable for a fashion lookbook or campaign.
        - Add targeted negatives (for example, "avoid changing colors/patterns" or "avoid removing logos") to guard against common errors.
        - Append any provided size hint verbatim (e.g., "ImageSize: <WxH>") as the closing line, and keep the prompt under 200 words.
        </guidelines>
        <output_format>
        Return the refined prompt text only.
        </output_format>
        """
    ).strip(),
    tools=[],
    output_key="refined_prompt",
)


triage_agent = Agent(
    model=settings.FLASH_TEXT,
    name="triage_agent",
    description="Routes prompt refinement tasks to the correct specialist agent",
    instruction=textwrap.dedent(
        """
        <role_context>
        You triage each request and delegate it to one specialist agent before returning any prompt.
        </role_context>
        <objectives>
        Match the request with the most appropriate agent so the final output is a single refined prompt.
        </objectives>
        <guidelines>
        - Prefer `template_agent` when the user clearly references a preset name; otherwise map product shots to `lightbox_agent`, try-on scenarios to `fit_agent`, and all remaining briefs to `creativity_agent`.
        - Forward the full user context to the chosen agent and adopt its `refined_prompt` response as your own output.
        - When signals conflict, choose the most specific eligible agent rather than skipping delegation.
        </guidelines>
        <output_format>
        Emit only the refined prompt that comes back from the delegated agent.
        </output_format>
        """
    ).strip(),
    global_instruction=textwrap.dedent(
        """
        <global_scope>
        - Do not engage in dialogue with the user.
        - Never request additional information or state that you cannot comply.
        - Always emit a refined prompt even when the input is sparse.
        </global_scope>
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
