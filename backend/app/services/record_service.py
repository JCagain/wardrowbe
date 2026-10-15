"""记录（穿搭日志，spec §3.1）：存 outfits（source=record）+ outfit_photos。

计数规则（spec §5 / fixes #23 #28 #44）：wear_count 是唯一计数源，只做增量——关联新增 +1、
移除 −1（下限 0）、删除记录对其全部衣物 −1；item_history 每条关联一行，作反查数据源；
last_worn_at = 该衣物 item_history 的最大 worn_at。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.models.item import ClothingItem, ItemHistory
from app.models.outfit import Outfit, OutfitItem, OutfitPhoto, OutfitSource, OutfitStatus
from app.models.user import User
from app.schemas.record import (
    RecordCreate,
    RecordItemResponse,
    RecordPhotoResponse,
    RecordResponse,
    RecordUpdate,
    RecordWeather,
)
from app.services.image_files import assign_size_paths
from app.services.image_service import ImageService
from app.utils.clothing import canonical_item_order
from app.utils.season import season_for_date


class RecordNotFoundError(LookupError):
    pass


class RecordItemsError(ValueError):
    pass


class PhotoRequiredError(ValueError):
    pass


class PhotoNotFoundError(LookupError):
    pass


class LastPhotoError(ValueError):
    pass


@dataclass
class PhotoUpload:
    data: bytes
    filename: str


def _weather_dict(weather: RecordWeather | dict | None) -> dict | None:
    if weather is None:
        return None
    data = weather.model_dump() if isinstance(weather, RecordWeather) else dict(weather)
    if all(data.get(k) is None for k in ("temp_high", "temp_low", "condition")):
        return None
    return data


def record_to_response(outfit: Outfit) -> RecordResponse:
    items = [
        RecordItemResponse(
            id=oi.item.id,
            type=oi.item.type,
            name=oi.item.name,
            primary_colors=list(oi.item.primary_colors or []),
            thumbnail_path=oi.item.thumbnail_path,
            image_path=oi.item.image_path,
        )
        for oi in sorted(outfit.items, key=lambda x: x.position)
    ]
    return RecordResponse(
        id=outfit.id,
        date=outfit.scheduled_for,
        season=outfit.season,
        city=outfit.city,
        weather=RecordWeather(**outfit.weather_data) if outfit.weather_data else None,
        occasion=outfit.occasion,
        notes=outfit.notes,
        photos=[RecordPhotoResponse.model_validate(p) for p in outfit.photos],
        items=items,
        created_at=outfit.created_at,
        updated_at=outfit.updated_at,
    )


class RecordService:
    def __init__(self, db: AsyncSession, image_service: ImageService | None = None):
        self.db = db
        self.images = image_service or ImageService()

    # ---- 读 ----

    async def _load(self, user_id: UUID, record_id: UUID) -> Outfit:
        result = await self.db.execute(
            select(Outfit)
            .where(
                and_(
                    Outfit.id == record_id,
                    Outfit.user_id == user_id,
                    Outfit.source == OutfitSource.record,
                )
            )
            .options(
                selectinload(Outfit.photos),
                selectinload(Outfit.items).selectinload(OutfitItem.item),
            )
            .execution_options(populate_existing=True)
        )
        outfit = result.scalar_one_or_none()
        if outfit is None:
            raise RecordNotFoundError(str(record_id))
        return outfit

    async def get(self, user_id: UUID, record_id: UUID) -> Outfit:
        return await self._load(user_id, record_id)

    async def list(
        self,
        user_id: UUID,
        date_from: date | None,
        date_to: date | None,
        page: int,
        page_size: int,
        item_id: UUID | None = None,
    ) -> tuple[list[Outfit], int]:
        conds = [Outfit.user_id == user_id, Outfit.source == OutfitSource.record]
        if date_from is not None:
            conds.append(Outfit.scheduled_for >= date_from)
        if date_to is not None:
            conds.append(Outfit.scheduled_for <= date_to)
        if item_id is not None:
            conds.append(
                Outfit.id.in_(select(OutfitItem.outfit_id).where(OutfitItem.item_id == item_id))
            )
        total = (
            await self.db.execute(select(func.count()).select_from(Outfit).where(and_(*conds)))
        ).scalar_one()
        result = await self.db.execute(
            select(Outfit)
            .where(and_(*conds))
            .options(
                selectinload(Outfit.photos),
                selectinload(Outfit.items).selectinload(OutfitItem.item),
            )
            .order_by(Outfit.scheduled_for.desc(), Outfit.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def companions(
        self, user_id: UUID, item_id: UUID, limit: int
    ) -> list[tuple[ClothingItem, int]]:
        """与 item 同在一条记录里的其它衣物，按共同记录数降序，同数按 id。

        只看 source=record（Ruling 70）；退役衣物照常计入，由前端标注。
        """
        me = aliased(OutfitItem)
        other = aliased(OutfitItem)
        shared = func.count(func.distinct(me.outfit_id)).label("shared")
        result = await self.db.execute(
            select(ClothingItem, shared)
            .select_from(me)
            .join(Outfit, Outfit.id == me.outfit_id)
            .join(other, and_(other.outfit_id == me.outfit_id, other.item_id != item_id))
            .join(ClothingItem, ClothingItem.id == other.item_id)
            .where(
                me.item_id == item_id,
                Outfit.user_id == user_id,
                Outfit.source == OutfitSource.record,
            )
            .group_by(ClothingItem.id)
            .order_by(shared.desc(), ClothingItem.id.asc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()]

    # ---- 衣物与计数 ----

    async def _validate_items(self, user_id: UUID, item_ids: list[UUID]) -> list[UUID]:
        unique = list(dict.fromkeys(item_ids))
        if not unique:
            return []
        result = await self.db.execute(
            select(ClothingItem.id, ClothingItem.type).where(
                and_(ClothingItem.id.in_(unique), ClothingItem.user_id == user_id)
            )
        )
        rows = result.all()
        if len(rows) != len(unique):
            raise RecordItemsError("one or more items not found")
        type_map = {row.id: (row.type or "") for row in rows}
        return canonical_item_order(unique, type_map)

    async def _set_outfit_items(self, outfit_id: UUID, ordered_ids: list[UUID]) -> None:
        await self.db.execute(delete(OutfitItem).where(OutfitItem.outfit_id == outfit_id))
        for pos, iid in enumerate(ordered_ids):
            self.db.add(OutfitItem(outfit_id=outfit_id, item_id=iid, position=pos))
        await self.db.flush()

    async def _add_wear(
        self, outfit_id: UUID, item_ids: list[UUID], day: date, occasion: str | None
    ) -> None:
        if not item_ids:
            return
        await self.db.execute(
            update(ClothingItem)
            .where(ClothingItem.id.in_(item_ids))
            .values(wear_count=func.coalesce(ClothingItem.wear_count, 0) + 1)
            .execution_options(synchronize_session=False)
        )
        for iid in item_ids:
            self.db.add(ItemHistory(item_id=iid, outfit_id=outfit_id, worn_at=day, occasion=occasion))
        await self.db.flush()

    async def _remove_wear(self, outfit_id: UUID, item_ids: list[UUID]) -> None:
        if not item_ids:
            return
        await self.db.execute(
            delete(ItemHistory).where(
                and_(ItemHistory.outfit_id == outfit_id, ItemHistory.item_id.in_(item_ids))
            )
        )
        await self.db.execute(
            update(ClothingItem)
            .where(ClothingItem.id.in_(item_ids))
            .values(wear_count=func.greatest(func.coalesce(ClothingItem.wear_count, 0) - 1, 0))
            .execution_options(synchronize_session=False)
        )
        await self.db.flush()

    async def _recompute_last_worn(self, item_ids: set[UUID]) -> None:
        if not item_ids:
            return
        latest = (
            select(func.max(ItemHistory.worn_at))
            .where(ItemHistory.item_id == ClothingItem.id)
            .correlate(ClothingItem)
            .scalar_subquery()
        )
        await self.db.execute(
            update(ClothingItem)
            .where(ClothingItem.id.in_(item_ids))
            .values(last_worn_at=latest)
            .execution_options(synchronize_session=False)
        )
        await self.db.flush()

    # ---- 照片 ----

    async def _store_photos(self, user_id: UUID, photos: list[PhotoUpload]) -> list[dict]:
        stored: list[dict] = []
        try:
            for photo in photos:
                paths = await self.images.process_and_store(
                    user_id=user_id,
                    image_data=photo.data,
                    original_filename=photo.filename,
                    keep_source=False,  # 记录照不校色不抠图（用户裁定 2026-10-14）
                )
                stored.append(paths)
        except Exception:
            for paths in stored:
                self.images.delete_images(paths)
            raise
        return stored

    # ---- 写 ----

    async def create(self, user: User, data: RecordCreate, photos: list[PhotoUpload], today: date) -> Outfit:
        if not photos:
            raise PhotoRequiredError("at least one photo is required")
        item_ids = await self._validate_items(user.id, data.item_ids)
        day = data.date or today
        stored = await self._store_photos(user.id, photos)

        outfit = Outfit(
            user_id=user.id,
            source=OutfitSource.record,
            status=OutfitStatus.accepted,
            scheduled_for=day,
            season=data.season or season_for_date(day),
            city=data.city,
            weather_data=_weather_dict(data.weather),
            occasion=data.occasion,
            notes=data.notes,
        )
        self.db.add(outfit)
        await self.db.flush()

        for pos, paths in enumerate(stored):
            self.db.add(
                OutfitPhoto(
                    outfit_id=outfit.id,
                    position=pos,
                    image_path=paths["image_path"],
                    medium_path=paths.get("medium_path"),
                    thumbnail_path=paths.get("thumbnail_path"),
                )
            )
        await self._set_outfit_items(outfit.id, item_ids)
        await self._add_wear(outfit.id, item_ids, day, data.occasion)
        await self._recompute_last_worn(set(item_ids))
        return await self._load(user.id, outfit.id)

    async def update(self, user: User, record_id: UUID, data: RecordUpdate) -> Outfit:
        outfit = await self._load(user.id, record_id)
        fields = data.model_dump(exclude_unset=True)
        old_ids = [oi.item_id for oi in outfit.items]
        affected: set[UUID] = set()

        if "date" in fields and fields["date"] != outfit.scheduled_for:
            outfit.scheduled_for = fields["date"]
            await self.db.execute(
                update(ItemHistory)
                .where(ItemHistory.outfit_id == outfit.id)
                .values(worn_at=fields["date"])
            )
            affected.update(old_ids)
            # 改日期 → 季节跟着重推导（用户裁定 2026-10-14）；同一请求里手给的季节优先
            if "season" not in fields:
                outfit.season = season_for_date(fields["date"])
        if "season" in fields:
            outfit.season = fields["season"]
        if "city" in fields:
            outfit.city = fields["city"]
        if "weather" in fields:
            outfit.weather_data = _weather_dict(fields["weather"])
        if "notes" in fields:
            outfit.notes = fields["notes"]
        if "occasion" in fields:
            outfit.occasion = fields["occasion"]
            await self.db.execute(
                update(ItemHistory)
                .where(ItemHistory.outfit_id == outfit.id)
                .values(occasion=fields["occasion"])
            )
        await self.db.flush()

        if fields.get("item_ids") is not None:
            new_ids = await self._validate_items(user.id, fields["item_ids"])
            added = [i for i in new_ids if i not in set(old_ids)]
            removed = [i for i in old_ids if i not in set(new_ids)]
            await self._set_outfit_items(outfit.id, new_ids)
            await self._remove_wear(outfit.id, removed)
            await self._add_wear(outfit.id, added, outfit.scheduled_for, outfit.occasion)
            affected.update(added)
            affected.update(removed)

        await self._recompute_last_worn(affected)
        return await self._load(user.id, outfit.id)

    async def delete(self, user_id: UUID, record_id: UUID) -> None:
        outfit = await self._load(user_id, record_id)
        item_ids = [oi.item_id for oi in outfit.items]
        photo_paths = [
            {"image_path": p.image_path, "medium_path": p.medium_path, "thumbnail_path": p.thumbnail_path}
            for p in outfit.photos
        ]
        await self._remove_wear(outfit.id, item_ids)
        await self.db.delete(outfit)
        await self.db.flush()
        await self._recompute_last_worn(set(item_ids))
        # 文件最后删：DB 失败回滚时照片还在。
        for paths in photo_paths:
            self.images.delete_images(paths)

    def _find_photo(self, outfit: Outfit, photo_id: UUID) -> OutfitPhoto:
        for photo in outfit.photos:
            if photo.id == photo_id:
                return photo
        raise PhotoNotFoundError(str(photo_id))

    async def add_photo(self, user_id: UUID, record_id: UUID, photo: PhotoUpload) -> Outfit:
        outfit = await self._load(user_id, record_id)
        (paths,) = await self._store_photos(user_id, [photo])
        next_pos = max((p.position for p in outfit.photos), default=-1) + 1
        self.db.add(
            OutfitPhoto(
                outfit_id=outfit.id,
                position=next_pos,
                image_path=paths["image_path"],
                medium_path=paths.get("medium_path"),
                thumbnail_path=paths.get("thumbnail_path"),
            )
        )
        await self.db.flush()
        return await self._load(user_id, record_id)

    async def remove_photo(self, user_id: UUID, record_id: UUID, photo_id: UUID) -> Outfit:
        outfit = await self._load(user_id, record_id)
        photo = self._find_photo(outfit, photo_id)
        if len(outfit.photos) <= 1:
            raise LastPhotoError("a record keeps at least one photo")
        paths = {
            "image_path": photo.image_path,
            "medium_path": photo.medium_path,
            "thumbnail_path": photo.thumbnail_path,
        }
        outfit.photos.remove(photo)  # delete-orphan
        for pos, p in enumerate(outfit.photos):
            p.position = pos
        await self.db.flush()
        self.images.delete_images(paths)
        return await self._load(user_id, record_id)

    async def rotate_photo(
        self, user_id: UUID, record_id: UUID, photo_id: UUID, direction: str
    ) -> Outfit:
        outfit = await self._load(user_id, record_id)
        photo = self._find_photo(outfit, photo_id)
        paths = self.images.rotate_image(photo.image_path, direction)
        assign_size_paths(photo, paths)
        await self.db.flush()
        return await self._load(user_id, record_id)
