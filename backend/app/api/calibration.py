"""校色 API（spec §1.2）：检出参考区、应用白平衡、手动白平衡、重置回原图。

四个端点都校验物品归属。写盘以 `calibration_original_path`（`_src.jpg`）为
不可变基准（fixes #6）：校色只重写工作图与三档，永远不碰副本。
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.schemas.item import CalibrationItemResponse, ItemResponse
from app.services.color_calibration import detect_reference
from app.services.image_service import ImageService
from app.services.item_service import ItemService
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["Calibration"])


class CalibrationApplyIn(BaseModel):
    box: list[int] = Field(min_length=4, max_length=4)
    baseline: str = Field(pattern="^(gray|white)$")


class ManualWbIn(BaseModel):
    kelvin: float = Field(ge=1500.0, le=15000.0)
    tint: float = Field(ge=-100.0, le=100.0)


class MaskStrokeIn(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    radius: int = Field(ge=1, le=512)
    mode: str = Field(pattern="^(add|subtract)$")


class MaskEditIn(BaseModel):
    strokes: list[MaskStrokeIn] = Field(min_length=1, max_length=2000)


async def _owned_item(db: AsyncSession, item_id: UUID, user_id: UUID) -> ClothingItem:
    """取物品并强制归属；他人的物品与不存在同为 404（与 items 路由同语义）。"""
    item = await ItemService(db).get_by_id(item_id, user_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return item


def _calibration_paths(item: ClothingItem) -> tuple[str, str]:
    """校色三写的前置条件：工作图与不可变副本在位，且没有在跑的后台任务。"""
    if not item.image_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item has no image",
        )
    if not item.calibration_original_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item has no calibration source",
        )

    if item.status == ItemStatus.processing and item.ai_job_id:
        # 同 remove-background：排队/在跑的 job 拥有 image_path/medium_path/
        # thumbnail_path——抢写会谁后落盘谁赢，甚至三档尺寸组撕裂。
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item has a background job in progress",
        )
    return item.image_path, item.calibration_original_path


async def _persist_image_op(
    db: AsyncSession,
    item: ClothingItem,
    op: Callable[..., dict[str, str | bool]],
    args: tuple,
    action: str,
) -> CalibrationItemResponse:
    """跑一个阻塞的图像改写，并把三个返回路径写回物品（同 rotate/remove-background语义）。"""
    try:
        # to_thread：解码/变换/重编码是阻塞 CPU 活，不能占着事件循环
        result = await asyncio.to_thread(op, *args)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    except Exception as e:
        logger.error(f"Failed to {action}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {action}",
        ) from None

    item.image_path = result["image_path"]
    item.medium_path = result["medium_path"]
    item.thumbnail_path = result["thumbnail_path"]
    # 校色从 `_src` 重推导像素，抠图结果不再对应：列只要校色跑过就清（不管原来
    # 有没有 mask），否则 update_mask 会拿过期 mask 合成垃圾。是否「真的清掉了
    # mask 文件」另由 mask_cleared 标志上报给 UI。
    item.mask_path = None
    await db.commit()
    # 只刷写过的列：整对象 refresh 会把 get_by_id 预载的 additional_images
    # 打回未加载，ItemResponse 序列化时懒加载就会炸 greenlet
    await db.refresh(
        item,
        attribute_names=[
            "image_path",
            "medium_path",
            "thumbnail_path",
            "mask_path",
            "updated_at",
        ],
    )
    return CalibrationItemResponse.model_validate(item).model_copy(
        update={"mask_cleared": bool(result.get("mask_cleared"))}
    )


@router.post("/{item_id}/calibration/detect")
async def detect_calibration_region(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    item = await _owned_item(db, item_id, current_user.id)
    if not item.image_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item has no image",
        )
    image_path = item.image_path

    def _detect() -> dict:
        image = Image.open(ImageService().get_image_path(image_path)).convert("RGB")
        found = detect_reference(image)
        if found is None:
            return {"kind": None, "box": None}
        # box 含右下（detect_reference 契约），原样下传；三联检出时把三框
        # 一起带回给 UI（Task 7 渲染用），单卡不编造 cards
        result = {"kind": found.kind, "box": list(found.box)}
        if found.cards is not None:
            result["cards"] = {k: list(v) for k, v in found.cards.items()}
        return result

    # skimage 的连通域分析是纯 CPU 阻塞活，不能占着事件循环
    return await asyncio.to_thread(_detect)


@router.post("/{item_id}/calibration/apply", response_model=CalibrationItemResponse)
async def apply_calibration(
    item_id: UUID,
    request: CalibrationApplyIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CalibrationItemResponse:
    item = await _owned_item(db, item_id, current_user.id)
    image_path, source_path = _calibration_paths(item)

    # box 含右下（detect_reference 契约），原样下传：转换只发生在 calibrate 内部
    return await _persist_image_op(
        db,
        item,
        ImageService().calibrate_image,
        (image_path, source_path, tuple(request.box), request.baseline),
        action="calibrate image",
    )


@router.post("/{item_id}/calibration/manual", response_model=CalibrationItemResponse)
async def manual_white_balance(
    item_id: UUID,
    request: ManualWbIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CalibrationItemResponse:
    item = await _owned_item(db, item_id, current_user.id)
    image_path, source_path = _calibration_paths(item)

    # 滑块范围由 Pydantic 卡；增益夹紧仍留在服务层（防御纵深）
    return await _persist_image_op(
        db,
        item,
        ImageService().manual_white_balance,
        (image_path, source_path, request.kelvin, request.tint),
        action="apply manual white balance",
    )


@router.post("/{item_id}/calibration/reset", response_model=CalibrationItemResponse)
async def reset_calibration(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CalibrationItemResponse:
    item = await _owned_item(db, item_id, current_user.id)
    image_path, source_path = _calibration_paths(item)

    return await _persist_image_op(
        db,
        item,
        ImageService().reset_calibration,
        (image_path, source_path),
        action="reset calibration",
    )


@router.post("/{item_id}/mask", response_model=ItemResponse)
async def edit_item_mask(
    item_id: UUID,
    payload: MaskEditIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    item = await _owned_item(db, item_id, current_user.id)
    if not item.mask_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item has no mask; run background removal first",
        )
    if item.status == ItemStatus.processing and item.ai_job_id:
        # 同 remove-background：job 拥有三档路径，抢写会撕裂尺寸组
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item has a background job in progress",
        )

    service = ImageService()
    try:
        result = await asyncio.to_thread(
            service.update_mask,
            item.image_path,
            item.mask_path,
            [s.model_dump() for s in payload.strokes],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from None

    item.image_path = result["image_path"]
    item.medium_path = result["medium_path"]
    item.thumbnail_path = result["thumbnail_path"]
    # mask_path 不动：我们刚改的就是这张 mask（不能走 _persist_image_op，
    # 它无条件把 mask_path 清成 None —— 那是校色的语义）
    await db.commit()
    # 只刷写过的列：整对象 refresh 会把 get_by_id 预载的 additional_images
    # 打回未加载，ItemResponse 序列化时懒加载就会炸 greenlet
    await db.refresh(
        item,
        attribute_names=[
            "image_path",
            "medium_path",
            "thumbnail_path",
            "mask_path",
            "updated_at",
        ],
    )
    return ItemResponse.model_validate(item)
