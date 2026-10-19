import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.models.item import ClothingItem, ItemStatus
from app.services.item_pipeline import auto_calibrate, ensure_cutout, hand_off_tagging
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_item_pipeline_job(ctx: dict, item_id: str, force_tag: bool = False) -> dict:
    """自动校色 -> 抠图 -> 把打标交给 tagging 队列（D8）。

    已完成的步骤跳过，所以重试/重入安全。图像步骤失败时 processing_kind 保持
    "pipeline"，前端据此显示「AI 处理失败」；不写 ai_raw_response/ai_failed_at
    （不是打标失败，不能触发打标冷却）。

    取消（arq abort = task.cancel()）落在图像步骤里时，item_pipeline 会等线程写完、
    只落文件列再把取消抛出（Ruling 114）；CancelledError 不是 Exception，不会被
    下面的失败分支当成图像失败。
    """
    db = get_db_session(ctx)
    try:
        result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
        item = result.scalar_one_or_none()
        if item is None:
            logger.warning(f"Item {item_id} not found for pipeline job")
            return {"status": "error", "error": "Item not found"}

        item.ai_started_at = datetime.now(UTC)
        await db.commit()

        try:
            state = await auto_calibrate(db, item, Path(settings.storage_path))
            item.calibration_state = state
            await db.commit()
            await ensure_cutout(db, item)
            await db.commit()
        except Exception as e:
            logger.exception("Pipeline image step failed for %s", item_id)
            # 失败的 commit 会让会话停在 failed 状态；先回滚再写错误状态
            await db.rollback()
            item.status = ItemStatus.error
            item.ai_started_at = None
            await db.commit()
            return {"status": "error", "error": str(e)}

        # Ruling 116：图像步骤期间用户可能已取消 / 保存（取消端点把状态翻回 ready）。
        # 回读两列；不再是 processing/pipeline 就收手，不入队打标、不改状态。
        await db.refresh(item, attribute_names=["status", "processing_kind"])
        if item.status != ItemStatus.processing or item.processing_kind != "pipeline":
            logger.info("Pipeline for %s was cancelled before tagging hand-off", item_id)
            return {
                "status": "cancelled",
                "calibration": item.calibration_state,
                "tagging": "cancelled",
            }

        tagging = await hand_off_tagging(db, item, ctx["redis"], force=force_tag)
        await db.commit()
        return {"status": "success", "calibration": item.calibration_state, "tagging": tagging}
    finally:
        await db.close()
