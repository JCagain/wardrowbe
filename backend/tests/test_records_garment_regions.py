import json
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from app.services.ai_service import AIService

BASE = "/api/v1/records"


def _jpeg(size=(200, 100)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


async def _record(client, headers):
    resp = await client.post(
        BASE,
        data={"data": json.dumps({"date": "2026-10-01"})},
        files=[("photos", ("p.jpg", _jpeg(), "image/jpeg"))],
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["id"], body["photos"][0]["id"]


@pytest.fixture
async def other_auth_headers(db_session):
    from app.api.auth import create_access_token
    from app.models import User

    other = User(id=uuid4(), external_id=f"o-{uuid4()}", email=f"o-{uuid4()}@x.com",
                 display_name="o", timezone="UTC", is_active=True)
    db_session.add(other)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(other.external_id)}"}


@pytest.fixture
def stub_detect(monkeypatch):
    calls = {}

    async def fake(self, image_path):
        calls["endpoints"] = [e.name for e in self._endpoints]
        return '{"regions": [{"body_part": "tops", "box": [0, 0, 500, 500]}]}'

    monkeypatch.setattr(AIService, "detect_garment_regions", fake)
    return calls


@pytest.mark.asyncio
async def test_detect_saves_and_returns_pixel_boxes(client, auth_headers, stub_detect):
    rid, pid = await _record(client, auth_headers)
    resp = await client.post(f"{BASE}/{rid}/photos/{pid}/garment-regions/detect", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["width"], body["height"]) == (200, 100)
    assert body["regions"] == [{"body_part": "tops", "box": {"l": 0, "t": 0, "r": 99, "b": 49}, "source": "auto"}]
    rec = (await client.get(f"{BASE}/{rid}", headers=auth_headers)).json()
    assert rec["photos"][0]["garment_regions"] == body["regions"]


@pytest.mark.asyncio
async def test_detect_unparseable_is_502_and_not_saved(client, auth_headers, monkeypatch):
    async def fake(self, image_path):
        return "sorry"

    monkeypatch.setattr(AIService, "detect_garment_regions", fake)
    rid, pid = await _record(client, auth_headers)
    resp = await client.post(f"{BASE}/{rid}/photos/{pid}/garment-regions/detect", headers=auth_headers)
    assert resp.status_code == 502
    rec = (await client.get(f"{BASE}/{rid}", headers=auth_headers)).json()
    assert rec["photos"][0]["garment_regions"] is None


@pytest.mark.asyncio
async def test_detect_uses_user_endpoints(client, auth_headers, stub_detect, db_session, test_user):
    from sqlalchemy import select

    from app.models.preference import UserPreference

    prefs = (
        await db_session.execute(select(UserPreference).where(UserPreference.user_id == test_user.id))
    ).scalar_one_or_none()
    if prefs is None:
        prefs = UserPreference(user_id=test_user.id)
        db_session.add(prefs)
    prefs.ai_endpoints = [{"url": "http://mine/v1", "vision_model": "v", "text_model": "t", "name": "mine"}]
    await db_session.commit()
    rid, pid = await _record(client, auth_headers)
    await client.post(f"{BASE}/{rid}/photos/{pid}/garment-regions/detect", headers=auth_headers)
    assert stub_detect["endpoints"][0] == "mine"


@pytest.mark.asyncio
async def test_detect_503_when_vision_disabled(client, auth_headers, stub_detect, monkeypatch):
    from app.config import Settings

    rid, pid = await _record(client, auth_headers)
    monkeypatch.setattr(Settings, "effective_ai_vision_enabled", property(lambda self: False))
    resp = await client.post(f"{BASE}/{rid}/photos/{pid}/garment-regions/detect", headers=auth_headers)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_put_clamps_validates_and_persists(client, auth_headers):
    rid, pid = await _record(client, auth_headers)
    payload = {"regions": [
        {"body_part": "bottoms", "box": {"l": -10, "t": 20, "r": 500, "b": 90}, "source": "manual"},
    ]}
    resp = await client.put(f"{BASE}/{rid}/photos/{pid}/garment-regions", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["regions"][0]["box"] == {"l": 0, "t": 20, "r": 199, "b": 90}
    bad = {"regions": [{"body_part": "wings", "box": {"l": 0, "t": 0, "r": 50, "b": 50}, "source": "manual"}]}
    assert (await client.put(f"{BASE}/{rid}/photos/{pid}/garment-regions", json=bad, headers=auth_headers)).status_code == 422


@pytest.mark.asyncio
async def test_rotate_clears_regions(client, auth_headers, stub_detect):
    rid, pid = await _record(client, auth_headers)
    await client.post(f"{BASE}/{rid}/photos/{pid}/garment-regions/detect", headers=auth_headers)
    resp = await client.post(f"{BASE}/{rid}/photos/{pid}/rotate", json={"direction": "cw"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["photos"][0]["garment_regions"] is None


@pytest.mark.asyncio
async def test_other_users_photo_is_404(client, auth_headers, other_auth_headers, stub_detect):
    rid, pid = await _record(client, auth_headers)
    url = f"{BASE}/{rid}/photos/{pid}/garment-regions"
    assert (await client.post(url + "/detect", headers=other_auth_headers)).status_code == 404
    assert (await client.put(url, json={"regions": []}, headers=other_auth_headers)).status_code == 404


async def _detect_with(monkeypatch, client, headers, rid, pid, text):
    async def fake(self, image_path):
        return text

    monkeypatch.setattr(AIService, "detect_garment_regions", fake)
    return await client.post(f"{BASE}/{rid}/photos/{pid}/garment-regions/detect", headers=headers)


@pytest.mark.asyncio
async def test_detect_valid_empty_regions_is_200(client, auth_headers, monkeypatch):
    rid, pid = await _record(client, auth_headers)
    resp = await _detect_with(monkeypatch, client, auth_headers, rid, pid, '{"regions": []}')
    assert resp.status_code == 200
    assert resp.json()["regions"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["I can't find any regions in this photo.", '{"regions": "x"}'])
async def test_detect_unusable_output_is_502_and_keeps_existing(client, auth_headers, monkeypatch, text):
    rid, pid = await _record(client, auth_headers)
    keep = {"regions": [{"body_part": "tops", "box": {"l": 0, "t": 0, "r": 50, "b": 50}, "source": "manual"}]}
    put = await client.put(f"{BASE}/{rid}/photos/{pid}/garment-regions", json=keep, headers=auth_headers)
    saved = put.json()["regions"]
    resp = await _detect_with(monkeypatch, client, auth_headers, rid, pid, text)
    assert resp.status_code == 502
    rec = (await client.get(f"{BASE}/{rid}", headers=auth_headers)).json()
    assert rec["photos"][0]["garment_regions"] == saved
