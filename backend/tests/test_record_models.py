from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Outfit, OutfitPhoto, UserPreference
from app.models.outfit import OutfitSource, OutfitStatus


@pytest.mark.asyncio
async def test_record_outfit_with_city_and_photos(db_session, test_user):
    outfit = Outfit(
        id=uuid4(),
        user_id=test_user.id,
        source=OutfitSource.record,
        status=OutfitStatus.accepted,
        scheduled_for=date(2026, 10, 1),
        city="杭州",
    )
    db_session.add(outfit)
    await db_session.flush()
    db_session.add_all(
        [
            OutfitPhoto(outfit_id=outfit.id, position=1, image_path="u/b.jpg"),
            OutfitPhoto(outfit_id=outfit.id, position=0, image_path="u/a.jpg"),
        ]
    )
    await db_session.flush()

    loaded = (
        await db_session.execute(
            select(Outfit)
            .where(Outfit.id == outfit.id)
            .options(selectinload(Outfit.photos))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert loaded.source == OutfitSource.record
    assert loaded.city == "杭州"
    assert [p.image_path for p in loaded.photos] == ["u/a.jpg", "u/b.jpg"]


@pytest.mark.asyncio
async def test_preference_cities_default_null(db_session, test_user):
    pref = UserPreference(user_id=test_user.id)
    db_session.add(pref)
    await db_session.flush()
    await db_session.refresh(pref)
    assert pref.cities is None
    assert pref.default_city is None
