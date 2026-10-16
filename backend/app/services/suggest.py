"""Single-box AI suggestion (spec §3.2 two-stage; D7 per-box query; never writes)."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.item import ClothingItem
from app.services.embedding_client import EmbeddingClient
from app.services.embedding_recall import load_candidates, top_k
from app.services.embedding_store import embedding_input_image
from app.services.garment_rerank import Verdict, image_to_b64_jpeg, parse_verdicts, rank_candidates

logger = logging.getLogger(__name__)

RECALL_K = 15  # spec: recall top 10-20
PART_MIN = 5  # below this many part-matching hits, top up from all parts
RERANK_GROUP = 5  # catalogue images per vision call (27B ctx 8192)
RERANK_BUDGET_SECONDS = 150  # wall budget for all rerank groups; stays under the proxy's 300 s
MAX_OUT = 8  # spec: 5-8 candidates (same cap rank_candidates applies)
QUERY_INSTRUCTION: str | None = None  # Ruling 98: decided by the probe, default off


@dataclass
class SuggestResult:
    ranked: list[tuple[ClothingItem, float, Verdict | None]]
    recall_count: int
    part_filtered: bool
    reranked: bool
    rerank_error: str | None = None


async def _recall(db, user_id, model, query, body_part) -> tuple[list[tuple[UUID, float]], bool]:
    by_part = top_k(query, await load_candidates(db, user_id, model, body_part=body_part), RECALL_K)
    if len(by_part) >= PART_MIN:
        return by_part, True
    seen = {cid for cid, _ in by_part}
    rest = [
        hit
        for hit in top_k(query, await load_candidates(db, user_id, model), RECALL_K)
        if hit[0] not in seen
    ]
    return (by_part + rest)[:RECALL_K], bool(by_part)


async def suggest_for_crop(
    db: AsyncSession,
    user_id: UUID,
    crop: Image.Image,
    body_part: str | None,
    client: EmbeddingClient,
    ai,
    rerank: bool = True,
    should_stop: Callable[[], Awaitable[bool]] | None = None,
) -> SuggestResult:
    (query,) = await client.embed_images([crop], instruction=QUERY_INSTRUCTION)
    hits, part_filtered = await _recall(db, user_id, client.model, query, body_part)
    if not hits:
        return SuggestResult([], 0, part_filtered, reranked=False)
    items = {
        i.id: i
        for i in (
            await db.execute(select(ClothingItem).where(ClothingItem.id.in_([h[0] for h in hits])))
        ).scalars()
    }
    hits = [h for h in hits if h[0] in items]
    verdicts: dict[UUID, Verdict | None] = {cid: None for cid, _ in hits}
    reranked, rerank_error = False, None
    if rerank and ai is not None:
        storage = Path(get_settings().storage_path)
        query_b64 = image_to_b64_jpeg(crop)
        errors = []
        started = time.monotonic()
        timed_out = False
        for start in range(0, len(hits), RERANK_GROUP):
            if should_stop is not None and await should_stop():
                break
            if time.monotonic() - started > RERANK_BUDGET_SECONDS:
                timed_out = True
                break
            group = []
            for cid, _ in hits[start : start + RERANK_GROUP]:
                try:
                    img = await asyncio.to_thread(embedding_input_image, items[cid], storage)
                    group.append((cid, image_to_b64_jpeg(img)))
                except (OSError, Image.DecompressionBombError) as e:  # deleted / corrupt: verdict None
                    logger.warning("rerank skips item %s: %s", cid, e)
            if not group:
                continue
            try:
                text = await ai.rerank_garment_candidates(query_b64, [b for _, b in group])
            except Exception as e:  # provider/network failure: this group stays unjudged
                errors.append(str(e))
                continue
            for (cid, _), v in zip(group, parse_verdicts(text, len(group)), strict=True):
                verdicts[cid] = v
            reranked = True
        if not reranked and timed_out:
            rerank_error = "视觉复判超时"
        elif not reranked and errors:
            rerank_error = errors[0]
    triples = [(cid, cos, verdicts[cid]) for cid, cos in hits]
    # Without verdicts keep recall order (part matches first, each by cosine); rank_candidates
    # would re-sort purely by cosine and bury the part hits under the top-up.
    ranked = rank_candidates(triples) if reranked else triples[:MAX_OUT]
    return SuggestResult(
        ranked=[(items[cid], cos, v) for cid, cos, v in ranked],
        recall_count=len(hits),
        part_filtered=part_filtered,
        reranked=reranked,
        rerank_error=rerank_error,
    )
