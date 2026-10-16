import logging
import time
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.models.item import ClothingItem, ItemStatus
from app.services.embedding_client import EmbeddingClient, EmbeddingUnavailableError
from app.services.embedding_store import stale_items, sync_item_embeddings
from app.services.embedding_sync import enqueue_embedding_sync
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)


def _storage_path() -> Path:
    return Path(get_settings().storage_path)


async def sync_embeddings_job(ctx: dict, user_id: str) -> dict:
    """Embed this user's stale items until done or the time budget runs out."""
    client = EmbeddingClient.from_settings()
    if client is None:
        return {"status": "unconfigured"}
    deadline = time.monotonic() + get_settings().embedding_sync_budget_seconds
    db = get_db_session(ctx)
    try:
        res = await sync_item_embeddings(db, UUID(user_id), client, _storage_path(), deadline=deadline)
        return {"status": "ok", "done": res.done, "remaining": res.remaining, "skipped": res.skipped}
    except EmbeddingUnavailableError as e:
        # Committed batches stay; the cron retries once ping() succeeds again.
        logger.warning("embedding sync for %s stopped: %s", user_id, e)
        return {"status": "unavailable", "error": str(e)}
    finally:
        await db.close()


async def embedding_sync_cron(ctx: dict) -> int:
    """Every minute: enqueue a sync for each user with stale items (Ruling 92)."""
    client = EmbeddingClient.from_settings()
    if client is None or not await client.ping():
        return 0
    db = get_db_session(ctx)
    try:
        user_ids = (
            await db.execute(
                select(ClothingItem.user_id)
                .where(ClothingItem.status.in_((ItemStatus.ready, ItemStatus.archived)))
                .distinct()
            )
        ).scalars().all()
        storage = _storage_path()
        queued = 0
        for uid in user_ids:
            if await stale_items(db, uid, client.model, storage):
                # Skipped (unreadable) items stay stale forever; that only costs one
                # short no-op run per minute, never a loop (Ruling 90).
                if await enqueue_embedding_sync(ctx["redis"], uid):
                    queued += 1
        return queued
    finally:
        await db.close()
