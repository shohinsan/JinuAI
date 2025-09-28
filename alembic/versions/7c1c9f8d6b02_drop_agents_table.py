"""Drop agents table

Revision ID: 7c1c9f8d6b02
Revises: 49fd23a3918f
Create Date: 2025-09-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "7c1c9f8d6b02"
down_revision: Union[str, None] = "49fd23a3918f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


agent_status_enum = postgresql.ENUM(
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    name="agentstatus",
)


def upgrade() -> None:
    """Upgrade database schema."""
    op.drop_table("agents")
    agent_status_enum.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """Downgrade database schema."""
    agent_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "app_name",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column(
            "agent",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "title",
            sqlmodel.sql.sqltypes.AutoString(length=200),
            nullable=True,
        ),
        sa.Column("status", agent_status_enum, nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agents_agent"), "agents", ["agent"], unique=False)
    op.create_index(op.f("ix_agents_app_name"), "agents", ["app_name"], unique=False)
    op.create_index(op.f("ix_agents_session_id"), "agents", ["session_id"], unique=False)
    op.create_index(op.f("ix_agents_status"), "agents", ["status"], unique=False)
    op.create_index(op.f("ix_agents_user_id"), "agents", ["user_id"], unique=False)
