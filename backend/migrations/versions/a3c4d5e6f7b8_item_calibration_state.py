"""clothing_items.calibration_state: D8 persisted calibration progress

Revision ID: a3c4d5e6f7b8
Revises: f2b3c4d5e6a7
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c4d5e6f7b8"
down_revision: str | None = "f2b3c4d5e6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clothing_items",
        sa.Column("calibration_state", sa.String(16), nullable=False, server_default="none"),
    )


def downgrade() -> None:
    op.drop_column("clothing_items", "calibration_state")
