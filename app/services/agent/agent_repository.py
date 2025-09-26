"""Agent repository helpers for the `agents` table."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session, select

from app.utils.models import AgentCreate, AgentUpdate, Agents


class AgentRepository:
    """Data access helpers for agent session records."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_session(
        self, *, app_name: str, session_id: str, user_id: UUID
    ) -> Agents | None:
        """Fetch a single agent session by composite identifiers."""
        query = (
            select(Agents)
            .where(Agents.app_name == app_name)
            .where(Agents.session_id == session_id)
            .where(Agents.user_id == user_id)
        )
        return self.session.exec(query).first()

    def list_for_user(
        self, *, user_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[Agents]:
        """Return recent agent sessions for a user ordered by recency."""
        query = (
            select(Agents)
            .where(Agents.user_id == user_id)
            .order_by(Agents.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.session.exec(query).all())

    def create(self, agent_create: AgentCreate) -> Agents:
        """Persist a new agent session record."""
        db_agent = Agents.model_validate(agent_create)
        self.session.add(db_agent)
        self.session.commit()
        self.session.refresh(db_agent)
        return db_agent

    def update(self, db_agent: Agents, agent_update: AgentUpdate) -> Agents:
        """Apply partial updates to an existing agent session."""
        data = agent_update.model_dump(exclude_unset=True)
        db_agent.sqlmodel_update(
            data,
            update={"updated_at": datetime.now(UTC)},
        )
        self.session.add(db_agent)
        self.session.commit()
        self.session.refresh(db_agent)
        return db_agent

    def bulk_update(
        self, records: Iterable[tuple[Agents, AgentUpdate]]
    ) -> list[Agents]:
        """Update multiple agent sessions in a single transaction."""
        updated: list[Agents] = []
        now = datetime.now(UTC)
        for db_agent, agent_update in records:
            data = agent_update.model_dump(exclude_unset=True)
            db_agent.sqlmodel_update(data, update={"updated_at": now})
            self.session.add(db_agent)
            updated.append(db_agent)

        if updated:
            self.session.commit()
            for db_agent in updated:
                self.session.refresh(db_agent)
        return updated
