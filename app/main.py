"""Application Factory
===================
Initializes the FastAPI application with routes, middleware, exception handlers,
and third-party integrations like Sentry and Logfire.
"""

import logfire
import sentry_sdk
import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routes import auth, health, user, agent
from app.utils.config import settings
from app.utils.exceptions import (
    http_validation_error,
    request_validation_error,
    validation_error,
)


def create_app() -> FastAPI:
    init_sentry()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        generate_unique_id_function=custom_generate_unique_id,
    )

    app.add_exception_handler(StarletteHTTPException, http_validation_error)
    app.add_exception_handler(RequestValidationError, request_validation_error)
    app.add_exception_handler(ValidationError, validation_error)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(create_api_router(), prefix=settings.API_V1_STR)

    init_logfire(app)

    return app


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


def init_sentry() -> None:
    if settings.SENTRY_DSN and settings.ENVIRONMENT != "development":
        sentry_sdk.init(
            dsn=str(settings.SENTRY_DSN),
            enable_tracing=True,
        )


def init_logfire(app: FastAPI) -> None:
    if settings.LOGFIRE_TOKEN and settings.ENVIRONMENT not in ["local", "development"]:
        try:
            logfire.configure()
            logfire.instrument_fastapi(app)
        except Exception as e:
            print(f"Warning: Failed to initialize Logfire: {e}")


def create_api_router() -> APIRouter:
    router = APIRouter()

    router.include_router(health.router, prefix="/health", tags=["health"])
    router.include_router(auth.router, prefix="/auth", tags=["auth"])
    router.include_router(user.router, prefix="/user", tags=["user"])
    router.include_router(agent.router, prefix="/agent", tags=["agent"])

    return router


if __name__ == "__main__":
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
