from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from arq.jobs import JobStatus

from app.services.embedding_sync import (
    SYNC_JOB_NAME,
    enqueue_embedding_sync,
    sync_job_id,
    sync_job_state,
)
from app.workers import embedding_sync as worker_mod
from app.workers.queues import IMAGE_QUEUE
from tests.test_embedding_store import FakeClient, make_item, storage  # noqa: F401


@pytest.mark.asyncio
async def test_enqueue_uses_deterministic_id_on_image_queue():
    uid = uuid4()
    redis = AsyncMock()
    redis.enqueue_job.return_value = MagicMock(job_id=sync_job_id(uid))
    assert await enqueue_embedding_sync(redis, uid) is True
    redis.enqueue_job.assert_awaited_once_with(
        SYNC_JOB_NAME, str(uid), _job_id=f"embedding-sync:{uid}", _queue_name=IMAGE_QUEUE
    )


@pytest.mark.asyncio
async def test_enqueue_returns_false_when_already_queued():
    redis = AsyncMock()
    redis.enqueue_job.return_value = None  # arq refuses a duplicate job id
    assert await enqueue_embedding_sync(redis, uuid4()) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [
        (JobStatus.queued, "queued"),
        (JobStatus.deferred, "queued"),
        (JobStatus.in_progress, "running"),
        (JobStatus.complete, "idle"),
        (JobStatus.not_found, "idle"),
    ],
)
async def test_sync_job_state_maps_arq_status(status, expected):
    with patch("app.services.embedding_sync.Job") as job_cls:
        job_cls.return_value.status = AsyncMock(return_value=status)
        assert await sync_job_state(AsyncMock(), uuid4()) == expected
        assert job_cls.call_args.kwargs["_queue_name"] == IMAGE_QUEUE




@pytest.mark.asyncio
async def test_job_syncs_with_budget_and_returns_counts(db_session, test_user, make_item, storage, monkeypatch):
    await make_item("j1")
    fake = FakeClient()
    monkeypatch.setattr(worker_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: fake))
    monkeypatch.setattr(worker_mod, "_storage_path", lambda: storage)
    with (
        patch("app.workers.embedding_sync.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
    ):
        out = await worker_mod.sync_embeddings_job({}, str(test_user.id))
    assert out["status"] == "ok" and out["done"] >= 1 and out["remaining"] == 0


@pytest.mark.asyncio
async def test_job_swallows_unavailable(db_session, test_user, make_item, storage, monkeypatch):
    await make_item("j2")
    monkeypatch.setattr(
        worker_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: FakeClient(fail_on_call=1))
    )
    monkeypatch.setattr(worker_mod, "_storage_path", lambda: storage)
    with (
        patch("app.workers.embedding_sync.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
    ):
        out = await worker_mod.sync_embeddings_job({}, str(test_user.id))
    assert out["status"] == "unavailable"


@pytest.mark.asyncio
async def test_job_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(worker_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: None))
    assert (await worker_mod.sync_embeddings_job({}, str(uuid4())))["status"] == "unconfigured"


@pytest.mark.asyncio
async def test_cron_skips_when_endpoint_down(monkeypatch):
    client = FakeClient()
    client.ping = AsyncMock(return_value=False)
    monkeypatch.setattr(worker_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: client))
    redis = AsyncMock()
    assert await worker_mod.embedding_sync_cron({"redis": redis}) == 0
    redis.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_cron_enqueues_users_with_stale_items(db_session, test_user, make_item, storage, monkeypatch):
    await make_item("c-stale")
    client = FakeClient()
    client.ping = AsyncMock(return_value=True)
    monkeypatch.setattr(worker_mod.EmbeddingClient, "from_settings", classmethod(lambda cls: client))
    monkeypatch.setattr(worker_mod, "_storage_path", lambda: storage)
    redis = AsyncMock()
    redis.enqueue_job.return_value = MagicMock()
    with (
        patch("app.workers.embedding_sync.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
    ):
        n = await worker_mod.embedding_sync_cron({"redis": redis})
    assert n >= 1
    enqueued_users = {c.args[1] for c in redis.enqueue_job.await_args_list}
    assert str(test_user.id) in enqueued_users
