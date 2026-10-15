"""GET /items 与批量全选的筛选口径（fixes #40/#41，Ruling 66/67）。"""
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import items as items_api
from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.schemas.item import BulkFilters, BulkSelectionRequest
from app.services.item_service import ItemService
from app.utils import garment_vocabulary as gv

BASE = "/api/v1/items"


def _item(user_id, **kw) -> ClothingItem:
    kw.setdefault("type", "t-shirt")
    kw.setdefault("status", ItemStatus.ready)
    kw.setdefault("primary_colors", ["black"])
    return ClothingItem(id=uuid4(), user_id=user_id, image_path=f"t/{uuid4()}.jpg", **kw)


async def _ids(client, headers, **params) -> set:
    resp = await client.get(BASE, params={"page_size": 100, **params}, headers=headers)
    assert resp.status_code == 200, resp.text
    return {i["id"] for i in resp.json()["items"]}


@pytest.mark.asyncio
async def test_colors_match_primary_only(client: AsyncClient, auth_headers, db_session: AsyncSession, test_user: User):
    a = _item(test_user.id, primary_colors=["red"])
    b = _item(test_user.id, primary_colors=["black"], secondary_colors=["red"])
    db_session.add_all([a, b])
    await db_session.commit()
    assert await _ids(client, auth_headers, colors="red") == {str(a.id)}


@pytest.mark.asyncio
async def test_color_scope_secondary_and_any(client, auth_headers, db_session, test_user):
    prim = _item(test_user.id, primary_colors=["wine"])
    sec = _item(test_user.id, primary_colors=["black"], secondary_colors=["wine"])
    db_session.add_all([prim, sec])
    await db_session.commit()
    assert await _ids(client, auth_headers, colors="wine", color_scope="secondary") == {str(sec.id)}
    assert await _ids(client, auth_headers, colors="wine", color_scope="any") == {str(prim.id), str(sec.id)}
    assert await _ids(client, auth_headers, color_family="red", color_scope="secondary") == {str(sec.id)}
    assert await _ids(client, auth_headers, color_family="red", color_scope="any") == {str(prim.id), str(sec.id)}
    resp = await client.get(BASE, params={"color_scope": "both"}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_color_family_expands_to_its_colors(client, auth_headers, db_session, test_user):
    a = _item(test_user.id, primary_colors=["wine"])
    b = _item(test_user.id, primary_colors=["blue"], secondary_colors=["wine"])
    db_session.add_all([a, b])
    await db_session.commit()
    assert await _ids(client, auth_headers, color_family="red") == {str(a.id)}
    assert await _ids(client, auth_headers, color_family="no-such-family") == set()


@pytest.mark.asyncio
async def test_color_family_includes_disabled_colors(client, auth_headers, db_session, test_user, monkeypatch):
    data = gv._data()
    patched = {**data, "colors": {**data["colors"], "values": [
        {**c, "disabled": True} if c["value"] == "wine" else c for c in data["colors"]["values"]
    ]}}
    monkeypatch.setattr(gv, "_data", lambda: patched)
    a = _item(test_user.id, primary_colors=["wine"])
    db_session.add(a)
    await db_session.commit()
    assert await _ids(client, auth_headers, color_family="red") == {str(a.id)}


@pytest.mark.asyncio
async def test_body_part_derives_from_type_when_null(client, auth_headers, db_session, test_user):
    jeans_null = _item(test_user.id, type="jeans", body_part=None)
    tee_tops = _item(test_user.id, type="t-shirt", body_part="tops")
    tee_null = _item(test_user.id, type="t-shirt", body_part=None)
    db_session.add_all([jeans_null, tee_tops, tee_null])
    await db_session.commit()
    assert await _ids(client, auth_headers, body_part="bottoms") == {str(jeans_null.id)}
    assert await _ids(client, auth_headers, body_part="tops") == {str(tee_tops.id), str(tee_null.id)}


@pytest.mark.asyncio
async def test_style_filter(client, auth_headers, db_session, test_user):
    a = _item(test_user.id, style=["goth", "retro"])
    b = _item(test_user.id, style=["casual"])
    db_session.add_all([a, b])
    await db_session.commit()
    assert await _ids(client, auth_headers, style="goth") == {str(a.id)}


@pytest.mark.asyncio
async def test_season_matches_all_season_too(client, auth_headers, db_session, test_user):
    summer = _item(test_user.id, season=["summer"])
    allseason = _item(test_user.id, season=["all-season"])
    winter = _item(test_user.id, season=["winter"])
    db_session.add_all([summer, allseason, winter])
    await db_session.commit()
    assert await _ids(client, auth_headers, season="summer") == {str(summer.id), str(allseason.id)}
    assert await _ids(client, auth_headers, season="all-season") == {str(allseason.id)}


@pytest.mark.asyncio
async def test_filters_combine_with_and(client, auth_headers, db_session, test_user):
    hit = _item(test_user.id, type="jeans", primary_colors=["navy"], season=["fall"])
    wrong_color = _item(test_user.id, type="jeans", primary_colors=["black"], season=["fall"])
    db_session.add_all([hit, wrong_color])
    await db_session.commit()
    got = await _ids(client, auth_headers, body_part="bottoms", color_family="blue", season="fall")
    assert got == {str(hit.id)}


@pytest.mark.asyncio
async def test_bulk_select_all_honors_vocab_filters(db_session, test_user):
    hit = _item(test_user.id, primary_colors=["wine"], style=["goth"], season=["winter"])
    miss_style = _item(test_user.id, primary_colors=["wine"], style=["casual"], season=["winter"])
    miss_family = _item(test_user.id, primary_colors=["blue"], style=["goth"], season=["winter"])
    db_session.add_all([hit, miss_style, miss_family])
    await db_session.commit()
    request = BulkSelectionRequest(
        select_all=True,
        filters=BulkFilters(color_family="red", style="goth", season="winter"),
    )
    ids, _cursor, has_more = await items_api._resolve_bulk_item_ids(
        ItemService(db_session), test_user.id, request, "test"
    )
    assert ids == [hit.id]
    assert has_more is False


@pytest.mark.asyncio
async def test_bulk_select_all_specific_color_is_primary_only(db_session, test_user):
    a = _item(test_user.id, primary_colors=["red"])
    b = _item(test_user.id, primary_colors=["black"], secondary_colors=["red"])
    db_session.add_all([a, b])
    await db_session.commit()
    request = BulkSelectionRequest(select_all=True, filters=BulkFilters(colors=["red"]))
    ids, _, _ = await items_api._resolve_bulk_item_ids(ItemService(db_session), test_user.id, request, "test")
    assert ids == [a.id]


@pytest.mark.asyncio
async def test_bulk_select_all_secondary_scope(db_session, test_user):
    a = _item(test_user.id, primary_colors=["red"])
    b = _item(test_user.id, primary_colors=["black"], secondary_colors=["red"])
    db_session.add_all([a, b])
    await db_session.commit()
    request = BulkSelectionRequest(
        select_all=True, filters=BulkFilters(colors=["red"], color_scope="secondary")
    )
    ids, _, _ = await items_api._resolve_bulk_item_ids(ItemService(db_session), test_user.id, request, "test")
    assert ids == [b.id]
