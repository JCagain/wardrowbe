import asyncio
import threading
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select, update
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
    # 先播种 _src，再把工作图换成不同尺寸/颜色：检出若读 image_path 就会断言失败
    item.calibration_original_path = ImageService().ensure_calibration_source(item.image_path)
    await db_session.commit()
    Image.new("RGB", (50, 70), (250, 0, 0)).save(
        ImageService().get_image_path(item.image_path), format="JPEG"
    )

    await _run(db_session, item, FakeRedis())

    item = await _reload(db_session, item.id)
    assert stubs.calibrate == []
    # 检出读的是 _src 副本而不是工作图：副本尺寸与工作图不同时才能区分，这里
    # 直接断言收到的图与 _src 文件像素一致
    src = Image.open(ImageService().get_image_path(item.calibration_original_path)).convert("RGB")
    assert len(stubs.detect_calls) == 1
    assert src.size == (400, 600)
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
    # final-findings #8：跳过打标回到 ready 时 ai_started_at 不能残留
    assert item.ai_started_at is None


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
    assert item.ai_started_at is None


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


# ---- final-findings #6 / Ruling 115：已有抠图时自动校色不动像素 ----


async def test_existing_cutout_is_kept_when_calibration_state_is_none(
    db_session, test_user, stubs
):
    item = await _make_item(db_session, test_user, mask_path="kept_mask.png")
    stubs.item = item
    stubs.detect = ReferenceDetection(kind="gray", box=(1, 1, 5, 5), cards=None)
    redis = FakeRedis()

    out = await _run(db_session, item, redis)

    item = await _reload(db_session, item.id)
    assert out["status"] == "success"
    assert stubs.detect_calls == []
    assert stubs.calibrate == [] and stubs.cutout == []
    assert item.mask_path == "kept_mask.png"
    assert item.calibration_state == "none"
    assert len(redis.calls) == 1


# ---- final-findings #9/#10 / Ruling 116：hand-off 前回读 DB ----


async def test_hand_off_bails_when_the_item_was_cancelled_meanwhile(
    db_session, test_user, stubs, monkeypatch
):
    item = await _make_item(db_session, test_user, ai_job_id="job-live")
    stubs.item = item
    from app.workers import pipeline as pipeline_mod

    original = pipeline_mod.ensure_cutout

    async def cut_then_user_cancels(db, it):
        done = await original(db, it)
        # 模拟 cancel-analysis 端点在另一个会话里把物品翻回 ready；
        # synchronize_session=False：job 手里的内存对象不会被顺手同步
        await db.execute(
            update(ClothingItem)
            .where(ClothingItem.id == it.id)
            .values(status=ItemStatus.ready, processing_kind=None, ai_job_id=None)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        return done

    monkeypatch.setattr(pipeline_mod, "ensure_cutout", cut_then_user_cancels)
    redis = FakeRedis()

    out = await _run(db_session, item, redis)

    item = await _reload(db_session, item.id)
    assert out["tagging"] == "cancelled"
    assert redis.calls == []
    assert item.status == ItemStatus.ready
    assert item.processing_kind is None
    assert item.ai_job_id is None


# ---- final-findings #1 / Ruling 114：取消时等图像线程跑完并落文件列 ----


class _Gate:
    """让线程里的图像操作卡在门口，直到测试放行。"""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()


async def _cancel_while_blocked(db_session, item, gate, *, cancels: int):
    ctx = {"redis": FakeRedis()}
    with (
        patch("app.workers.pipeline.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
    ):
        task = asyncio.create_task(run_item_pipeline_job(ctx, str(item.id)))
        assert await asyncio.to_thread(gate.entered.wait, 5)
        for _ in range(cancels):
            task.cancel()
            for _ in range(5):
                await asyncio.sleep(0)
        # 用户的取消端点：状态列翻回 ready（取消路径绝不能再写这些列）
        await db_session.execute(
            update(ClothingItem)
            .where(ClothingItem.id == item.id)
            .values(status=ItemStatus.ready, processing_kind=None, ai_job_id=None)
            .execution_options(synchronize_session=False)
        )
        await db_session.commit()
        gate.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        # 旧实现里线程在 job 结束后仍在跑：等它真正写完再看盘
        assert await asyncio.to_thread(gate.finished.wait, 5)
        return ctx["redis"]


@pytest.mark.parametrize("cancels", [1, 2])
async def test_cancel_during_cutout_persists_the_files_the_thread_wrote(
    db_session, test_user, monkeypatch, cancels
):
    item = await _make_item(
        db_session, test_user, calibration_state="skipped", ai_job_id="job-live"
    )
    gate = _Gate()

    class BlockingProvider:
        def remove(self, image):
            gate.entered.set()
            gate.release.wait(5)
            return image.convert("RGBA")

    original = ImageService.remove_background

    def tracked(self, image_path):
        try:
            return original(self, image_path)
        finally:
            gate.finished.set()

    monkeypatch.setattr(
        "app.services.background_removal.get_provider", lambda: BlockingProvider()
    )
    monkeypatch.setattr(ImageService, "remove_background", tracked)

    redis = await _cancel_while_blocked(db_session, item, gate, cancels=cancels)

    item = await _reload(db_session, item.id)
    svc = ImageService()
    for col in ("image_path", "medium_path", "thumbnail_path", "mask_path", "original_image_path"):
        rel = getattr(item, col)
        assert rel, col
        assert svc.get_image_path(rel).exists(), f"{col} -> missing {rel}"
    assert item.image_path.endswith(".png")
    # 状态列归取消端点所有：取消路径只落文件列
    assert item.status == ItemStatus.ready
    assert item.processing_kind is None
    assert item.ai_job_id is None
    assert redis.calls == []


async def test_cancel_during_auto_calibrate_persists_the_calibration(
    db_session, test_user, stubs, monkeypatch
):
    item = await _make_item(db_session, test_user, ai_job_id="job-live")
    stubs.item = item
    stubs.detect = ReferenceDetection(kind="gray", box=(1, 1, 5, 5), cards=None)
    gate = _Gate()

    def blocking_calibrate(self, image_path, source, box, baseline):
        gate.entered.set()
        gate.release.wait(5)
        try:
            stubs.calibrate.append((image_path, source, box, baseline))
            return _sizes(stubs.item)
        finally:
            gate.finished.set()

    monkeypatch.setattr(ImageService, "calibrate_image", blocking_calibrate)

    await _cancel_while_blocked(db_session, item, gate, cancels=2)

    item = await _reload(db_session, item.id)
    assert len(stubs.calibrate) == 1
    assert item.calibration_state == "done"
    assert item.calibration_original_path
    assert stubs.cutout == []
    assert item.status == ItemStatus.ready
