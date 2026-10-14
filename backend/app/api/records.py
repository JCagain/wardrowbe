from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.outfits import get_user_today
from app.database import get_db
from app.models.user import User
from app.schemas.record import (
    RecordCreate,
    RecordListResponse,
    RecordResponse,
    RecordUpdate,
    RecordWeather,
    RecordWeatherLookupResponse,
)
from app.services.image_service import ImageService
from app.services.preference_service import PreferenceService
from app.services.record_service import (
    LastPhotoError,
    PhotoNotFoundError,
    PhotoRequiredError,
    PhotoUpload,
    RecordItemsError,
    RecordNotFoundError,
    RecordService,
    record_to_response,
)
from app.services.weather_service import WeatherService
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


@router.get("/weather", response_model=RecordWeatherLookupResponse)
async def lookup_record_weather(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    city: str = Query(..., min_length=1, max_length=50),
    day: date = Query(..., alias="date"),
) -> RecordWeatherLookupResponse:
    """记录表单预填用（spec §3.1 / §10.16）。拉不到或城市不在列表里都回 null，前端留空手填。"""
    preferences = await PreferenceService(db).get_or_create_preferences(current_user.id)
    match = next(
        (c for c in PreferenceService.effective_cities(preferences) if c["name"] == city), None
    )
    if match is None:
        return RecordWeatherLookupResponse(weather=None)
    found = await WeatherService().get_weather_for_date(
        match["latitude"], match["longitude"], day, get_user_today(current_user)
    )
    return RecordWeatherLookupResponse(
        weather=RecordWeather(**found.to_dict()) if found is not None else None
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


class RotateRequest(BaseModel):
    direction: Literal["cw", "ccw"]


@router.post("/{record_id}/photos", response_model=RecordResponse)
async def add_record_photo(
    record_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    photo: UploadFile = File(...),
) -> RecordResponse:
    images = ImageService()
    upload = await read_photo(photo, images)
    try:
        outfit = await RecordService(db, images).add_photo(current_user.id, record_id, upload)
    except RecordNotFoundError:
        raise NOT_FOUND from None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return record_to_response(outfit)


@router.delete("/{record_id}/photos/{photo_id}", response_model=RecordResponse)
async def delete_record_photo(
    record_id: UUID,
    photo_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RecordResponse:
    try:
        outfit = await RecordService(db).remove_photo(current_user.id, record_id, photo_id)
    except (RecordNotFoundError, PhotoNotFoundError):
        raise NOT_FOUND from None
    except LastPhotoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="记录至少保留一张照片"
        ) from None
    return record_to_response(outfit)


@router.post("/{record_id}/photos/{photo_id}/rotate", response_model=RecordResponse)
async def rotate_record_photo(
    record_id: UUID,
    photo_id: UUID,
    body: RotateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RecordResponse:
    try:
        outfit = await RecordService(db).rotate_photo(
            current_user.id, record_id, photo_id, body.direction
        )
    except (RecordNotFoundError, PhotoNotFoundError):
        raise NOT_FOUND from None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return record_to_response(outfit)
