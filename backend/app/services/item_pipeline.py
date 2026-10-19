"""物品流水线共享步骤（D8：先 AI 处理，后录入）。

与 API 层解耦：这里抛原始异常（`ValueError` 等），由调用方决定映射成 HTTP 状态还是 job 失败。
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.item import ClothingItem, ItemStatus, TaggingStatus
from app.services.color_calibration import detect_reference
from app.services.image_files import SIZE_KEYS, assign_size_paths
from app.services.image_service import ImageService
from app.services.item_service import ItemService
from app.utils.item_lifecycle import terminal_status
from app.workers.queues import TAGGING_QUEUE

logger = logging.getLogger(__name__)
settings = get_settings()


async def _wait_out_cancellation(fut: asyncio.Future) -> bool:
    """等 `fut` 结束（成功或失败），期间到达的取消一律先吞下；返回是否被取消过。

    `asyncio.wait` 被取消时不会连带取消 `fut`；arq 的 abort 可能不止一次
    `task.cancel()`（abort 集合跨轮询才清），所以要循环吞，而不是只吞一次。
    """
    cancelled = False
    while not fut.done():
        try:
            await asyncio.wait({fut})
        except asyncio.CancelledError:
            cancelled = True
    return cancelled


async def _run_image_op(
    op: Callable[..., Any],
    args: tuple,
    on_cancel: Callable[[Any], Coroutine[Any, Any, None]],
) -> Any:
    """在线程里跑会改写磁盘的阻塞图像操作，对取消安全（Ruling 114）。

    `asyncio.to_thread` 的线程不会因任务取消而停：它照样写新文件、删旧三档。若此时
    直接让取消冒泡，DB 还指着已被删掉的文件。所以被取消时先等线程跑完；成功了就
    用 `on_cancel(结果)` 只落文件列，然后再把取消抛出去。没被取消时与
    `await asyncio.to_thread(op, *args)` 等价（线程里的异常原样上抛）。
    """
    fut = asyncio.ensure_future(asyncio.to_thread(op, *args))
    if not await _wait_out_cancellation(fut):
        return fut.result()
    if fut.cancelled():
        raise asyncio.CancelledError
    if fut.exception() is not None:
        # 已取消：不再走失败路径写 error 状态；线程失败只记日志
        logger.warning("Image op failed after cancellation: %r", fut.exception())
        raise asyncio.CancelledError
    persist = asyncio.ensure_future(on_cancel(fut.result()))
    await _wait_out_cancellation(persist)
    if not persist.cancelled() and persist.exception() is not None:
        logger.error("Failed to persist image paths after cancellation: %r", persist.exception())
    raise asyncio.CancelledError


def _persist_files_after_cancel(
    db: AsyncSession, item_id, source_image_path: str | None, **extra: Any
) -> Callable[[dict], Coroutine[Any, Any, None]]:
    """取消路径的落库：只写文件列（+ 调用方给的 extra），短事务提交。

    先 rollback 丢掉会话里任何未提交的 ORM 改动，保证这一笔绝不碰
    status/processing_kind/ai_*——那些列此时归取消端点所有。按 image_path
    做 compare-and-set：期间主图被换掉就不写（新写的文件成孤儿，只是磁盘泄漏）。
    """

    async def persist(result: dict) -> None:
        values = {k: result[k] for k in SIZE_KEYS if k in result}
        if "original_backup_path" in result:
            values["original_image_path"] = result["original_backup_path"]
        if "mask_path" in result:
            values["mask_path"] = result["mask_path"]
        values.update(extra)
        await db.rollback()
        await db.execute(
            update(ClothingItem)
            .where(ClothingItem.id == item_id, ClothingItem.image_path == source_image_path)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await db.commit()

    return persist


async def ensure_calibration_source(db: AsyncSession, item: ClothingItem) -> str:
    """列为 NULL 时惰性补种 `_src` 并落列（Ruling 51）；返回副本相对路径。"""
    if item.calibration_original_path:
        return item.calibration_original_path

    item_id, image_path = item.id, item.image_path

    def on_cancel_persist(source: str):
        return _persist_files_after_cancel(
            db, item_id, image_path, calibration_original_path=source
        )({})

    source_path = await _run_image_op(
        ImageService().ensure_calibration_source, (image_path,), on_cancel_persist
    )
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
    if item.mask_path:
        # Ruling 115：已有抠图（可能还带画笔修过的 mask）时不自动校色——校色会作废
        # 抠图，而流水线不该替用户重抠。像素不动，状态留 "none"，用户可手动校色。
        return "none"

    source_path = await ensure_calibration_source(db, item)

    def _detect():
        # 读校色副本而不是工作图：抠图后工作图背景 RGB 已清零（Ruling 52）
        image = Image.open(storage_path / source_path).convert("RGB")
        return detect_reference(image)

    found = await asyncio.to_thread(_detect)
    if found is None:
        return "skipped"

    # box 含右下（detect_reference 契约），原样下传
    result = await _run_image_op(
        ImageService().calibrate_image,
        (item.image_path, source_path, found.box, found.kind),
        _persist_files_after_cancel(
            db,
            item.id,
            item.image_path,
            mask_path=None,
            original_image_path=None,
            calibration_state="done",
        ),
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
    out = await _run_image_op(
        ImageService().remove_background,
        (item.image_path,),
        _persist_files_after_cancel(db, item.id, item.image_path),
    )
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
        item.ai_started_at = None
        return "skipped"

    if not settings.effective_ai_vision_enabled:
        await ItemService(db).mark_pending(item, set_ready=True)
        item.processing_kind = None
        item.ai_job_id = None
        item.ai_started_at = None
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
