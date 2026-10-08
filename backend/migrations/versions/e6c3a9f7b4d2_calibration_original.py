"""add calibration_original_path to clothing_items

Revision ID: e6c3a9f7b4d2
Revises: a3c5e7f9b1d2
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6c3a9f7b4d2"
down_revision: str | None = "a3c5e7f9b1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clothing_items",
        sa.Column("calibration_original_path", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clothing_items", "calibration_original_path")
