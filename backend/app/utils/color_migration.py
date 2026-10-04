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
    "army-green": "army",
    "dark-brown": "coffee",
}

from app.utils.garment_vocabulary import BODY_PART_BY_TYPE, COLOR_VALUE_SET


def _normalize(value: str | None) -> str | None:
    """Map a legacy/AI color onto the vocabulary — or drop it.

    Policy (spec §1.4): alias first; if the result is not a vocabulary color
    the value is discarded rather than written through, so unknown slugs never
    reach the color columns.
    """
    if not value:
        return None
    value = value.strip().lower()
    value = LEGACY_COLOR_ALIASES.get(value, value)
    return value if value in COLOR_VALUE_SET else None


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
