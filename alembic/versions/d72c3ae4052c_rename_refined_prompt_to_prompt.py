"""rename_refined_prompt_to_prompt

Revision ID: d72c3ae4052c
Revises: e2a1af2c63a1
Create Date: 2025-10-05 20:26:58.939245

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd72c3ae4052c'
down_revision: Union[str, None] = 'e2a1af2c63a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Rename refined_prompt column to prompt in asset table
    op.alter_column('asset', 'refined_prompt', new_column_name='prompt')


def downgrade() -> None:
    """Downgrade database schema."""
    # Rename prompt column back to refined_prompt in asset table
    op.alter_column('asset', 'prompt', new_column_name='refined_prompt')
