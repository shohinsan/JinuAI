"""Health Check Routes
===================
Provides endpoints to monitor the application's liveness and readiness.

Endpoints:
- GET /liveness: Confirms the service is running.
- GET /readiness: Verifies the database connection is healthy.
"""

from fastapi import APIRouter, Response, status
from sqlmodel import text

from app.utils.delegate import SessionDep

router = APIRouter()


@router.get("/liveness", status_code=status.HTTP_204_NO_CONTENT)
def health_check() -> Response:
    """Ensure the service is running"""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/readiness", status_code=status.HTTP_204_NO_CONTENT)
def readiness_check(session: SessionDep) -> Response:
    """Ensure the service is ready to handle requests"""
    session.exec(text("SELECT 1"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
