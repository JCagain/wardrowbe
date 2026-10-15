"""item_embeddings: archive-side vectors for AI-suggested linking

Revision ID: e1a2b3c4d5f6
Revises: d9e0f1a2b3c4
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1a2b3c4d5f6"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "item_embeddings",
        sa.Column("item_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clothing_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("source_fingerprint", sa.String(1200), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", postgresql.ARRAY(sa.REAL()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("item_embeddings")
