from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService
from app.workers.background_removal import remove_item_background_job
from app.workers.image_worker import ImageWorkerSettings
from app.workers.queues import IMAGE_QUEUE, TAGGING_QUEUE, queue_for_kind
from app.workers.rotation import rotate_item_image_job
from app.workers.worker import WorkerSettings


def _jpeg_bytes(size: tuple[int, int] = (400, 600)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (10, 200, 30)).save(buf, format="JPEG")
    return buf.getvalue()


async def _make_item(db_session: AsyncSession, user: User, **overrides) -> ClothingItem:
    svc = ImageService()
    paths = await svc.process_and_store(
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
        "processing_kind": "rotate",
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


def _job_on(db_session: AsyncSession):
    return (
        patch("app.workers.rotation.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
    )


class TestQueueRouting:
    def test_image_kinds_route_to_the_image_queue(self):
        assert queue_for_kind("rotate") == IMAGE_QUEUE
        assert queue_for_kind("background_removal") == IMAGE_QUEUE

    def test_tagging_and_unknown_kinds_route_to_the_tagging_queue(self):
        assert queue_for_kind(None) == TAGGING_QUEUE
        assert queue_for_kind("tagging") == TAGGING_QUEUE

    def test_the_two_queues_are_distinct(self):
        assert IMAGE_QUEUE != TAGGING_QUEUE


class TestWorkerSplit:
    def test_image_worker_serves_the_image_queue(self):
        assert ImageWorkerSettings.queue_name == IMAGE_QUEUE

    def test_image_worker_carries_both_image_jobs(self):
        # Embedding sync is registered as an arq Function (keep_result=0), so
        # compare by name; the two image jobs are plain callables.
        names = {getattr(f, "name", None) or f.__name__ for f in ImageWorkerSettings.functions}
        assert names == {
            rotate_item_image_job.__name__,
            remove_item_background_job.__name__,
            "run_item_pipeline_job",
            "sync_embeddings_job",
        }

    def test_tagging_worker_no_longer_runs_image_jobs(self):
        # Leaving these on arq:tagging is the starvation this split exists to
        # fix: one bulk batch blocks every AI tagging job behind it.
        assert rotate_item_image_job not in WorkerSettings.functions
        assert remove_item_background_job not in WorkerSettings.functions

    def test_image_worker_keeps_no_results(self):
        # A kept failure result would block the fixed embedding-sync job id.
        assert ImageWorkerSettings.keep_result == 0

    def test_image_worker_can_abort_jobs(self):
        # cancel-analysis aborts a queued rotate or background removal.
        assert ImageWorkerSettings.allow_abort_jobs is True


class TestRotateItemImageJob:
    @pytest.mark.asyncio
    async def test_success_rotates_on_disk_and_returns_the_item_to_ready(
        self, db_session: AsyncSession, test_user: User
    ):
        item = await _make_item(db_session, test_user)
        svc = ImageService()
        assert Image.open(svc.get_image_path(item.image_path)).size == (400, 600)

        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            result = await rotate_item_image_job({}, str(item.id), "cw")

        assert result["status"] == "success"
        assert Image.open(svc.get_image_path(item.image_path)).size == (600, 400)
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.processing_kind is None
        assert refreshed.ai_started_at is None

    @pytest.mark.asyncio
    async def test_retired_item_lands_archived_not_ready(
        self, db_session: AsyncSession, test_user: User
    ):
        # Rotation is a pipeline finisher: it must not resurrect a retired
        # item (spec §10.16 status/lifecycle sync).
        item = await _make_item(db_session, test_user, lifecycle="retired")

        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            result = await rotate_item_image_job({}, str(item.id), "cw")

        assert result["status"] == "success"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.archived

    @pytest.mark.asyncio
    async def test_regenerates_every_size(self, db_session: AsyncSession, test_user: User):
        item = await _make_item(db_session, test_user)
        svc = ImageService()

        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            await rotate_item_image_job({}, str(item.id), "cw")

        medium = Image.open(svc.get_image_path(item.medium_path)).size
        thumb = Image.open(svc.get_image_path(item.thumbnail_path)).size
        assert medium[0] > medium[1]
        assert thumb[0] > thumb[1]

    @pytest.mark.asyncio
    async def test_writes_back_the_paths_the_rotation_actually_returned(
        self, db_session: AsyncSession, test_user: User
    ):
        # An RGB working image stored under a .png name gets rewritten as .jpg
        # (extension follows the alpha channel), so `_save_all_sizes` returns
        # different names - the job must write them back or the item keeps
        # pointing at the now-deleted PNG. A matted RGBA PNG keeps its
        # extension; this is the case where the names actually change.
        item = await _make_item(db_session, test_user)
        svc = ImageService()
        base = item.image_path.rsplit(".", 1)[0]
        png_path = f"{base}.png"
        Image.new("RGB", (400, 600), (10, 200, 30)).save(
            svc.get_image_path(png_path), format="PNG"
        )
        item.image_path = png_path
        item.medium_path = f"{base}_medium.png"
        item.thumbnail_path = f"{base}_thumb.png"
        await db_session.commit()

        original = ImageService.rotate_image
        returned: dict = {}

        def _rotate(self, image_path, direction="cw"):
            out = original(self, image_path, direction)
            returned.update(out)
            return out

        get_db, close_db = _job_on(db_session)
        with get_db, close_db, patch.object(ImageService, "rotate_image", _rotate):
            result = await rotate_item_image_job({}, str(item.id), "cw")

        assert result["status"] == "success"
        # The format flip happened, so the returned names differ from the old ones.
        assert returned["image_path"] != png_path
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.image_path == returned["image_path"]
        assert refreshed.medium_path == returned["medium_path"]
        assert refreshed.thumbnail_path == returned["thumbnail_path"]
        assert svc.get_image_path(refreshed.image_path).exists()

    @pytest.mark.asyncio
    async def test_sets_ai_started_at_before_the_rotation_runs(
        self, db_session: AsyncSession, test_user: User
    ):
        item = await _make_item(db_session, test_user)
        seen: dict = {}
        original = ImageService.rotate_image

        def _rotate(self, image_path, direction="cw"):
            # Reads the same ORM object the job mutated (shared identity map on
            # db_session), proving the started-at write is committed before the
            # thread-offloaded rotation, not after.
            seen["ai_started_at"] = item.ai_started_at
            return original(self, image_path, direction)

        get_db, close_db = _job_on(db_session)
        with get_db, close_db, patch.object(ImageService, "rotate_image", _rotate):
            await rotate_item_image_job({}, str(item.id), "cw")

        assert seen["ai_started_at"] is not None

    @pytest.mark.asyncio
    async def test_failure_marks_error_and_keeps_the_kind(
        self, db_session: AsyncSession, test_user: User
    ):
        # The kind has to survive so the grid labels the failure as a rotate and
        # the retry path re-runs a rotate rather than an AI analysis.
        item = await _make_item(db_session, test_user, image_path="nobody/missing.jpg")

        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            result = await rotate_item_image_job({}, str(item.id), "cw")

        assert result["status"] == "error"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.error
        assert refreshed.processing_kind == "rotate"
        assert refreshed.ai_started_at is None

    @pytest.mark.asyncio
    async def test_failure_leaves_ai_bookkeeping_untouched(
        self, db_session: AsyncSession, test_user: User
    ):
        # ai_failed_at drives the AI retry cooldown, so a rotate failure must
        # not start one.
        item = await _make_item(db_session, test_user, image_path="nobody/missing.jpg")

        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            await rotate_item_image_job({}, str(item.id), "cw")

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.ai_failed_at is None
        assert refreshed.ai_raw_response is None

    @pytest.mark.asyncio
    async def test_missing_item_returns_an_error_without_raising(self, db_session: AsyncSession):
        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            result = await rotate_item_image_job({}, str(uuid4()), "cw")

        assert result["status"] == "error"


def _opaque_provider():
    provider = MagicMock()
    provider.remove.side_effect = lambda img: Image.new("RGBA", img.size, (0, 0, 255, 255))
    return provider


class TestRemoveItemBackgroundJob:
    @pytest.mark.asyncio
    async def test_persists_the_written_paths_mask_and_backup(
        self, db_session: AsyncSession, test_user: User
    ):
        # remove_background returns the paths it wrote (extension flips to
        # .png) plus a mask sidecar and the pre-matte backup; the job must
        # write all of them back. bg_color_hex stays in the queue signature
        # but is ignored (no solid-background composite is stored).
        item = await _make_item(
            db_session, test_user, processing_kind="background_removal"
        )
        item_id = item.id
        base = item.image_path.rsplit(".", 1)[0]
        svc = ImageService()

        get_db = patch(
            "app.workers.background_removal.get_db_session", return_value=db_session
        )
        close_db = patch.object(db_session, "close", new_callable=AsyncMock)
        provider = patch(
            "app.services.background_removal.get_provider", return_value=_opaque_provider()
        )
        with get_db, close_db, provider:
            result = await remove_item_background_job({}, str(item_id), "#FFFFFF")

        assert result["status"] == "success"
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.image_path == f"{base}.png"
        assert refreshed.medium_path == f"{base}_medium.png"
        assert refreshed.thumbnail_path == f"{base}_thumb.png"
        assert refreshed.mask_path == f"{base}_mask.png"
        assert refreshed.original_image_path == f"{base}_orig.jpg"
        assert refreshed.status == ItemStatus.ready
        for path in (
            refreshed.image_path,
            refreshed.medium_path,
            refreshed.thumbnail_path,
            refreshed.mask_path,
            refreshed.original_image_path,
        ):
            assert svc.get_image_path(path).exists()
        assert Image.open(svc.get_image_path(refreshed.image_path)).mode == "RGBA"
