"""物品流水线共享步骤（D8：先 AI 处理，后录入）。

与 API 层解耦：这里抛原始异常（`ValueError` 等），由调用方决定映射成 HTTP 状态还是 job 失败。
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem
from app.services.image_service import ImageService


async def ensure_calibration_source(db: AsyncSession, item: ClothingItem) -> str:
    """列为 NULL 时惰性补种 `_src` 并落列（Ruling 51）；返回副本相对路径。"""
    if item.calibration_original_path:
        return item.calibration_original_path
    source_path = await asyncio.to_thread(ImageService().ensure_calibration_source, item.image_path)
    item.calibration_original_path = source_path
    await db.commit()
    await db.refresh(item, attribute_names=["calibration_original_path"])
    return source_path
