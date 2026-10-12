"""add mask_path to clothing_items

Revision ID: f7d8e9a0b1c2
Revises: e6c3a9f7b4d2
Create Date: 2026-10-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7d8e9a0b1c2"
down_revision: str | None = "e6c3a9f7b4d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clothing_items",
        sa.Column("mask_path", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clothing_items", "mask_path")
