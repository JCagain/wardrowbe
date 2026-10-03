"""personal wardrobe fields: body_part, primary/secondary colors, temp bounds

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-10-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.utils.color_migration import body_part_case_sql

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _array_literal(values: list[str]) -> str:
    """Render a Python str list as a postgres ARRAY literal.

    asyncpg cannot bind Python lists through text() without a typed bindparam,
    so the data migration inlines literals instead (authorized fallback). Only
    slugs reach here, but quote them properly anyway.
    """
    if not values:
        return "ARRAY[]::varchar[]"
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return f"ARRAY[{quoted}]::varchar[]"


def upgrade() -> None:
    op.add_column("clothing_items", sa.Column("body_part", sa.String(50), nullable=True))
    op.add_column(
        "clothing_items",
        sa.Column("primary_colors", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "clothing_items",
        sa.Column("secondary_colors", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.add_column("clothing_items", sa.Column("temp_low", sa.Float(), nullable=True))
    op.add_column("clothing_items", sa.Column("temp_high", sa.Float(), nullable=True))
    op.add_column(
        "clothing_items", sa.Column("purchase_date_precision", sa.String(8), nullable=True)
    )

    # 旧颜色数据 -> 新数组：主色进 primary_colors，其余去重进 secondary_colors。
    # 别名归一由 Python 端逐行处理（值域小，行数 < 1000）。
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, type, primary_color, colors FROM clothing_items")
    ).fetchall()
    from app.utils.color_migration import migrate_legacy_colors

    for row in rows:
        primary_list, secondary_list = migrate_legacy_colors(row.primary_color, row.colors)
        conn.execute(
            sa.text(
                "UPDATE clothing_items SET body_part = "
                + body_part_case_sql("type")
                + ", primary_colors = "
                + _array_literal(primary_list)
                + ", secondary_colors = "
                + _array_literal(secondary_list)
                + " WHERE id = :id"
            ),
            {"id": row.id},
        )
    # 老行 type 映射不到 body_part 的兜底：全表再刷一次 CASE（新行由应用层写入）。
    op.execute(
        sa.text(
            "UPDATE clothing_items SET body_part = "
            + body_part_case_sql("type")
            + " WHERE body_part IS NULL"
        )
    )

    op.alter_column("outfits", "occasion", existing_type=sa.String(50), nullable=True)
    op.drop_column("clothing_items", "primary_color")
    op.drop_column("clothing_items", "colors")


def downgrade() -> None:
    op.add_column(
        "clothing_items",
        sa.Column("colors", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "clothing_items",
        sa.Column("primary_color", sa.String(50), nullable=True)
    )
    op.execute(
        sa.text(
            "UPDATE clothing_items SET primary_color = primary_colors[1], "
            "colors = primary_colors || secondary_colors"
        )
    )
    op.alter_column("outfits", "occasion", existing_type=sa.String(50), nullable=False)
    op.drop_column("clothing_items", "purchase_date_precision")
    op.drop_column("clothing_items", "temp_high")
    op.drop_column("clothing_items", "temp_low")
    op.drop_column("clothing_items", "secondary_colors")
    op.drop_column("clothing_items", "primary_colors")
    op.drop_column("clothing_items", "body_part")
