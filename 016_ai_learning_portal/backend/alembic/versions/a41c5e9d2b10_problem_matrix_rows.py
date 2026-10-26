"""problem matrix rows

Revision ID: a41c5e9d2b10
Revises: 7ce72e64d310
Create Date: 2026-10-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a41c5e9d2b10'
down_revision: Union[str, Sequence[str], None] = '7ce72e64d310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add as nullable, fill existing rows with an empty list, then make it NOT NULL
    # (MySQL JSON columns cannot have a literal default)
    op.add_column('problems', sa.Column('matrix_rows', sa.JSON(), nullable=True))
    op.execute("UPDATE problems SET matrix_rows = JSON_ARRAY() WHERE matrix_rows IS NULL")
    op.alter_column('problems', 'matrix_rows', existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('problems', 'matrix_rows')
