"""outfit records: outfit_photos, outfits.city, record source, preference cities

Revision ID: d9e0f1a2b3c4
Revises: f7d8e9a0b1c2
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "f7d8e9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PG ≥ 12 允许在事务内 ADD VALUE（同一事务内不使用新值即可）。
    op.execute("ALTER TYPE outfit_source ADD VALUE IF NOT EXISTS 'record'")

    op.add_column("outfits", sa.Column("city", sa.String(50), nullable=True))

    op.create_table(
        "outfit_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "outfit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outfits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_path", sa.String(500), nullable=False),
        sa.Column("medium_path", sa.String(500), nullable=True),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_outfit_photos_outfit_id", "outfit_photos", ["outfit_id"])

    op.add_column(
        "user_preferences",
        sa.Column("cities", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "user_preferences",
        sa.Column("default_city", sa.String(50), nullable=True),
    )

    # 反查 / 改关联按 outfit_id 删改 item_history。
    op.create_index("ix_item_history_outfit_id", "item_history", ["outfit_id"])


def downgrade() -> None:
    op.drop_index("ix_item_history_outfit_id", table_name="item_history")
    op.drop_column("user_preferences", "default_city")
    op.drop_column("user_preferences", "cities")
    op.drop_index("ix_outfit_photos_outfit_id", table_name="outfit_photos")
    op.drop_table("outfit_photos")
    op.drop_column("outfits", "city")
    # PG 不支持删除 enum 值；'record' 留在 outfit_source 里无害。
