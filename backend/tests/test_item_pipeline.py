from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.item import ClothingItem, ItemStatus, TaggingStatus
from app.models.user import User
from app.services.color_calibration import ReferenceDetection
from app.services.image_service import ImageService
from app.workers.pipeline import run_item_pipeline_job
from app.workers.queues import TAGGING_QUEUE


class FakeRedis:
    def __init__(self, result="job-1"):
        self.calls: list[tuple] = []
        self.result = result

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(job_id=self.result) if self.result else None


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
        "status": ItemStatus.processing,
        "processing_kind": "pipeline",
    }
    defaults.update(overrides)
    item = ClothingItem(**defaults)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


def _sizes(item: ClothingItem) -> dict:
    return {
        "image_path": item.image_path,
        "medium_path": item.medium_path,
        "thumbnail_path": item.thumbnail_path,
    }


@pytest.fixture
def stubs(monkeypatch):
    """detect/calibrate/remove_background 全 monkeypatch，不跑 skimage/rembg。"""
    s = SimpleNamespace(detect=None, detect_calls=[], calibrate=[], cutout=[], item=None)

    def detect(image):
        s.detect_calls.append(image)
        return s.detect

    def calibrate(self, image_path, source, box, baseline):
        s.calibrate.append((image_path, source, box, baseline))
        return _sizes(s.item)

    def cutout(self, image_path):
        s.cutout.append(image_path)
        return {
            **_sizes(s.item),
            "original_backup_path": "x_orig.jpg",
            "mask_path": "x_mask.png",
        }

    monkeypatch.setattr("app.services.item_pipeline.detect_reference", detect)
    monkeypatch.setattr(ImageService, "calibrate_image", calibrate)
    monkeypatch.setattr(ImageService, "remove_background", cutout)
    return s


async def _run(db_session, item, redis, **kw):
    ctx = {"redis": redis}
    with (
        patch("app.workers.pipeline.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
    ):
        return await run_item_pipeline_job(ctx, str(item.id), **kw)


async def _reload(db_session, item_id) -> ClothingItem:
    db_session.expire_all()
    r = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return r.scalar_one()


async def test_detected_card_calibrates_then_cuts_out_then_queues_tagging(
    db_session, test_user, stubs
):
    item = await _make_item(db_session, test_user)
    stubs.item = item
    stubs.detect = ReferenceDetection(kind="gray", box=(1, 1, 5, 5), cards=None)
    redis = FakeRedis("job-xyz")

    out = await _run(db_session, item, redis)

    item = await _reload(db_session, item.id)
    assert out["status"] == "success"
    assert len(stubs.calibrate) == 1
    assert stubs.calibrate[0][2:] == ((1, 1, 5, 5), "gray")
    assert item.calibration_state == "done"
    assert item.mask_path == "x_mask.png"
    (args, kwargs) = redis.calls[0]
    assert args[0] == "tag_item_image"
    assert kwargs["_queue_name"] == TAGGING_QUEUE
    assert item.status == ItemStatus.processing
    assert item.processing_kind is None
    assert item.ai_job_id == "job-xyz"


async def test_no_card_skips_calibration_but_still_cuts_out(db_session, test_user, stubs):
    item = await _make_item(db_session, test_user)
    stubs.item = item
    stubs.detect = None

    await _run(db_session, item, FakeRedis())

    item = await _reload(db_session, item.id)
    assert stubs.calibrate == []
    # 检出读的是 _src 副本而不是工作图：副本尺寸与工作图不同时才能区分，这里
    # 直接断言收到的图与 _src 文件像素一致
    src = Image.open(ImageService().get_image_path(item.calibration_original_path)).convert("RGB")
    assert len(stubs.detect_calls) == 1
    assert stubs.detect_calls[0].size == src.size
    assert stubs.detect_calls[0].tobytes() == src.tobytes()
    assert item.calibration_state == "skipped"
    assert len(stubs.cutout) == 1


async def _done_item(db_session, test_user, stubs):
    item = await _make_item(
        db_session,
        test_user,
        calibration_state="done",
        mask_path="x_mask.png",
        tagging_status=TaggingStatus.tagged,
    )
    stubs.item = item
    return item


async def test_already_done_steps_are_not_rerun(db_session, test_user, stubs):
    item = await _done_item(db_session, test_user, stubs)
    redis = FakeRedis()

    await _run(db_session, item, redis)

    item = await _reload(db_session, item.id)
    assert stubs.detect_calls == []
    assert stubs.calibrate == [] and stubs.cutout == [] and redis.calls == []
    assert item.calibration_state == "done"
    assert item.status == ItemStatus.ready
    assert item.processing_kind is None


async def test_force_tag_requeues_tagged_item(db_session, test_user, stubs):
    item = await _done_item(db_session, test_user, stubs)
    redis = FakeRedis()

    await _run(db_session, item, redis, force_tag=True)

    assert len(redis.calls) == 1


async def test_cutout_failure_marks_error_and_keeps_pipeline_kind(
    db_session, test_user, stubs, monkeypatch
):
    item = await _make_item(db_session, test_user)
    stubs.item = item

    def boom(self, image_path):
        raise RuntimeError("rembg exploded")

    monkeypatch.setattr(ImageService, "remove_background", boom)
    redis = FakeRedis()

    out = await _run(db_session, item, redis)

    item = await _reload(db_session, item.id)
    assert out["status"] == "error"
    assert item.status == ItemStatus.error
    assert item.processing_kind == "pipeline"
    assert item.ai_failed_at is None
    assert item.ai_raw_response is None
    assert redis.calls == []


async def test_vision_disabled_defers_tagging(db_session, test_user, stubs, monkeypatch):
    item = await _make_item(db_session, test_user)
    stubs.item = item
    monkeypatch.setattr("app.services.item_pipeline.settings", Settings(ai_vision_enabled=False))
    redis = FakeRedis()

    out = await _run(db_session, item, redis)

    item = await _reload(db_session, item.id)
    assert out["tagging"] == "deferred"
    assert redis.calls == []
    assert item.status == ItemStatus.ready
    assert item.tagging_status == TaggingStatus.pending
    assert item.processing_kind is None


async def test_enqueue_failure_marks_tagging_error(db_session, test_user, stubs):
    item = await _make_item(db_session, test_user)
    stubs.item = item

    out = await _run(db_session, item, FakeRedis(result=None))

    item = await _reload(db_session, item.id)
    assert out["tagging"] == "error"
    assert item.status == ItemStatus.error
    assert item.processing_kind is None


async def test_missing_item_returns_error(db_session):
    out = await _run(db_session, SimpleNamespace(id=uuid4()), FakeRedis())
    assert out["status"] == "error"
