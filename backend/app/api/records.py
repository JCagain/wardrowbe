import asyncio
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from PIL import Image
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.outfits import get_user_today
from app.config import get_settings
from app.database import get_db
from app.models.preference import UserPreference
from app.models.user import User
from app.schemas.record import (
    GarmentRegionsResponse,
    GarmentRegionsUpdate,
    RecordCreate,
    RecordListResponse,
    RecordResponse,
    RecordUpdate,
    RecordWeather,
    RecordWeatherLookupResponse,
    SuggestCandidate,
    SuggestRequest,
    SuggestResponse,
)
from app.services import suggest as suggest_service
from app.services.ai_service import AIDisabledError, AIService, require_internal_ai
from app.services.embedding_client import EmbeddingClient, EmbeddingUnavailableError
from app.services.garment_regions import clamp_regions, is_parseable, parse_garment_regions
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
    item_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> RecordListResponse:
    outfits, total = await RecordService(db).list(
        current_user.id, date_from, date_to, page, page_size, item_id=item_id
    )
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


def _photo_size(rel_path: str) -> tuple[int, int]:
    with Image.open(Path(get_settings().storage_path) / rel_path) as im:
        return im.size


def _crop_photo(rel_path: str, box: dict) -> Image.Image:
    with Image.open(Path(get_settings().storage_path) / rel_path) as im:
        return im.convert("RGB").crop((box["l"], box["t"], box["r"] + 1, box["b"] + 1))


async def _user_ai_endpoints(db: AsyncSession, user_id) -> list[dict] | None:
    # CLAUDE.md pitfall 3: settings-page endpoints take priority (same as the tagging worker).
    prefs = (
        await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    ).scalar_one_or_none()
    return prefs.ai_endpoints if prefs and prefs.ai_endpoints else None


@router.post(
    "/{record_id}/photos/{photo_id}/garment-regions/detect",
    response_model=GarmentRegionsResponse,
)
async def detect_garment_regions(
    record_id: UUID,
    photo_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GarmentRegionsResponse:
    service = RecordService(db)
    try:
        photo = await service.get_photo_for_user(current_user.id, record_id, photo_id)
    except (RecordNotFoundError, PhotoNotFoundError):
        raise NOT_FOUND from None
    try:
        require_internal_ai("vision")
        ai = AIService(endpoints=await _user_ai_endpoints(db, current_user.id))
    except AIDisabledError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from None
    storage = Path(get_settings().storage_path)
    try:
        raw = await ai.detect_garment_regions(storage / photo.image_path)
    except Exception as e:  # provider/network failure
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"检出失败：{e}") from None
    width, height = _photo_size(photo.image_path)
    if not is_parseable(raw):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="模型没有返回可解析的框")
    regions = parse_garment_regions(raw, width, height)
    # Detect only returns; PUT is the sole writer, so cancelling never changes stored boxes.
    return GarmentRegionsResponse(photo_id=photo.id, width=width, height=height, regions=regions)


@router.put(
    "/{record_id}/photos/{photo_id}/garment-regions",
    response_model=GarmentRegionsResponse,
)
async def put_garment_regions(
    record_id: UUID,
    photo_id: UUID,
    body: GarmentRegionsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GarmentRegionsResponse:
    service = RecordService(db)
    try:
        photo = await service.get_photo_for_user(current_user.id, record_id, photo_id)
    except (RecordNotFoundError, PhotoNotFoundError):
        raise NOT_FOUND from None
    width, height = _photo_size(photo.image_path)
    regions = clamp_regions([r.model_dump() for r in body.regions], width, height)
    photo = await service.save_garment_regions(current_user.id, record_id, photo_id, regions)
    return GarmentRegionsResponse(photo_id=photo.id, width=width, height=height, regions=regions)


@router.post("/{record_id}/photos/{photo_id}/suggest", response_model=SuggestResponse)
async def suggest_for_region(
    record_id: UUID,
    photo_id: UUID,
    body: SuggestRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SuggestResponse:
    """Spec §3.2: candidates only — nothing is linked or written here."""
    service = RecordService(db)
    try:
        photo = await service.get_photo_for_user(current_user.id, record_id, photo_id)
    except (RecordNotFoundError, PhotoNotFoundError):
        raise NOT_FOUND from None
    client = EmbeddingClient.from_settings()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="embedding 未配置（AI_EMBEDDING_* 环境变量）",
        )
    unreadable = HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="照片读不了"
    )
    try:
        width, height = await asyncio.to_thread(_photo_size, photo.image_path)
    except (OSError, Image.DecompressionBombError):
        raise unreadable from None
    clamped = clamp_regions([body.region.model_dump()], width, height)
    if not clamped:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="框太小或在图外")
    try:
        crop = await asyncio.to_thread(_crop_photo, photo.image_path, clamped[0]["box"])
    except (OSError, Image.DecompressionBombError):
        raise unreadable from None
    ai = None
    if body.rerank:
        try:
            require_internal_ai("vision")
            ai = AIService(endpoints=await _user_ai_endpoints(db, current_user.id))
        except AIDisabledError:
            ai = None
    try:
        res = await suggest_service.suggest_for_crop(
            db, current_user.id, crop, body.region.body_part, client, ai,
            rerank=body.rerank, should_stop=request.is_disconnected,
        )
    except EmbeddingUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"embedding 服务不可用：{e}"
        ) from None
    rerank_error = res.rerank_error
    if body.rerank and ai is None:
        rerank_error = "视觉端点未启用，仅按相似度排序"
    return SuggestResponse(
        candidates=[
            SuggestCandidate(
                id=item.id, type=item.type, name=item.name,
                primary_colors=list(item.primary_colors or []),
                thumbnail_path=item.thumbnail_path, image_path=item.image_path,
                cosine=cos, verdict=v, lifecycle=item.lifecycle,
            )
            for item, cos, v in res.ranked
        ],
        recall_count=res.recall_count,
        part_filtered=res.part_filtered,
        reranked=res.reranked,
        rerank_error=rerank_error,
    )
