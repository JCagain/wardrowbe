import json
from datetime import date
from io import BytesIO
from uuid import uuid4

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

from app.models.item import ClothingItem, ItemHistory, ItemStatus

BASE = "/api/v1/records"


def _jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 48), (200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


def _files(n: int = 1):
    return [("photos", (f"p{i}.jpg", _jpeg(), "image/jpeg")) for i in range(n)]


async def _create(client, headers, payload: dict, n_photos: int = 1):
    return await client.post(
        BASE, data={"data": json.dumps(payload)}, files=_files(n_photos), headers=headers
    )


@pytest_asyncio.fixture
async def items(db_session, test_user):
    out = []
    for t in ["t-shirt", "jeans", "sneakers"]:
        item = ClothingItem(
            id=uuid4(), user_id=test_user.id, type=t, image_path=f"t/{t}.jpg",
            status=ItemStatus.ready, primary_colors=["blue"], wear_count=0,
            wears_since_wash=0, needs_wash=False,
        )
        db_session.add(item)
        out.append(item)
    await db_session.commit()
    return out


async def _item(db_session, item_id) -> ClothingItem:
    return (
        await db_session.execute(
            select(ClothingItem).where(ClothingItem.id == item_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _history(db_session, item_id) -> list[ItemHistory]:
    return list(
        (await db_session.execute(select(ItemHistory).where(ItemHistory.item_id == item_id)))
        .scalars().all()
    )


@pytest.mark.asyncio
async def test_create_minimal_defaults_today_and_derived_season(client, auth_headers):
    r = await _create(client, auth_headers, {})
    assert r.status_code == 201, r.text
    body = r.json()
    today = date.today()  # test_user.timezone == "UTC"; 容器亦为 UTC
    assert body["date"] == today.isoformat()
    from app.utils.season import season_for_date
    assert body["season"] == season_for_date(today)
    assert body["city"] is None and body["weather"] is None
    assert body["occasion"] is None and body["notes"] is None
    assert body["items"] == []
    assert len(body["photos"]) == 1
    assert body["photos"][0]["thumbnail_url"]


@pytest.mark.asyncio
async def test_create_requires_photo(client, auth_headers):
    r = await client.post(BASE, data={"data": "{}"}, headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_with_items_counts_wear_and_writes_history(client, auth_headers, db_session, items):
    payload = {
        "date": "2026-10-01", "season": "summer", "city": "杭州",
        "weather": {"temp_high": 25, "temp_low": 18, "condition": "sunny"},
        "occasion": "casual", "notes": "国庆",
        "item_ids": [str(items[0].id), str(items[1].id)],
    }
    r = await _create(client, auth_headers, payload, n_photos=2)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["season"] == "summer"  # 手改胜过推导
    assert body["weather"] == {"temp_high": 25.0, "temp_low": 18.0, "condition": "sunny"}
    assert {i["id"] for i in body["items"]} == {str(items[0].id), str(items[1].id)}
    assert [p["position"] for p in body["photos"]] == [0, 1]

    shirt = await _item(db_session, items[0].id)
    assert shirt.wear_count == 1
    assert shirt.last_worn_at == date(2026, 10, 1)
    hist = await _history(db_session, items[0].id)
    assert len(hist) == 1 and str(hist[0].outfit_id) == body["id"]
    assert hist[0].worn_at == date(2026, 10, 1)


@pytest.mark.asyncio
async def test_duplicate_item_ids_counted_once(client, auth_headers, db_session, items):
    r = await _create(client, auth_headers, {"item_ids": [str(items[0].id)] * 2})
    assert r.status_code == 201
    assert (await _item(db_session, items[0].id)).wear_count == 1
    assert len(await _history(db_session, items[0].id)) == 1


@pytest.mark.asyncio
async def test_foreign_item_rejected(client, auth_headers):
    r = await _create(client, auth_headers, {"item_ids": [str(uuid4())]})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invalid_season_and_condition_rejected(client, auth_headers):
    assert (await _create(client, auth_headers, {"season": "all-season"})).status_code == 422
    assert (await _create(client, auth_headers, {"weather": {"condition": "hail"}})).status_code == 422


@pytest.mark.asyncio
async def test_patch_items_diff_only_changes_delta(client, auth_headers, db_session, items):
    shirt, jeans, shoes = items
    rid = (await _create(client, auth_headers, {"item_ids": [str(shirt.id), str(jeans.id)]})).json()["id"]

    r = await client.patch(
        f"{BASE}/{rid}", json={"item_ids": [str(jeans.id), str(shoes.id)]}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    assert (await _item(db_session, shirt.id)).wear_count == 0
    assert (await _item(db_session, jeans.id)).wear_count == 1   # 前后都在：不变
    assert (await _item(db_session, shoes.id)).wear_count == 1
    assert await _history(db_session, shirt.id) == []
    assert len(await _history(db_session, shoes.id)) == 1


@pytest.mark.asyncio
async def test_patch_to_zero_items_and_back(client, auth_headers, db_session, items):
    rid = (await _create(client, auth_headers, {"item_ids": [str(items[0].id)]})).json()["id"]
    await client.patch(f"{BASE}/{rid}", json={"item_ids": []}, headers=auth_headers)
    assert (await _item(db_session, items[0].id)).wear_count == 0
    r = await client.patch(f"{BASE}/{rid}", json={"item_ids": [str(items[0].id)]}, headers=auth_headers)
    assert r.json()["items"][0]["id"] == str(items[0].id)
    assert (await _item(db_session, items[0].id)).wear_count == 1


@pytest.mark.asyncio
async def test_patch_removing_only_record_item_clears_last_worn(client, auth_headers, db_session, items):
    rid = (await _create(client, auth_headers, {"date": "2026-10-01", "item_ids": [str(items[0].id)]})).json()["id"]
    assert (await _item(db_session, items[0].id)).last_worn_at == date(2026, 10, 1)
    r = await client.patch(f"{BASE}/{rid}", json={"item_ids": []}, headers=auth_headers)
    assert r.status_code == 200, r.text
    item = await _item(db_session, items[0].id)
    assert item.last_worn_at is None and item.wear_count == 0


@pytest.mark.asyncio
async def test_wear_count_never_negative(client, auth_headers, db_session, items):
    rid = (await _create(client, auth_headers, {"item_ids": [str(items[0].id)]})).json()["id"]
    item = await _item(db_session, items[0].id)
    item.wear_count = 0  # 模拟用户手改到 0（§4 计划的手改入口）
    await db_session.commit()
    await client.patch(f"{BASE}/{rid}", json={"item_ids": []}, headers=auth_headers)
    assert (await _item(db_session, items[0].id)).wear_count == 0


@pytest.mark.asyncio
async def test_patch_date_moves_history_and_last_worn(client, auth_headers, db_session, items):
    shirt = items[0]
    await _create(client, auth_headers, {"date": "2026-09-20", "item_ids": [str(shirt.id)]})
    rid = (await _create(client, auth_headers, {"date": "2026-10-10", "item_ids": [str(shirt.id)]})).json()["id"]
    assert (await _item(db_session, shirt.id)).last_worn_at == date(2026, 10, 10)

    r = await client.patch(f"{BASE}/{rid}", json={"date": "2026-09-01"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["season"] == "summer"  # 改日期未带季节 → 按新日期重推导（10-10 秋 → 09-01 夏）
    item = await _item(db_session, shirt.id)
    assert item.last_worn_at == date(2026, 9, 20)
    assert item.wear_count == 2
    worn = sorted(h.worn_at for h in await _history(db_session, shirt.id))
    assert worn == [date(2026, 9, 1), date(2026, 9, 20)]


@pytest.mark.asyncio
async def test_patch_date_with_explicit_season_keeps_it(client, auth_headers):
    rid = (await _create(client, auth_headers, {"date": "2026-10-10"})).json()["id"]
    r = await client.patch(
        f"{BASE}/{rid}", json={"date": "2026-07-01", "season": "spring"}, headers=auth_headers
    )
    assert r.json()["season"] == "spring"  # 同一请求里手给的季节胜过推导


@pytest.mark.asyncio
async def test_patch_other_fields_keep_manual_season(client, auth_headers):
    rid = (await _create(client, auth_headers, {"date": "2026-10-10", "season": "winter"})).json()["id"]
    r = await client.patch(f"{BASE}/{rid}", json={"notes": "x"}, headers=auth_headers)
    assert r.json()["season"] == "winter"  # 没改日期就不动季节


@pytest.mark.asyncio
async def test_patch_date_null_rejected(client, auth_headers):
    rid = (await _create(client, auth_headers, {})).json()["id"]
    r = await client.patch(f"{BASE}/{rid}", json={"date": None}, headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_weather_null_clears(client, auth_headers):
    rid = (await _create(client, auth_headers, {"weather": {"temp_high": 20}})).json()["id"]
    r = await client.patch(f"{BASE}/{rid}", json={"weather": None, "city": None}, headers=auth_headers)
    assert r.json()["weather"] is None and r.json()["city"] is None


@pytest.mark.asyncio
async def test_patch_occasion_syncs_history(client, auth_headers, db_session, items):
    rid = (await _create(client, auth_headers, {"item_ids": [str(items[0].id)]})).json()["id"]
    await client.patch(f"{BASE}/{rid}", json={"occasion": "office"}, headers=auth_headers)
    assert (await _history(db_session, items[0].id))[0].occasion == "office"


@pytest.mark.asyncio
async def test_delete_record_reverts_counts(client, auth_headers, db_session, items):
    rid = (await _create(client, auth_headers, {"item_ids": [str(items[0].id)]})).json()["id"]
    r = await client.delete(f"{BASE}/{rid}", headers=auth_headers)
    assert r.status_code == 204
    item = await _item(db_session, items[0].id)
    assert item.wear_count == 0 and item.last_worn_at is None
    assert await _history(db_session, items[0].id) == []
    assert (await client.get(f"{BASE}/{rid}", headers=auth_headers)).status_code == 404


@pytest.mark.asyncio
async def test_list_filters_by_date_and_orders_desc(client, auth_headers):
    for d in ["2026-09-01", "2026-10-05", "2026-10-01"]:
        await _create(client, auth_headers, {"date": d})
    r = await client.get(
        BASE, params={"date_from": "2026-10-01", "date_to": "2026-10-31"}, headers=auth_headers
    )
    body = r.json()
    assert [rec["date"] for rec in body["records"]] == ["2026-10-05", "2026-10-01"]
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_same_day_multiple_records_and_item_in_both(client, auth_headers, db_session, items):
    for _ in range(2):
        await _create(client, auth_headers, {"date": "2026-10-03", "item_ids": [str(items[0].id)]})
    assert (await _item(db_session, items[0].id)).wear_count == 2


@pytest.mark.asyncio
async def test_other_users_record_404(client, auth_headers, db_session):
    from app.models import User
    from app.api.auth import create_access_token

    other = User(id=uuid4(), external_id=f"o-{uuid4()}", email=f"o-{uuid4()}@x.com",
                 display_name="o", timezone="UTC", is_active=True)
    db_session.add(other)
    await db_session.commit()
    other_headers = {"Authorization": f"Bearer {create_access_token(other.external_id)}"}
    rid = (await _create(client, other_headers, {})).json()["id"]
    assert (await client.get(f"{BASE}/{rid}", headers=auth_headers)).status_code == 404
