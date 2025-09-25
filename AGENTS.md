# Project Guide for Agents

## What This Service Does
- FastAPI backend that orchestrates an image-generation workflow around Google "Nano Banana" (Gemini) models.
- Routes live under `app/routes`; the `/agent` endpoints collect user uploads and metadata, generate refined prompts, and return base64 images.
- Prompt refinement uses the Google ADK agent runner: `app/utils/agent_orchestration.py` wires specialist agents on top of an OpenAI-compatible adapter backed by Ollama.
- Final image synthesis calls Google GenAI directly; generated binaries are persisted to `generated-img/` for inspection.

## Getting A Local Environment Running
- Requires Python 3.11 and Poetry; install deps with `poetry install` from the repo root.
- Copy or create `.env` and provide the mandatory keys from `app/utils/config.py` (`POSTGRES_*`, `GOOGLE_API_KEY`, `SECRET_KEY`, etc.). Never commit real credentials.
- Start dependencies (Postgres, Redis if caching is enabled) before running the API. Docker compose is not bundled, so launch your own services or use a local stack.
- Boot the API with `poetry run uvicorn app.main:create_app --factory --reload`. The OpenAPI docs live at `/api/v1/openapi.json`.

## Working With Data And Schemas
- SQLModel is used for ORM models while migrations are managed by Alembic. Follow `alembic/CLAUDE.md` for end-to-end migration rules, including required imports and verification steps.
- Any schema change must be reflected in both the SQLModel definitions (usually under `app/services` or `app/utils/models.py`) and an Alembic migration. Keep upgrade/downgrade paths symmetrical.
- Run `poetry run alembic upgrade head` to sync your database, and roll back with `poetry run alembic downgrade -1` during testing.

## LLM And Agent-Oriented Code
- The entry point for new LLM adapters is `app/llm/`; `openai_llm.py` demonstrates how to wrap an OpenAI-compatible endpoint behind the `BaseLlm` interface.
- Agent definitions live in `app/utils/agent_orchestration.py`. Each agent should output a `refined_prompt` and remain free of conversational prose. Keep instructions terse and deterministic.
- Guardrails (`app/utils/agent_guardrail.py`) are executed before the primary agent model; extend these when adding new validation logic.
- When integrating a Claude endpoint, supply an OpenAI-compatible surface (e.g., Anthropic Messages API via a proxy) or implement a new adapter mirroring `OpenAIChatLlm`. Ensure streaming is either implemented or explicitly unsupported, as in the current adapter.

## Image Generation Pipeline
- Uploaded files are normalized in `prepare_upload_payloads`; any preprocessing (resizing, format enforcement) should happen there.
- Prompt refinement results and session state are stored via `settings.GOOGLE_BANANA_MODEL_SESSION`, an in-memory service. Replace with a durable backend (Redis, Firestore) before production if persistence is required.
- `generate_image_bytes` sends prompt plus media to `settings.FLASH_IMAGE`. Update the model constant in `app/utils/config.py` if the target image model changes.
- Returned images are written to `generated-img/` and included in the API response as base64 data URIs. Consider offloading large outputs to object storage for production deployments.

## Quality Gates Before You Ship
- Lint: `poetry run ruff check .`
- Type check: `poetry run mypy app`
- Tests: `poetry run pytest`
- Keep changes ASCII-only unless the surrounding file already uses extended characters. Prefer descriptive unit tests near affected modules.
- Document new endpoints or workflows in `README.md` if they affect external consumers.

## Operational Hints
- Observability hooks (Sentry, Logfire, OpenTelemetry) only initialize when their environment variables are present and the environment is not local. Configure them in staging before enabling in production.
- CORS defaults to `*` but is governed by `BACKEND_CORS_ORIGINS` and `FRONTEND_HOST`. Update these values when you deploy to new domains.
- Redis caching is optional; keep the URL in sync across `.env`, infrastructure, and deployment manifests.
- For CI/CD, ensure migrations run before application containers start to avoid schema drift.

## Where To Put Future Instructions
- Keep cross-cutting guidance here at the repo root. Folder-specific playbooks (for example, migrations) belong in their respective directories alongside a dedicated `CLAUDE.md`.
- Update this document whenever you add major components so Claude (and other collaborators) persistently understand the project topology.
