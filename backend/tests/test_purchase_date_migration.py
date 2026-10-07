"""Legacy purchase_date rows must be normalized at migration time.

The old schema stored a plain Date (users entered full days). The new wire
format is year-month only, so the day is dropped — the migration must do that
once, deterministically, and record the loss in purchase_date_precision,
instead of the first unrelated save silently rewriting the row.
"""
import importlib.util
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _migration_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "e7f8a9b0c1d2_personal_wardrobe_fields.py"
    )
    spec = importlib.util.spec_from_file_location("e7f8a9b0c1d2_normalize_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_legacy_full_dates_come_out_as_day_one_with_marker(db_session: AsyncSession, test_user):
    from app.models.item import ClothingItem

    item = ClothingItem(
        id=uuid4(), user_id=test_user.id, type="shirt", image_path="t.jpg",
        purchase_date=date(2024, 3, 15),  # legacy full date, no marker
    )
    db_session.add(item)
    await db_session.flush()

    module = _migration_module()
    await db_session.execute(text(module.NORMALIZE_PURCHASE_DATE_SQL))
    await db_session.flush()
    await db_session.refresh(item)

    assert item.purchase_date == date(2024, 3, 1)
    assert item.purchase_date_precision == "month"


@pytest.mark.asyncio
async def test_rows_with_marker_are_untouched(db_session: AsyncSession, test_user):
    from app.models.item import ClothingItem

    item = ClothingItem(
        id=uuid4(), user_id=test_user.id, type="shirt", image_path="t.jpg",
        purchase_date=date(2024, 1, 1), purchase_date_precision="year",
    )
    db_session.add(item)
    await db_session.flush()

    module = _migration_module()
    await db_session.execute(text(module.NORMALIZE_PURCHASE_DATE_SQL))
    await db_session.flush()
    await db_session.refresh(item)

    assert item.purchase_date == date(2024, 1, 1)
    assert item.purchase_date_precision == "year"


def test_migration_ships_the_normalization_in_its_own_contents():
    # Reproducibility rule: the migration carries the statement itself, with
    # no runtime-vocabulary or app-side repair dependency.
    module = _migration_module()
    assert hasattr(module, "NORMALIZE_PURCHASE_DATE_SQL")
    assert "date_trunc('month', purchase_date)" in module.NORMALIZE_PURCHASE_DATE_SQL
    assert "purchase_date_precision = 'month'" in module.NORMALIZE_PURCHASE_DATE_SQL
