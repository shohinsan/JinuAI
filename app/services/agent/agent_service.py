"""Agent service orchestrating session persistence."""

from __future__ import annotations

from uuid import UUID

from app.services.agent.agent_repository import AgentRepository
from app.utils.models import AgentCreate, AgentUpdate, Agents, ImageStatus


class AgentService:
    """Coordinate persistence of agent session records."""

    def __init__(self, repository: AgentRepository):
        self.repository = repository

    def ensure_session(
        self,
        *,
        app_name: str,
        agent_name: str,
        session_id: str,
        user_id: UUID,
        title: str | None = None,
        status: ImageStatus | None = None,
    ) -> Agents:
        """Return an agent session record, creating it when needed."""
        existing = self.repository.get_by_session(
            app_name=app_name,
            session_id=session_id,
            user_id=user_id,
        )

        if existing:
            updates: dict[str, object] = {}
            if title is not None and title != existing.title:
                updates["title"] = title
            if status and status != existing.status:
                updates["status"] = status

            if updates:
                update_payload = AgentUpdate(**updates)
                return self.repository.update(existing, update_payload)
            return existing

        create_payload = AgentCreate(
            app_name=app_name,
            agent=agent_name,
            session_id=session_id,
            user_id=user_id,
            title=title,
            status=status or ImageStatus.PENDING,
            turn_count=0,
        )
        return self.repository.create(create_payload)

    def start_turn(
        self,
        *,
        app_name: str,
        agent_name: str,
        session_id: str,
        user_id: UUID,
        title: str | None = None,
    ) -> Agents:
        """Increment the turn count and mark the session as processing."""
        record = self.ensure_session(
            app_name=app_name,
            agent_name=agent_name,
            session_id=session_id,
            user_id=user_id,
            title=title,
        )

        update_kwargs: dict[str, object] = {
            "status": ImageStatus.PROCESSING,
            "turn_count": record.turn_count + 1,
        }
        if title is not None and title != record.title:
            update_kwargs["title"] = title

        update_payload = AgentUpdate(**update_kwargs)
        return self.repository.update(record, update_payload)

    def finish_turn(
        self,
        *,
        app_name: str,
        agent_name: str,
        session_id: str,
        user_id: UUID,
        status: ImageStatus = ImageStatus.COMPLETED,
        title: str | None = None,
    ) -> Agents:
        """Mark the current turn as completed (or failed)."""
        record = self.ensure_session(
            app_name=app_name,
            agent_name=agent_name,
            session_id=session_id,
            user_id=user_id,
            title=title,
        )

        update_kwargs: dict[str, object] = {"status": status}
        if title is not None and title != record.title:
            update_kwargs["title"] = title

        update_payload = AgentUpdate(**update_kwargs)
        return self.repository.update(record, update_payload)

    def list_sessions(
        self,
        *,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Agents]:
        """Return recent sessions for UI listings."""
        return self.repository.list_for_user(user_id=user_id, skip=skip, limit=limit)
