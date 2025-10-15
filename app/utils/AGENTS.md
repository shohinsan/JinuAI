# Utils Folder Rules (`app/utils/`)

**models.py**: All SQLModel schemas, database models, request/response models

**config.py**: Pydantic settings management with environment variable support

**security.py**: Authentication, hashing, token generation utilities

**sqldb.py**: Database connection, session management

**redisdb.py**: Redis connection and caching utilities

**delegate.py**: Dependency injection definitions for FastAPI
```python
def get_{domain}_repository(session: SessionDep) -> {Domain}Repository:
    """Get {domain} repository dependency."""
    return {Domain}Repository(session)

def get_{domain}_service(
    repository: Annotated[{Domain}Repository, Depends(get_{domain}_repository)],
) -> {Domain}Service:
    """Get {domain} service dependency."""
    return {Domain}Service(repository)

{Domain}RepositoryDep = Annotated[{Domain}Repository, Depends(get_{domain}_repository)]
{Domain}ServiceDep = Annotated[{Domain}Service, Depends(get_{domain}_service)]
```

**exceptions.py**: Custom exception classes

**Organization**: Group related models and utilities logically

**Type Safety**: Use SQLModel for database models, Pydantic for API models

**Validation**: Include custom validators for phone numbers, emails, etc.

**Enums**: Define enums for status fields and other constrained values

**agent_guardrail.py**:
- Owns `prompt_input_guardrail`, the ADK `before_model_callback` that inspects the last user message and short-circuits unsafe prompts.
- Normalize user text before matching; extend `banned_tokens` when introducing new policy requirements and persist the block message in `BLOCKED_PROMPT_RESPONSE`.
- Record any violation metadata on `callback_context.state` so downstream agents can log or audit the rejection without reprocessing the prompt.

**agent_helpers.py**:
- Async utility layer for the agent workflow: session bootstrapping, upload preparation, prompt resolution, and final image generation.
- All writes to the ADK persistence layer (sessions, user/app state, events) go through helpers here; `ensure_session_exists`, `start_session_turn`, `finish_session_turn`, and `append_session_event` keep state changes consistent.
- Keep `prepare_upload_payloads` lossless—perform normalization only (no resizing) and preserve MIME types resolved via Pillow.
- `generate_image_bytes` is the single entry for Google GenAI calls; update safety thresholds or response parsing here and keep the async executor boundary intact.
- `run_root_agent` streams events from `runner_image`; funnel new result fields through the generator loop without breaking final-response detection.

**agent_orchestration.py**:
- Defines shared LLM clients plus the specialist agents (`default`, `template`, `fit`) and the `triage_agent` orchestrator. Lightbox requests now flow through template presets rather than a dedicated agent.
- Keep agent instructions terse, deterministic, and free of conversational language; any prompt template changes belong here.
- Add new tools by updating both the agent config and the corresponding helper/tool modules, then register them on the correct sub-agent list.
- `Runner` wiring must always include `settings.GOOGLE_BANANA_MODEL_SESSION` and `prompt_input_guardrail`; do not bypass the guardrail in production flows.

- **agent_tool.py**:
- Style presets live in the `STYLE_PRESETS` constant; extend that mapping when adding new prompts so the tool stays source-controlled.
- Preserve the lazy mapping contract of `STYLE_PRESETS`; new preset keys must normalize to lowercase, and non-existent styles must return `(None, None, None)`.
- Extend `resolve_styles_for_tool` when introducing namespaced style semantics; maintain compatibility with `ImageStyle` enums. Template presets support groups like `styles:*` and `lightbox:*` for UI segmentation.
- `style_function_tool.custom_metadata` should mirror the underlying schema; update the declaration when changing arguments or return shapes so ADK reflection stays accurate.
