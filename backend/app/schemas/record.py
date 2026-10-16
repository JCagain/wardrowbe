from datetime import date as dt_date
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.utils import garment_vocabulary
from app.services.weather_service import RECORD_CONDITIONS
from app.utils.season import RECORD_SEASONS
from app.utils.signed_urls import sign_image_url

MAX_RECORD_ITEMS = 200  # 只是请求体护栏；spec 说「任意件」


class RecordWeather(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temp_high: float | None = Field(default=None, ge=-60, le=60)
    temp_low: float | None = Field(default=None, ge=-60, le=60)
    condition: str | None = None

    @field_validator("condition")
    @classmethod
    def _condition_in_set(cls, v: str | None) -> str | None:
        if v is not None and v not in RECORD_CONDITIONS:
            raise ValueError(f"Invalid condition '{v}'")
        return v


def _check_season(v: str | None) -> str | None:
    if v is not None and v not in RECORD_SEASONS:
        raise ValueError(f"Invalid season '{v}'")
    return v


def _check_occasion(v: str | None) -> str | None:
    from app.api.outfits import VALID_OCCASIONS

    if v is None:
        return None
    v = v.strip().lower()
    if not v:
        return None
    if v not in VALID_OCCASIONS:
        raise ValueError(f"Invalid occasion '{v}'")
    return v


class RecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt_date | None = None
    season: str | None = None
    city: str | None = Field(default=None, max_length=50)
    weather: RecordWeather | None = None
    occasion: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    item_ids: list[UUID] = Field(default_factory=list, max_length=MAX_RECORD_ITEMS)

    @field_validator("season")
    @classmethod
    def _season_valid(cls, v: str | None) -> str | None:
        return _check_season(v)

    @field_validator("occasion")
    @classmethod
    def _occasion_valid(cls, v: str | None) -> str | None:
        return _check_occasion(v)


class RecordUpdate(BaseModel):
    """PATCH：只改请求里出现的键（exclude_unset）。显式 null = 清空（date 除外）。"""

    model_config = ConfigDict(extra="forbid")

    date: dt_date | None = None
    season: str | None = None
    city: str | None = Field(default=None, max_length=50)
    weather: RecordWeather | None = None
    occasion: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    item_ids: list[UUID] | None = Field(default=None, max_length=MAX_RECORD_ITEMS)

    @field_validator("date")
    @classmethod
    def _date_not_null(cls, v: dt_date | None) -> dt_date:
        if v is None:
            raise ValueError("date cannot be null")
        return v

    @field_validator("season")
    @classmethod
    def _season_valid(cls, v: str | None) -> str | None:
        return _check_season(v)

    @field_validator("occasion")
    @classmethod
    def _occasion_valid(cls, v: str | None) -> str | None:
        return _check_occasion(v)


class GarmentRegionBox(BaseModel):
    l: int
    t: int
    r: int
    b: int


class GarmentRegionOut(BaseModel):
    """Response side: no vocabulary check, so a part later removed from the editable
    vocabulary cannot 500 every record response."""

    body_part: str
    box: GarmentRegionBox
    source: Literal["auto", "manual"] = "manual"


class GarmentRegion(GarmentRegionOut):
    """Input side: body_part must be in the current vocabulary."""

    @field_validator("body_part")
    @classmethod
    def _known_part(cls, v: str) -> str:
        if v not in {p["value"] for p in garment_vocabulary.BODY_PARTS}:
            raise ValueError(f"unknown body part: {v}")
        return v


class GarmentRegionsUpdate(BaseModel):
    regions: list[GarmentRegion] = Field(max_length=12)


class GarmentRegionsResponse(BaseModel):
    photo_id: UUID
    width: int
    height: int
    regions: list[GarmentRegionOut]


class RecordPhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    image_path: str
    medium_path: str | None = None
    thumbnail_path: str | None = None
    garment_regions: list[GarmentRegionOut] | None = None

    @computed_field
    @property
    def image_url(self) -> str:
        return sign_image_url(self.image_path)

    @computed_field
    @property
    def medium_url(self) -> str | None:
        return sign_image_url(self.medium_path) if self.medium_path else None

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        return sign_image_url(self.thumbnail_path) if self.thumbnail_path else None


class RecordItemResponse(BaseModel):
    id: UUID
    type: str
    name: str | None = None
    primary_colors: list[str] = []
    thumbnail_path: str | None = None
    image_path: str | None = None

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        path = self.thumbnail_path or self.image_path
        return sign_image_url(path) if path else None


class RecordResponse(BaseModel):
    id: UUID
    date: dt_date
    season: str | None = None
    city: str | None = None
    weather: RecordWeather | None = None
    occasion: str | None = None
    notes: str | None = None
    photos: list[RecordPhotoResponse]
    items: list[RecordItemResponse]
    created_at: datetime
    updated_at: datetime


class RecordListResponse(BaseModel):
    records: list[RecordResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class RecordWeatherLookupResponse(BaseModel):
    weather: RecordWeather | None = None


class CompanionResponse(BaseModel):
    """常搭衣物（fixes #46，Ruling 70）：记录内共现次数。"""

    id: UUID
    type: str
    name: str | None = None
    primary_colors: list[str] = []
    lifecycle: str
    count: int
    thumbnail_path: str | None = Field(default=None, exclude=True)
    image_path: str | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        path = self.thumbnail_path or self.image_path
        return sign_image_url(path) if path else None


class SuggestRequest(BaseModel):
    region: GarmentRegion  # input model: body_part validated against the live vocabulary
    rerank: bool = True


class SuggestCandidate(RecordItemResponse):
    cosine: float
    verdict: Literal["same", "similar", "different"] | None = None
    lifecycle: str


class SuggestResponse(BaseModel):
    candidates: list[SuggestCandidate]
    recall_count: int
    part_filtered: bool
    reranked: bool
    rerank_error: str | None = None
