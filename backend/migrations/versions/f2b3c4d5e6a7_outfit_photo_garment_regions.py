"""outfit_photos.garment_regions: D7 garment boxes on outfit photos

Revision ID: f2b3c4d5e6a7
Revises: e1a2b3c4d5f6
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2b3c4d5e6a7"
down_revision: str | None = "e1a2b3c4d5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("outfit_photos", sa.Column("garment_regions", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("outfit_photos", "garment_regions")
