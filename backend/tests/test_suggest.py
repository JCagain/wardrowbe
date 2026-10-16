import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from app.config import get_settings
from app.models.item import ClothingItem, ItemStatus
from app.services import suggest as suggest_mod
from app.services.ai_service import AIService
from app.services.embedding_client import EmbeddingUnavailableError
from app.services.embedding_store import upsert_embedding

BASE = "/api/v1/records"


def _jpeg(size=(200, 100)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


async def _record(client, headers):
    resp = await client.post(
        BASE, data={"data": json.dumps({"date": "2026-10-01"})},
        files=[("photos", ("p.jpg", _jpeg(), "image/jpeg"))], headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["id"], body["photos"][0]["id"]


class FakeEmb:
    model = "m1"

    def __init__(self, query=(1, 0, 0, 0), fail=False):
        self.query = np.asarray(query, dtype=np.float32)
        self.fail = fail
        self.instructions = []

    async def embed_images(self, images, instruction=None, batch_size=8):
        self.instructions.append(instruction)
        if self.fail:
            raise EmbeddingUnavailableError("down")
        return [self.query / np.linalg.norm(self.query) for _ in images]


@pytest.fixture
def fake_emb(monkeypatch):
    emb = FakeEmb()
    monkeypatch.setattr(suggest_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: emb))
    return emb


async def _item(db_session, user, vec, *, type_="shirt", body_part="tops", with_file=True, model="m1"):
    storage = Path(get_settings().storage_path)
    rel = f"{user.id}/sugg_{uuid4().hex}.jpg"
    if with_file:
        (storage / rel).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (30, 30), (10, 20, 30)).save(storage / rel)
    item = ClothingItem(id=uuid4(), user_id=user.id, type=type_, body_part=body_part, image_path=rel,
                        status=ItemStatus.ready, primary_colors=["blue"], wear_count=0,
                        wears_since_wash=0, needs_wash=False)
    db_session.add(item)
    await db_session.commit()
    await upsert_embedding(db_session, item.id, model, "fp", np.asarray(vec, dtype=np.float32))
    await db_session.commit()
    return item


def _region(part="tops", box=(0, 0, 99, 99)):
    l, t, r, b = box
    return {"region": {"body_part": part, "box": {"l": l, "t": t, "r": r, "b": b}, "source": "manual"}}


@pytest.fixture
def no_rerank_ai(monkeypatch):
    async def boom(self, q, cs):
        raise AssertionError("rerank must not be called")
    monkeypatch.setattr(AIService, "rerank_garment_candidates", boom)


@pytest.mark.asyncio
async def test_recall_only_orders_by_cosine(client, auth_headers, db_session, test_user, fake_emb, no_rerank_ai):
    near = await _item(db_session, test_user, (1, 0.1, 0, 0))
    far = await _item(db_session, test_user, (0, 1, 0, 0))
    rid, pid = await _record(client, auth_headers)
    r = await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json={**_region(), "rerank": False}, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["candidates"]]
    assert ids.index(str(near.id)) < ids.index(str(far.id))
    assert body["reranked"] is False and body["rerank_error"] is None
    cand = next(c for c in body["candidates"] if c["id"] == str(near.id))
    assert cand["verdict"] is None and cand["thumbnail_url"] and cand["lifecycle"]
    assert fake_emb.instructions == [suggest_mod.QUERY_INSTRUCTION]


@pytest.mark.asyncio
async def test_part_filter_with_fallback(client, auth_headers, db_session, test_user, fake_emb, no_rerank_ai, monkeypatch):
    monkeypatch.setattr(suggest_mod, "PART_MIN", 2)
    top = await _item(db_session, test_user, (0.5, 0.5, 0, 0), type_="shirt", body_part="tops")
    pants = await _item(db_session, test_user, (1, 0, 0, 0), type_="jeans", body_part="bottoms")
    rid, pid = await _record(client, auth_headers)
    body = (await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json={**_region("tops"), "rerank": False},
                              headers=auth_headers)).json()
    ids = [c["id"] for c in body["candidates"]]
    # test_user is fresh per test, so exactly these two items exist: 1 part hit < PART_MIN=2
    # → top up from all parts; the part hit stays first despite the lower cosine.
    assert ids == [str(top.id), str(pants.id)]
    assert body["part_filtered"] is True


@pytest.mark.asyncio
async def test_rerank_groups_and_ranks(client, auth_headers, db_session, test_user, fake_emb, monkeypatch):
    monkeypatch.setattr(suggest_mod, "RERANK_GROUP", 2)
    items = [await _item(db_session, test_user, (1, i / 10, 0, 0)) for i in range(3)]
    calls = []

    async def fake_rerank(self, q, cs):
        calls.append(len(cs))
        return json.dumps({"verdicts": ["different"] * len(cs)}) if len(calls) == 1 else '{"verdicts": ["same"]}'

    monkeypatch.setattr(AIService, "rerank_garment_candidates", fake_rerank)
    rid, pid = await _record(client, auth_headers)
    body = (await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json=_region(), headers=auth_headers)).json()
    assert body["reranked"] is True
    assert all(n <= 2 for n in calls)
    assert body["candidates"][0]["verdict"] == "same"


@pytest.mark.asyncio
async def test_rerank_failure_falls_back_to_cosine(client, auth_headers, db_session, test_user, fake_emb, monkeypatch):
    await _item(db_session, test_user, (1, 0, 0, 0))

    async def fail(self, q, cs):
        raise RuntimeError("27B down")

    monkeypatch.setattr(AIService, "rerank_garment_candidates", fail)
    rid, pid = await _record(client, auth_headers)
    body = (await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json=_region(), headers=auth_headers)).json()
    assert body["reranked"] is False and "27B down" in body["rerank_error"]
    assert body["candidates"] and all(c["verdict"] is None for c in body["candidates"])


@pytest.mark.asyncio
async def test_unreadable_candidate_image_gets_null_verdict(client, auth_headers, db_session, test_user, fake_emb, monkeypatch):
    ok = await _item(db_session, test_user, (1, 0, 0, 0))
    gone = await _item(db_session, test_user, (1, 0.05, 0, 0), with_file=False)
    seen = []

    async def fake_rerank(self, q, cs):
        seen.append(len(cs))
        return json.dumps({"verdicts": ["same"] * len(cs)})

    monkeypatch.setattr(AIService, "rerank_garment_candidates", fake_rerank)
    rid, pid = await _record(client, auth_headers)
    body = (await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json=_region(), headers=auth_headers)).json()
    by_id = {c["id"]: c for c in body["candidates"]}
    assert by_id[str(ok.id)]["verdict"] == "same"
    assert by_id[str(gone.id)]["verdict"] is None


@pytest.mark.asyncio
async def test_tiny_box_is_422_without_model_calls(client, auth_headers, fake_emb, no_rerank_ai):
    rid, pid = await _record(client, auth_headers)
    r = await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json=_region(box=(195, 95, 400, 400)), headers=auth_headers)
    assert r.status_code == 422
    assert fake_emb.instructions == []


@pytest.mark.asyncio
async def test_embedding_unconfigured_or_down_is_503(client, auth_headers, monkeypatch, no_rerank_ai):
    rid, pid = await _record(client, auth_headers)
    monkeypatch.setattr(suggest_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: None))
    assert (await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json=_region(), headers=auth_headers)).status_code == 503
    monkeypatch.setattr(suggest_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: FakeEmb(fail=True)))
    assert (await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json=_region(), headers=auth_headers)).status_code == 503


@pytest.mark.asyncio
async def test_other_users_photo_is_404(client, auth_headers, db_session, fake_emb, no_rerank_ai):
    from app.api.auth import create_access_token
    from app.models import User

    other = User(id=uuid4(), external_id=f"o-{uuid4()}", email=f"o-{uuid4()}@x.com",
                 display_name="o", timezone="UTC", is_active=True)
    db_session.add(other)
    await db_session.commit()
    rid, pid = await _record(client, auth_headers)
    r = await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json=_region(),
                          headers={"Authorization": f"Bearer {create_access_token(other.external_id)}"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_suggest_never_writes(client, auth_headers, db_session, test_user, fake_emb, no_rerank_ai):
    await _item(db_session, test_user, (1, 0, 0, 0))
    rid, pid = await _record(client, auth_headers)
    before = (await client.get(f"{BASE}/{rid}", headers=auth_headers)).json()
    await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json={**_region(), "rerank": False}, headers=auth_headers)
    after = (await client.get(f"{BASE}/{rid}", headers=auth_headers)).json()
    assert after["items"] == before["items"] == []
    assert after["photos"][0]["garment_regions"] == before["photos"][0]["garment_regions"]


@pytest.mark.asyncio
async def test_stops_reranking_when_client_disconnects(db_session, test_user, monkeypatch):
    """Service level: should_stop is checked between rerank groups."""
    monkeypatch.setattr(suggest_mod, "RERANK_GROUP", 1)
    for i in range(3):
        await _item(db_session, test_user, (1, i / 10, 0, 0))
    calls = []

    async def fake_rerank(self, q, cs):
        calls.append(1)
        return '{"verdicts": ["same"]}'

    monkeypatch.setattr(AIService, "rerank_garment_candidates", fake_rerank)
    stop_after = {"n": 1}

    async def should_stop():
        return len(calls) >= stop_after["n"]

    res = await suggest_mod.suggest_for_crop(
        db_session, test_user.id, Image.new("RGB", (50, 50)), "tops",
        FakeEmb(), AIService(endpoints=None), rerank=True, should_stop=should_stop,
    )
    assert len(calls) == 1
    assert res.reranked is True  # partial rerank still counts; unjudged ones stay None


@pytest.mark.asyncio
async def test_recall_only_caps_at_eight(client, auth_headers, db_session, test_user, fake_emb, no_rerank_ai):
    for i in range(12):
        await _item(db_session, test_user, (1, i / 20, 0, 0))
    rid, pid = await _record(client, auth_headers)
    body = (await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json={**_region(), "rerank": False},
                              headers=auth_headers)).json()
    assert len(body["candidates"]) == 8


@pytest.mark.asyncio
async def test_all_different_still_returns_five(client, auth_headers, db_session, test_user, fake_emb, monkeypatch):
    for i in range(7):
        await _item(db_session, test_user, (1, i / 20, 0, 0))

    async def fake_rerank(self, q, cs):
        return json.dumps({"verdicts": ["different"] * len(cs)})

    monkeypatch.setattr(AIService, "rerank_garment_candidates", fake_rerank)
    rid, pid = await _record(client, auth_headers)
    body = (await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json=_region(), headers=auth_headers)).json()
    assert body["reranked"] is True
    assert len(body["candidates"]) == 5


@pytest.mark.asyncio
async def test_corrupt_stored_photo_is_422(client, auth_headers, fake_emb, no_rerank_ai):
    rid, pid = await _record(client, auth_headers)
    rec = (await client.get(f"{BASE}/{rid}", headers=auth_headers)).json()
    path = rec["photos"][0]["image_path"]
    (Path(get_settings().storage_path) / path).write_bytes(b"not an image")
    r = await client.post(f"{BASE}/{rid}/photos/{pid}/suggest", json=_region(), headers=auth_headers)
    assert r.status_code == 422
    assert fake_emb.instructions == []
