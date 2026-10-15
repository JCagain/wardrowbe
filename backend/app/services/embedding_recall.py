"""Stage-one recall for AI-suggested linking (spec §3.2): cosine top-K in app code (D5)."""

from collections.abc import Sequence
from uuid import UUID

import numpy as np
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import ItemEmbedding
from app.models.item import ClothingItem
from app.utils import garment_vocabulary


def top_k(
    query: np.ndarray, candidates: Sequence[tuple[UUID, Sequence[float]]], k: int
) -> list[tuple[UUID, float]]:
    q = np.asarray(query, dtype=np.float32)
    norm = float(np.linalg.norm(q))
    if k <= 0 or norm == 0.0 or not candidates:
        return []
    q = q / norm
    kept = [(cid, np.asarray(vec, dtype=np.float32)) for cid, vec in candidates if len(vec) == q.shape[0]]
    if not kept:
        return []
    matrix = np.stack([v for _, v in kept])
    scores = matrix @ q
    order = np.argsort(-scores, kind="stable")[:k]
    return [(kept[i][0], float(scores[i])) for i in order]


async def load_candidates(
    db: AsyncSession, user_id: UUID, model: str, body_part: str | None = None
) -> list[tuple[UUID, list[float]]]:
    stmt = (
        select(ClothingItem.id, ClothingItem.type, ClothingItem.body_part, ItemEmbedding.vector)
        .join(ItemEmbedding, ItemEmbedding.item_id == ClothingItem.id)
        .where(ClothingItem.user_id == user_id, ItemEmbedding.model == model)
        .order_by(ClothingItem.id)
    )
    if body_part:
        types_in_part = [
            t for t, p in garment_vocabulary.BODY_PART_BY_TYPE.items() if p == body_part
        ]
        stmt = stmt.where(
            or_(
                ClothingItem.body_part == body_part,
                and_(ClothingItem.body_part.is_(None), ClothingItem.type.in_(types_in_part)),
            )
        )
    rows = (await db.execute(stmt)).all()
    return [(row.id, list(row.vector)) for row in rows]
