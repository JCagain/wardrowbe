from uuid import uuid4

import pytest

from app.models.item import ClothingItem, ItemStatus


@pytest.mark.asyncio
async def test_studio_create_without_occasion(client, auth_headers, db_session, test_user):
    item = ClothingItem(
        id=uuid4(), user_id=test_user.id, type="t-shirt", image_path="t/x.jpg",
        status=ItemStatus.ready, primary_colors=["blue"], wear_count=0,
        wears_since_wash=0, needs_wash=False,
    )
    db_session.add(item)
    await db_session.commit()

    r = await client.post(
        "/api/v1/outfits/studio",
        json={"items": [str(item.id)], "name": "无场合"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["occasion"] is None


@pytest.mark.asyncio
async def test_studio_create_invalid_occasion_still_rejected(client, auth_headers):
    r = await client.post(
        "/api/v1/outfits/studio",
        json={"items": [str(uuid4())], "occasion": "moon-landing"},
        headers=auth_headers,
    )
    assert r.status_code == 422
