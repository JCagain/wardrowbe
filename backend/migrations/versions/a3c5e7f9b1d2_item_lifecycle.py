"""item lifecycle status: active/idle/retired

Revision ID: a3c5e7f9b1d2
Revises: e7f8a9b0c1d2
Create Date: 2026-10-04

The boolean is_archived becomes the compatibility view of a three-state
lifecycle (spec §5/§10.16). Existing rows map True→retired, False→active.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e7f9b1d2"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIFECYCLE = sa.Enum("active", "idle", "retired", name="item_lifecycle")


def upgrade() -> None:
    LIFECYCLE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "clothing_items",
        sa.Column("lifecycle", LIFECYCLE, nullable=False, server_default="active"),
    )
    op.execute("UPDATE clothing_items SET lifecycle = 'retired' WHERE is_archived = TRUE")


def downgrade() -> None:
    op.drop_column("clothing_items", "lifecycle")
    LIFECYCLE.drop(op.get_bind(), checkfirst=True)
