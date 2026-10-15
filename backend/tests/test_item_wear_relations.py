"""手改穿着次数 / 反查 / 常搭（fixes #43 #45 #46，Ruling 68–70）。"""
import json
from io import BytesIO
from uuid import uuid4

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

from app.models.item import ClothingItem, ItemStatus

RECORDS = "/api/v1/records"
ITEMS = "/api/v1/items"


def _jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 24), (10, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


async def _record(client, headers, item_ids, day: str):
    resp = await client.post(
        RECORDS,
        data={"data": json.dumps({"date": day, "item_ids": [str(i) for i in item_ids]})},
        files=[("photos", ("p.jpg", _jpeg(), "image/jpeg"))],
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _wear_count(db_session, item_id) -> int:
    return (
        await db_session.execute(
            select(ClothingItem.wear_count)
            .where(ClothingItem.id == item_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


@pytest_asyncio.fixture
async def wardrobe(db_session, test_user):
    out = {}
    for name, t in [("tee", "t-shirt"), ("jeans", "jeans"), ("shoes", "sneakers"), ("coat", "coat")]:
        item = ClothingItem(
            id=uuid4(), user_id=test_user.id, type=t, image_path=f"t/{name}.jpg",
            status=ItemStatus.ready, primary_colors=["black"], wear_count=0,
            wears_since_wash=0, needs_wash=False,
        )
        db_session.add(item)
        out[name] = item
    await db_session.commit()
    return out


@pytest.mark.asyncio
async def test_manual_wear_count_then_records_delta(client, auth_headers, db_session, wardrobe):
    tee = wardrobe["tee"]
    resp = await client.patch(f"{ITEMS}/{tee.id}", json={"wear_count": 5}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["wear_count"] == 5

    rec = await _record(client, auth_headers, [tee.id], "2026-10-01")
    assert await _wear_count(db_session, tee.id) == 6

    resp = await client.delete(f"{RECORDS}/{rec['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert await _wear_count(db_session, tee.id) == 5


@pytest.mark.asyncio
async def test_wear_count_rejects_negative_and_null(client, auth_headers, wardrobe):
    tee = wardrobe["tee"]
    assert (await client.patch(f"{ITEMS}/{tee.id}", json={"wear_count": -1}, headers=auth_headers)).status_code == 422
    assert (await client.patch(f"{ITEMS}/{tee.id}", json={"wear_count": None}, headers=auth_headers)).status_code == 422


@pytest.mark.asyncio
async def test_records_reverse_lookup_by_item(client, auth_headers, wardrobe):
    tee, jeans = wardrobe["tee"], wardrobe["jeans"]
    r1 = await _record(client, auth_headers, [tee.id, jeans.id], "2026-09-01")
    r2 = await _record(client, auth_headers, [tee.id], "2026-10-02")
    await _record(client, auth_headers, [jeans.id], "2026-10-03")

    resp = await client.get(RECORDS, params={"item_id": str(tee.id)}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["id"] for r in body["records"]] == [r2["id"], r1["id"]]
    assert body["total"] == 2

    page1 = (await client.get(RECORDS, params={"item_id": str(tee.id), "page_size": 1}, headers=auth_headers)).json()
    assert [r["id"] for r in page1["records"]] == [r2["id"]]
    assert page1["has_more"] is True


@pytest.mark.asyncio
async def test_companions_ranked_by_shared_records(client, auth_headers, db_session, wardrobe):
    tee, jeans, shoes, coat = (wardrobe[k] for k in ("tee", "jeans", "shoes", "coat"))
    await _record(client, auth_headers, [tee.id, jeans.id, shoes.id], "2026-10-01")
    await _record(client, auth_headers, [tee.id, jeans.id], "2026-10-02")
    await _record(client, auth_headers, [tee.id, coat.id], "2026-10-03")
    await _record(client, auth_headers, [jeans.id, coat.id], "2026-10-04")  # 不含 tee，不计

    coat.lifecycle = "retired"
    coat.is_archived = True
    await db_session.commit()

    resp = await client.get(f"{ITEMS}/{tee.id}/companions", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert rows[0]["id"] == str(jeans.id) and rows[0]["count"] == 2
    rest = {r["id"]: r for r in rows[1:]}
    assert set(rest) == {str(shoes.id), str(coat.id)}
    assert rest[str(coat.id)]["count"] == 1
    assert rest[str(coat.id)]["lifecycle"] == "retired"
    assert all(r["id"] != str(tee.id) for r in rows)

    limited = (await client.get(f"{ITEMS}/{tee.id}/companions", params={"limit": 1}, headers=auth_headers)).json()
    assert [r["id"] for r in limited] == [str(jeans.id)]


@pytest.mark.asyncio
async def test_companions_unknown_item_404(client, auth_headers):
    resp = await client.get(f"{ITEMS}/{uuid4()}/companions", headers=auth_headers)
    assert resp.status_code == 404
