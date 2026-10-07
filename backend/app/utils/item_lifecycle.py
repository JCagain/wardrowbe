"""Retired-boundary status lockstep (spec §5/§10.16).

A retired item's terminal status is archived — whatever the pipeline computed.
Lifecycle is authoritative; these helpers keep `status` from drifting out of
lockstep at every site that finishes a processing pass.
"""

from sqlalchemy import case, cast

from app.models.item import ClothingItem, ItemStatus


def terminal_status(lifecycle: str, desired: ItemStatus) -> ItemStatus:
    """Python-side write: the status a finishing pipeline may set."""
    return ItemStatus.archived if lifecycle == "retired" else desired


def terminal_status_case(desired: ItemStatus):
    """SQL-side write: the same rule as a Core update() values() expression.

    Cast to the column's enum type: a bare CASE infers text and asyncpg rejects
    it against the item_status column.
    """
    return cast(
        case((ClothingItem.lifecycle == "retired", ItemStatus.archived), else_=desired),
        ClothingItem.status.type,
    )
