"""mask 画笔 API（fixes #12/#13）：加/减 mask，并把三档一起重生成。"""

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.calibration import get_owned_item
from app.database import get_db
from app.models.item import ItemStatus
from app.models.user import User
from app.schemas.item import ItemResponse
from app.services.image_files import assign_size_paths
from app.services.image_service import ImageService
from app.utils.auth import get_current_user

router = APIRouter(prefix="/items", tags=["Mask"])


class MaskStrokeIn(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    radius: int = Field(ge=1, le=512)
    mode: str = Field(pattern="^(add|subtract)$")


class MaskEditIn(BaseModel):
    strokes: list[MaskStrokeIn] = Field(min_length=1, max_length=2000)


@router.post("/{item_id}/mask", response_model=ItemResponse)
async def edit_item_mask(
    item_id: UUID,
    payload: MaskEditIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    item = await get_owned_item(db, item_id, current_user.id)
    if not item.mask_path or not item.original_image_path:
        # 补抠的像素取自抠图前备份；任一缺失就无从重建，让用户重抠
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
            item.original_image_path,
            [s.model_dump() for s in payload.strokes],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from None

    assign_size_paths(item, result)
    # mask_path 不动：我们刚改的就是这张 mask（校色的 _persist_image_op 会把它清成
    # None —— 那是校色的语义，这里不能复用）
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
