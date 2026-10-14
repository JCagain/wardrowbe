from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.outfits import get_user_today
from app.database import get_db
from app.models.user import User
from app.schemas.record import (
    RecordCreate,
    RecordListResponse,
    RecordResponse,
    RecordUpdate,
)
from app.services.image_service import ImageService
from app.services.record_service import (
    PhotoRequiredError,
    PhotoUpload,
    RecordItemsError,
    RecordNotFoundError,
    RecordService,
    record_to_response,
)
from app.utils.auth import get_current_user

router = APIRouter(prefix="/records", tags=["Records"])

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")


async def read_photo(upload: UploadFile, images: ImageService) -> PhotoUpload:
    content = await upload.read()
    if not images.validate_image(content, upload.content_type or "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: JPEG, PNG, WebP, HEIC",
        )
    return PhotoUpload(data=content, filename=upload.filename or "photo.jpg")


@router.post("", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
async def create_record(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    data: str = Form("{}"),
    photos: list[UploadFile] | None = File(None),
) -> RecordResponse:
    try:
        payload = RecordCreate.model_validate_json(data)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors(include_url=False, include_context=False),
        ) from None
    images = ImageService()
    uploads = [await read_photo(p, images) for p in (photos or [])]
    service = RecordService(db, images)
    try:
        outfit = await service.create(current_user, payload, uploads, get_user_today(current_user))
    except PhotoRequiredError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="至少需要一张照片"
        ) from None
    except RecordItemsError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="关联的衣物不存在"
        ) from None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return record_to_response(outfit)


@router.get("", response_model=RecordListResponse)
async def list_records(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> RecordListResponse:
    outfits, total = await RecordService(db).list(current_user.id, date_from, date_to, page, page_size)
    return RecordListResponse(
        records=[record_to_response(o) for o in outfits],
        total=total,
        page=page,
        page_size=page_size,
        has_more=page * page_size < total,
    )


@router.get("/{record_id}", response_model=RecordResponse)
async def get_record(
    record_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RecordResponse:
    try:
        return record_to_response(await RecordService(db).get(current_user.id, record_id))
    except RecordNotFoundError:
        raise NOT_FOUND from None


@router.patch("/{record_id}", response_model=RecordResponse)
async def update_record(
    record_id: UUID,
    data: RecordUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RecordResponse:
    try:
        outfit = await RecordService(db).update(current_user, record_id, data)
    except RecordNotFoundError:
        raise NOT_FOUND from None
    except RecordItemsError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="关联的衣物不存在"
        ) from None
    return record_to_response(outfit)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    record_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    try:
        await RecordService(db).delete(current_user.id, record_id)
    except RecordNotFoundError:
        raise NOT_FOUND from None
