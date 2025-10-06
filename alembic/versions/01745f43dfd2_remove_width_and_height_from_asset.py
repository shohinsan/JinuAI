"""remove_width_and_height_from_asset

Revision ID: 01745f43dfd2
Revises: d72c3ae4052c
Create Date: 2025-10-05 20:32:36.621406

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '01745f43dfd2'
down_revision: Union[str, None] = 'd72c3ae4052c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Remove width and height columns from asset table
    op.drop_column('asset', 'width')
    op.drop_column('asset', 'height')


def downgrade() -> None:
    """Downgrade database schema."""
    # Re-add width and height columns to asset table
    op.add_column('asset', sa.Column('width', sa.Integer(), nullable=True))
    op.add_column('asset', sa.Column('height', sa.Integer(), nullable=True))
