"""Tests for POST /items/{id}/pipeline and POST /items/bulk/pipeline."""

from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (400, 600), (10, 200, 30)).save(buf, format="JPEG")
    return buf.getvalue()


async def _make_item(db_session: AsyncSession, user: User, **overrides) -> ClothingItem:
    paths = await ImageService().process_and_store(
        user_id=user.id, image_data=_jpeg_bytes(), original_filename="test.jpg"
    )
    defaults = {
        "user_id": user.id,
        "type": "shirt",
        "image_path": paths["image_path"],
        "medium_path": paths["medium_path"],
        "thumbnail_path": paths["thumbnail_path"],
        "image_hash": paths["image_hash"],
        "status": ItemStatus.ready,
    }
    defaults.update(overrides)
    item = ClothingItem(**defaults)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _get_item(db_session: AsyncSession, item_id) -> ClothingItem:
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return result.scalar_one()


def _redis(job_id: str = "pipe-job-id") -> AsyncMock:
    r = AsyncMock()
    r.enqueue_job.return_value.job_id = job_id
    return r


@pytest.mark.asyncio
async def test_single_pipeline_enqueues_on_image_queue(
    client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
):
    item = await _make_item(db_session, test_user)
    item_id = item.id
    with patch("app.api.items.create_pool", new_callable=AsyncMock) as cp:
        cp.return_value = r = _redis()
        resp = await client.post(
            f"/api/v1/items/{item_id}/pipeline", headers=auth_headers, json={}
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "queued", "job_id": "pipe-job-id"}
    r.enqueue_job.assert_called_once_with(
        "run_item_pipeline_job", str(item_id), False, _queue_name="arq:images"
    )
    r.aclose.assert_awaited()
    db_session.expire_all()
    got = await _get_item(db_session, item_id)
    assert got.status == ItemStatus.processing
    assert got.processing_kind == "pipeline"
    assert got.ai_job_id == "pipe-job-id"


@pytest.mark.asyncio
async def test_single_pipeline_passes_force_tag(
    client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
):
    item = await _make_item(db_session, test_user)
    item_id = item.id
    with patch("app.api.items.create_pool", new_callable=AsyncMock) as cp:
        cp.return_value = r = _redis()
        resp = await client.post(
            f"/api/v1/items/{item_id}/pipeline", headers=auth_headers, json={"force_tag": True}
        )
    assert resp.status_code == 200
    assert r.enqueue_job.call_args.args[2] is True


@pytest.mark.asyncio
async def test_single_pipeline_dedups_live_job(
    client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
):
    item = await _make_item(
        db_session, test_user, status=ItemStatus.processing, ai_job_id="live-job"
    )
    item_id = item.id
    with patch("app.api.items.create_pool", new_callable=AsyncMock) as cp:
        cp.return_value = r = _redis()
        resp = await client.post(
            f"/api/v1/items/{item_id}/pipeline", headers=auth_headers, json={}
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "already_queued", "job_id": "live-job"}
    r.enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_single_pipeline_other_user_404(
    client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
):
    other = User(
        email=f"other-{uuid4().hex[:8]}@example.com",
        external_id=f"ext-{uuid4().hex}",
        display_name="Other",
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    item = await _make_item(db_session, other)
    with patch("app.api.items.create_pool", new_callable=AsyncMock) as cp:
        cp.return_value = _redis()
        resp = await client.post(
            f"/api/v1/items/{item.id}/pipeline", headers=auth_headers, json={}
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_bulk_pipeline_skips_live_jobs_and_queues_rest(
    client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
):
    a = await _make_item(db_session, test_user)
    b = await _make_item(db_session, test_user)
    c = await _make_item(db_session, test_user, status=ItemStatus.processing, ai_job_id="live")
    ids = [str(a.id), str(b.id), str(c.id)]
    with patch("app.api.items.create_pool", new_callable=AsyncMock) as cp:
        cp.return_value = r = _redis()
        resp = await client.post(
            "/api/v1/items/bulk/pipeline", headers=auth_headers, json={"item_ids": ids}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["queued"], body["skipped"], body["failed"]) == (2, 1, 0)
    assert "already_done" not in body
    assert r.enqueue_job.call_count == 2
    for call in r.enqueue_job.call_args_list:
        assert call.args[0] == "run_item_pipeline_job"
        assert call.args[2] is False
        assert call.kwargs == {"_queue_name": "arq:images"}


@pytest.mark.asyncio
async def test_pipeline_enqueue_failure_restores_status(
    client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
):
    item = await _make_item(db_session, test_user)
    item_id = item.id
    with patch("app.api.items.create_pool", new_callable=AsyncMock) as cp:
        r = AsyncMock()
        r.enqueue_job.return_value = None
        cp.return_value = r
        resp = await client.post(
            f"/api/v1/items/{item_id}/pipeline", headers=auth_headers, json={}
        )
    assert resp.status_code == 500
    db_session.expire_all()
    got = await _get_item(db_session, item_id)
    assert got.status == ItemStatus.ready
    assert got.processing_kind is None
