"""物品流水线共享步骤（D8：先 AI 处理，后录入）。

与 API 层解耦：这里抛原始异常（`ValueError` 等），由调用方决定映射成 HTTP 状态还是 job 失败。
"""

import asyncio
import logging
from pathlib import Path

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.item import ClothingItem, ItemStatus, TaggingStatus
from app.services.color_calibration import detect_reference
from app.services.image_files import assign_size_paths
from app.services.image_service import ImageService
from app.services.item_service import ItemService
from app.utils.item_lifecycle import terminal_status
from app.workers.queues import TAGGING_QUEUE

logger = logging.getLogger(__name__)
settings = get_settings()


async def ensure_calibration_source(db: AsyncSession, item: ClothingItem) -> str:
    """列为 NULL 时惰性补种 `_src` 并落列（Ruling 51）；返回副本相对路径。"""
    if item.calibration_original_path:
        return item.calibration_original_path
    source_path = await asyncio.to_thread(ImageService().ensure_calibration_source, item.image_path)
    item.calibration_original_path = source_path
    await db.commit()
    await db.refresh(item, attribute_names=["calibration_original_path"])
    return source_path


async def auto_calibrate(db: AsyncSession, item: ClothingItem, storage_path: Path) -> str:
    """自动校色一步；返回新的 `calibration_state`（调用方负责落列）。

    已校/已跳过（state != "none"）原样返回、不动图。检出参考物 → 校色并作废抠图；
    检不出 → "skipped"（不猜白平衡）。
    """
    if item.calibration_state != "none":
        return item.calibration_state

    source_path = await ensure_calibration_source(db, item)

    def _detect():
        # 读校色副本而不是工作图：抠图后工作图背景 RGB 已清零（Ruling 52）
        image = Image.open(storage_path / source_path).convert("RGB")
        return detect_reference(image)

    found = await asyncio.to_thread(_detect)
    if found is None:
        return "skipped"

    # box 含右下（detect_reference 契约），原样下传
    result = await asyncio.to_thread(
        ImageService().calibrate_image, item.image_path, source_path, found.box, found.kind
    )
    assign_size_paths(item, result)
    # 同 calibration API 的 _persist_image_op：校色使抠图结果失效
    item.mask_path = None
    item.original_image_path = None
    await db.commit()
    return "done"


async def ensure_cutout(db: AsyncSession, item: ClothingItem) -> bool:
    """已有 mask 则跳过（False）；否则抠图并落三档路径/备份/mask（True）。"""
    if item.mask_path:
        return False
    out = await asyncio.to_thread(ImageService().remove_background, item.image_path)
    assign_size_paths(item, out)
    item.original_image_path = out["original_backup_path"]
    item.mask_path = out["mask_path"]
    await db.commit()
    return True


async def hand_off_tagging(db: AsyncSession, item: ClothingItem, redis, *, force: bool) -> str:
    """把打标交给 tagging 队列；返回 "queued" | "deferred" | "skipped" | "error"。"""
    if not force and item.tagging_status == TaggingStatus.tagged:
        item.status = terminal_status(item.lifecycle, ItemStatus.ready)
        item.processing_kind = None
        item.ai_job_id = None
        return "skipped"

    if not settings.effective_ai_vision_enabled:
        await ItemService(db).mark_pending(item, set_ready=True)
        item.processing_kind = None
        item.ai_job_id = None
        return "deferred"

    item.status = ItemStatus.processing
    item.processing_kind = None
    item.ai_started_at = None
    try:
        job = await redis.enqueue_job(
            "tag_item_image",
            str(item.id),
            f"{settings.storage_path}/{item.image_path}",
            _queue_name=TAGGING_QUEUE,
        )
        if job is None:
            raise RuntimeError("enqueue_job returned None")
    except Exception:
        logger.exception("Failed to queue tagging for %s", item.id)
        # 打标侧失败：前端走现有打标重试
        item.status = ItemStatus.error
        item.processing_kind = None
        item.ai_raw_response = {"error": "Failed to queue tagging"}
        return "error"
    item.ai_job_id = job.job_id
    return "queued"
