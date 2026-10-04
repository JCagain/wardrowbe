from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, computed_field
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import Outfit
from app.models.user import User
from app.utils.auth import get_current_user
from app.utils.clothing import WardrobeComposition, count_composition, first_primary
from app.utils.signed_urls import sign_image_url

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class ColorDistribution(BaseModel):
    color: str
    count: int
    percentage: float


class TypeDistribution(BaseModel):
    type: str
    count: int
    percentage: float


class WearStats(BaseModel):
    id: UUID
    name: str | None
    type: str
    primary_color: str | None
    thumbnail_path: str | None
    wear_count: int
    last_worn_at: date | None

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class WardrobeStats(BaseModel):
    total_items: int
    items_by_status: dict[str, int]
    total_outfits: int
    outfits_this_week: int
    outfits_this_month: int
    total_wears: int


class AnalyticsResponse(BaseModel):
    wardrobe: WardrobeStats
    color_distribution: list[ColorDistribution]
    type_distribution: list[TypeDistribution]
    most_worn: list[WearStats]
    least_worn: list[WearStats]
    never_worn: list[WearStats]


# 摘不删（spec §7）：insights 搭配建议已从统计页下线，启发式保留备查。
def composition_insights(c: WardrobeComposition) -> list[str]:
    # Layers (cardigans, vests) need something underneath, so they are judged against
    # base tops rather than counted as tops themselves. Dresses count as something to
    # layer over too, because cardigans and vests are worn over dresses as often as over shirts.
    if c.layers >= 3 and c.layers > 2 * (c.base_tops + c.full_body):
        return [
            "Most of your tops are layers like cardigans and vests. Add a few basics to wear under them!"
        ]

    # A dress-first wardrobe doesn't need its few separates to balance.
    if c.full_body >= c.base_tops + c.bottoms:
        return []

    if c.base_tops > 0 and c.bottoms > 0:
        ratio = c.base_tops / c.bottoms
        if ratio > 3:
            return ["You have many more tops than bottoms. Consider adding pants or skirts!"]
        if ratio < 0.5:
            return ["You have more bottoms than tops. Consider adding some shirts!"]
    return []


def _wear_stats(item: ClothingItem) -> WearStats:
    return WearStats(
        id=item.id,
        name=item.name,
        type=item.type,
        primary_color=first_primary(item.primary_colors),
        thumbnail_path=item.thumbnail_path,
        wear_count=item.wear_count,
        last_worn_at=item.last_worn_at,
    )


@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AnalyticsResponse:
    # Calculate date ranges
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # === Wardrobe Stats ===
    # Total items and status breakdown
    items_query = select(
        func.count(ClothingItem.id).label("total"),
        func.sum(case((ClothingItem.status == ItemStatus.ready, 1), else_=0)).label("ready"),
        func.sum(case((ClothingItem.status == ItemStatus.processing, 1), else_=0)).label(
            "processing"
        ),
        func.sum(case((ClothingItem.status == ItemStatus.archived, 1), else_=0)).label("archived"),
        func.sum(case((ClothingItem.status == ItemStatus.error, 1), else_=0)).label("error"),
        func.sum(ClothingItem.wear_count).label("total_wears"),
    ).where(ClothingItem.user_id == current_user.id)

    items_result = await db.execute(items_query)
    items_row = items_result.one()

    total_items = items_row.total or 0
    items_by_status = {
        "ready": items_row.ready or 0,
        "processing": items_row.processing or 0,
        "archived": items_row.archived or 0,
        "error": items_row.error or 0,
    }
    total_wears = items_row.total_wears or 0

    # Outfit stats
    outfits_query = select(
        func.count(Outfit.id).label("total"),
        func.sum(case((Outfit.created_at >= week_ago, 1), else_=0)).label("this_week"),
        func.sum(case((Outfit.created_at >= month_ago, 1), else_=0)).label("this_month"),
    ).where(Outfit.user_id == current_user.id)

    outfits_result = await db.execute(outfits_query)
    outfits_row = outfits_result.one()

    wardrobe_stats = WardrobeStats(
        total_items=total_items,
        items_by_status=items_by_status,
        total_outfits=outfits_row.total or 0,
        outfits_this_week=outfits_row.this_week or 0,
        outfits_this_month=outfits_row.this_month or 0,
        total_wears=total_wears,
    )

    ready_items = items_by_status["ready"]

    # === Color Distribution ===
    # Per spec §10.15: count by 件次 over primary colors only — an item with two
    # primaries counts once in each, secondaries never count. Percentages stay a
    # share of ready items, so the sum can exceed 100% for multi-primary closets.
    color_query = (
        select(
            func.unnest(ClothingItem.primary_colors).label("color"),
            func.count().label("count"),
        )
        .where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.status == ItemStatus.ready,
            )
        )
        .group_by("color")
        .order_by(func.count().desc())
        .limit(10)
    )
    color_result = await db.execute(color_query)
    color_rows = color_result.all()

    color_distribution = [
        ColorDistribution(
            color=row.color,
            count=row.count,
            percentage=round(row.count / ready_items * 100, 1) if ready_items > 0 else 0,
        )
        for row in color_rows
    ]

    # === Type Distribution ===
    type_query = (
        select(
            ClothingItem.type,
            func.count(ClothingItem.id).label("count"),
        )
        .where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.status == ItemStatus.ready,
            )
        )
        .group_by(ClothingItem.type)
        .order_by(func.count(ClothingItem.id).desc())
    )
    type_result = await db.execute(type_query)
    type_rows = type_result.all()

    type_distribution = [
        TypeDistribution(
            type=row.type,
            count=row.count,
            percentage=round(row.count / ready_items * 100, 1) if ready_items > 0 else 0,
        )
        for row in type_rows
    ]

    # === Most/Least/Never Worn ===
    def wear_stats_query(order_desc: bool, limit: int, never_worn: bool = False):
        q = select(ClothingItem).where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.status == ItemStatus.ready,
            )
        )
        if never_worn:
            q = q.where(ClothingItem.wear_count == 0)
            q = q.order_by(ClothingItem.created_at.desc())
        elif order_desc:
            q = q.where(ClothingItem.wear_count > 0)
            q = q.order_by(ClothingItem.wear_count.desc())
        else:
            q = q.where(ClothingItem.wear_count > 0)
            q = q.order_by(ClothingItem.wear_count.asc())
        return q.limit(limit)

    most_worn_result = await db.execute(wear_stats_query(order_desc=True, limit=5))
    most_worn = [_wear_stats(item) for item in most_worn_result.scalars().all()]

    least_worn_result = await db.execute(wear_stats_query(order_desc=False, limit=5))
    least_worn = [_wear_stats(item) for item in least_worn_result.scalars().all()]

    never_worn_result = await db.execute(
        wear_stats_query(order_desc=False, limit=5, never_worn=True)
    )
    never_worn = [_wear_stats(item) for item in never_worn_result.scalars().all()]

    return AnalyticsResponse(
        wardrobe=wardrobe_stats,
        color_distribution=color_distribution,
        type_distribution=type_distribution,
        most_worn=most_worn,
        least_worn=least_worn,
        never_worn=never_worn,
    )
