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

# The garment_vocabulary import is deliberately function-local below: alembic
# loads every revision script (and this module with it) at startup, and the
# vocabulary file is runtime-mutable — a corrupted or missing JSON must never
# take the migration chain down. Migrations pass frozen snapshots and never
# touch the defaults.


def _normalize(value: str | None, valid: set[str]) -> str | None:
    """Map a legacy/AI color onto the vocabulary — or drop it.

    Policy (spec §1.4): a direct vocabulary hit always wins (a live color must
    never be alias-rewritten — "lavender" is both a live color and a legacy
    alias for "taro"), then the alias table; what is still outside the
    vocabulary is discarded rather than written through.
    """
    if not value:
        return None
    value = value.strip().lower()
    if value in valid:
        return value
    value = LEGACY_COLOR_ALIASES.get(value, value)
    return value if value in valid else None


def migrate_legacy_colors(
    primary_color: str | None,
    colors: list[str] | None,
    valid: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Split/normalize the legacy (primary_color, colors) shape.

    `valid` defaults to the live vocabulary; the DB data migration passes a
    frozen snapshot so re-runs stay reproducible.
    """
    if valid is None:
        from app.utils.garment_vocabulary import COLOR_VALUE_SET

        valid = COLOR_VALUE_SET
    primary = _normalize(primary_color, valid)
    primary_list = [primary] if primary else []
    secondary: list[str] = []
    for raw in colors or []:
        value = _normalize(raw, valid)
        if value and value not in primary_list and value not in secondary:
            secondary.append(value)
    return primary_list, secondary


def body_part_case_sql(type_column: str, mapping: dict[str, str] | None = None) -> str:
    """CASE expression mapping a type column onto body_part slugs.

    `mapping` defaults to the live vocabulary; the DB data migration passes a
    frozen snapshot so re-runs stay reproducible. `type_column` is a
    code-provided identifier; mapping values are quoted with doubled single
    quotes so runtime-vocabulary slugs can never break out of the literal
    (same rule as `_array_literal`).
    """
    if mapping is None:
        from app.utils.garment_vocabulary import BODY_PART_BY_TYPE

        mapping = BODY_PART_BY_TYPE
    branches = " ".join(
        "WHEN {col} = '{value}' THEN '{part}'".format(
            col=type_column,
            value=value.replace("'", "''"),
            part=part.replace("'", "''"),
        )
        for value, part in sorted(mapping.items())
    )
    return f"CASE {branches} ELSE NULL END"
