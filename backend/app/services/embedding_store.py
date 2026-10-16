"""Archive-side embeddings: fingerprint, staleness, storage, sync (spec §3.2, fixes #29).

Staleness is detected by scanning fingerprints rather than hooking every
endpoint that rewrites item pixels (Ruling 81). Vectors are computed from the
same "current best pixels" tagging uses: the cut-out composited on white when
a mask exists or the working image has transparency (cut-outs are RGBA PNGs),
else the plain working image (Ruling 82).
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import numpy as np
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import ItemEmbedding
from app.models.item import ClothingItem, ItemStatus
from app.services.mask_service import composite_on_white

logger = logging.getLogger(__name__)


def _stat_part(storage_path: Path, rel: str | None) -> str | None:
    if not rel:
        return "-"
    p = storage_path / rel
    try:
        st = p.stat()
    except FileNotFoundError:
        return None
    return f"{rel}:{st.st_mtime_ns}:{st.st_size}"


def source_fingerprint(item: ClothingItem, storage_path: Path) -> str | None:
    work = _stat_part(storage_path, item.image_path)
    if work is None or work == "-":
        return None
    mask = _stat_part(storage_path, item.mask_path) or "-"
    return f"{work}|{mask}"


def embedding_input_image(item: ClothingItem, storage_path: Path) -> Image.Image:
    work = storage_path / item.image_path
    mask_ok = bool(item.mask_path) and (storage_path / item.mask_path).exists()
    with Image.open(work) as src:
        has_alpha = src.mode in ("RGBA", "LA") or (
            src.mode == "P" and "transparency" in src.info
        )
        if mask_ok or has_alpha:
            return composite_on_white(src.convert("RGBA"))
        return src.convert("RGB")


async def stale_items(
    db: AsyncSession, user_id: UUID, model: str, storage_path: Path
) -> list[ClothingItem]:
    rows = (
        await db.execute(
            select(ClothingItem, ItemEmbedding)
            .outerjoin(ItemEmbedding, ItemEmbedding.item_id == ClothingItem.id)
            .where(
                ClothingItem.user_id == user_id,
                ClothingItem.status.in_((ItemStatus.ready, ItemStatus.archived)),
            )
            .order_by(ClothingItem.created_at, ClothingItem.id)
        )
    ).all()
    out = []
    for item, emb in rows:
        fp = source_fingerprint(item, storage_path)
        if fp is None:
            continue
        if emb is None or emb.model != model or emb.source_fingerprint != fp:
            out.append(item)
    return out


async def upsert_embedding(
    db: AsyncSession, item_id: UUID, model: str, fingerprint: str, vector: np.ndarray
) -> None:
    v = np.asarray(vector, dtype=np.float32)
    v = v / float(np.linalg.norm(v))
    values = {
        "item_id": item_id,
        "model": model,
        "source_fingerprint": fingerprint,
        "dim": int(v.shape[0]),
        "vector": [float(x) for x in v],
        "computed_at": datetime.now(UTC),
    }
    stmt = insert(ItemEmbedding).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[ItemEmbedding.item_id],
        set_={k: stmt.excluded[k] for k in values if k != "item_id"},
    )
    await db.execute(stmt)


@dataclass
class SyncResult:
    done: int
    remaining: int
    skipped: int = 0


async def sync_item_embeddings(
    db: AsyncSession,
    user_id: UUID,
    client,
    storage_path: Path,
    batch_size: int = 8,
    deadline: float | None = None,
) -> SyncResult:
    """Embed every stale item, committing per batch so a failure resumes cleanly.

    `deadline` is a `time.monotonic()` instant; the run stops between batches once passed.
    """
    todo = await stale_items(db, user_id, client.model, storage_path)
    done = 0
    skipped = 0
    for start in range(0, len(todo), batch_size):
        if deadline is not None and time.monotonic() >= deadline:
            break
        batch = todo[start : start + batch_size]
        prepared = []
        for item in batch:
            try:
                img = embedding_input_image(item, storage_path)
            except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as e:
                logger.warning("skipping embedding for item %s: unreadable image (%s)", item.id, e)
                skipped += 1
                continue
            prepared.append((item, source_fingerprint(item, storage_path), img))
        if not prepared:
            continue
        vectors = await client.embed_images([img for _, _, img in prepared], batch_size=batch_size)
        for (item, fp, _), vec in zip(prepared, vectors, strict=True):
            await upsert_embedding(db, item.id, client.model, fp, vec)
        await db.commit()
        done += len(prepared)
    remaining = len(await stale_items(db, user_id, client.model, storage_path))
    return SyncResult(done=done, remaining=remaining, skipped=skipped)


async def mark_all_stale(db: AsyncSession, user_id: UUID) -> int:
    """Full rebuild (spec §3.2 重建入口): blank fingerprints so every vector is re-made.

    Old vectors keep serving recall until each is replaced (Ruling 94).
    """
    item_ids = select(ClothingItem.id).where(ClothingItem.user_id == user_id)
    result = await db.execute(
        update(ItemEmbedding)
        .where(ItemEmbedding.item_id.in_(item_ids))
        .values(source_fingerprint="")
    )
    return result.rowcount or 0


async def embedding_counts(
    db: AsyncSession, user_id: UUID, model: str, storage_path: Path
) -> tuple[int, int]:
    """(total eligible items with a working image, stale among them)."""
    rows = (
        await db.execute(
            select(ClothingItem).where(
                ClothingItem.user_id == user_id,
                ClothingItem.status.in_((ItemStatus.ready, ItemStatus.archived)),
            )
        )
    ).scalars().all()
    total = sum(1 for i in rows if source_fingerprint(i, storage_path) is not None)
    stale = len(await stale_items(db, user_id, model, storage_path))
    return total, stale
