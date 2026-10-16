from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api import embeddings as api_mod

BASE = "/api/v1/embeddings"


class _Client:
    model = "m1"

    def __init__(self, up=True):
        self._up = up

    async def ping(self):
        return self._up


def _redis(enqueued=True):
    redis = AsyncMock()
    redis.enqueue_job.return_value = MagicMock() if enqueued else None
    return redis


@pytest.mark.asyncio
async def test_status_unconfigured(client, auth_headers, monkeypatch):
    monkeypatch.setattr(api_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: None))
    r = await client.get(f"{BASE}/status", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"configured": False, "available": False, "model": None,
                        "total": 0, "embedded": 0, "stale": 0, "job": "idle"}


@pytest.mark.asyncio
async def test_status_counts_and_job(client, auth_headers, monkeypatch):
    monkeypatch.setattr(api_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: _Client(up=False)))
    monkeypatch.setattr(api_mod, "embedding_counts", AsyncMock(return_value=(10, 3)))
    with (
        patch("app.api.embeddings.create_pool", new_callable=AsyncMock) as cp,
        patch("app.api.embeddings.sync_job_state", AsyncMock(return_value="running")),
    ):
        cp.return_value = _redis()
        r = await client.get(f"{BASE}/status", headers=auth_headers)
    assert r.json() == {"configured": True, "available": False, "model": "m1",
                        "total": 10, "embedded": 7, "stale": 3, "job": "running"}


@pytest.mark.asyncio
async def test_sync_enqueues(client, auth_headers, monkeypatch, test_user):
    monkeypatch.setattr(api_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: _Client()))
    mark = AsyncMock(return_value=0)
    monkeypatch.setattr(api_mod, "mark_all_stale", mark)
    with (
        patch("app.api.embeddings.create_pool", new_callable=AsyncMock) as cp,
        patch("app.api.embeddings.sync_job_state", AsyncMock(return_value="queued")),
    ):
        redis = _redis()
        cp.return_value = redis
        r = await client.post(f"{BASE}/sync", json={}, headers=auth_headers)
    assert r.status_code == 200 and r.json() == {"queued": True, "job": "queued"}
    mark.assert_not_awaited()
    assert redis.enqueue_job.await_args.args[1] == str(test_user.id)


@pytest.mark.asyncio
async def test_rebuild_blanks_then_enqueues_even_if_already_running(client, auth_headers, monkeypatch):
    monkeypatch.setattr(api_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: _Client()))
    mark = AsyncMock(return_value=5)
    monkeypatch.setattr(api_mod, "mark_all_stale", mark)
    with (
        patch("app.api.embeddings.create_pool", new_callable=AsyncMock) as cp,
        patch("app.api.embeddings.sync_job_state", AsyncMock(return_value="running")),
    ):
        cp.return_value = _redis(enqueued=False)
        r = await client.post(f"{BASE}/sync", json={"rebuild": True}, headers=auth_headers)
    assert r.status_code == 200 and r.json() == {"queued": False, "job": "running"}
    mark.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_503_when_unconfigured(client, auth_headers, monkeypatch):
    monkeypatch.setattr(api_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: None))
    r = await client.post(f"{BASE}/sync", json={}, headers=auth_headers)
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_requires_auth(client):
    assert (await client.get(f"{BASE}/status")).status_code in (401, 403)
