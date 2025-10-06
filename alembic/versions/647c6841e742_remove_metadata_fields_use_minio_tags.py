"""remove_metadata_fields_use_minio_tags

Revision ID: 647c6841e742
Revises: 01745f43dfd2
Create Date: 2025-10-05 20:38:35.110112

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '647c6841e742'
down_revision: Union[str, None] = '01745f43dfd2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema: remove metadata fields that are now stored in MinIO tags."""
    # Drop columns that are replaced by MinIO tagging
    op.drop_column('asset', 'style_subcategory')
    op.drop_column('asset', 'mime_type')
    op.drop_column('asset', 'file_size')
    op.drop_column('asset', 'filename')


def downgrade() -> None:
    """Downgrade database schema: restore metadata fields."""
    # Restore dropped columns
    op.add_column('asset', sa.Column('filename', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('asset', sa.Column('mime_type', sa.String(length=50), nullable=False, server_default='application/octet-stream'))
    op.add_column('asset', sa.Column('file_size', sa.Integer(), nullable=True))
    op.add_column('asset', sa.Column('style_subcategory', sa.String(length=50), nullable=True))
    
    # Remove server defaults after adding columns
    op.alter_column('asset', 'filename', server_default=None)
    op.alter_column('asset', 'mime_type', server_default=None)
