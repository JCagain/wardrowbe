"""Legacy vocabulary mapping kept in one place (AI parsing + DB migration)."""
from __future__ import annotations

LEGACY_COLOR_ALIASES = {
    "burgundy": "wine",
    "light-blue": "sky",
    "tan": "camel",
    "beige": "khaki",
    "charcoal": "dark-gray",
    "teal": "klein",
    "mustard": "ginger",
    "lavender": "taro",
    "chocolate": "coffee",
}

from app.utils.garment_vocabulary import BODY_PART_BY_TYPE


def _normalize(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return LEGACY_COLOR_ALIASES.get(value, value)


def migrate_legacy_colors(
    primary_color: str | None, colors: list[str] | None
) -> tuple[list[str], list[str]]:
    primary = _normalize(primary_color)
    primary_list = [primary] if primary else []
    secondary: list[str] = []
    for raw in colors or []:
        value = _normalize(raw)
        if value and value not in primary_list and value not in secondary:
            secondary.append(value)
    return primary_list, secondary


def body_part_case_sql(type_column: str) -> str:
    branches = " ".join(
        f"WHEN {type_column} = '{value}' THEN '{part}'"
        for value, part in sorted(BODY_PART_BY_TYPE.items())
    )
    return f"CASE {branches} ELSE NULL END"
