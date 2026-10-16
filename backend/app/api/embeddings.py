"""Item-vector index status, sync and rebuild (fixes #29; spec §3.2 重建入口)."""

from pathlib import Path
from typing import Annotated, Literal

from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.services.embedding_client import EmbeddingClient
from app.services.embedding_store import embedding_counts, mark_all_stale
from app.services.embedding_sync import enqueue_embedding_sync, sync_job_state
from app.utils.auth import get_current_user
from app.workers.settings import get_redis_settings

router = APIRouter(prefix="/embeddings", tags=["Embeddings"])

JobState = Literal["idle", "queued", "running"]


class EmbeddingStatus(BaseModel):
    configured: bool
    available: bool
    model: str | None
    total: int
    embedded: int
    stale: int
    job: JobState


class SyncRequest(BaseModel):
    rebuild: bool = False


class SyncResponse(BaseModel):
    queued: bool
    job: JobState


@router.get("/status", response_model=EmbeddingStatus)
async def get_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> EmbeddingStatus:
    client = EmbeddingClient.from_settings()
    if client is None:
        return EmbeddingStatus(configured=False, available=False, model=None,
                               total=0, embedded=0, stale=0, job="idle")
    total, stale = await embedding_counts(
        db, current_user.id, client.model, Path(get_settings().storage_path)
    )
    redis = await create_pool(get_redis_settings())
    try:
        job = await sync_job_state(redis, current_user.id)
    finally:
        await redis.aclose()
    return EmbeddingStatus(configured=True, available=await client.ping(), model=client.model,
                           total=total, embedded=total - stale, stale=stale, job=job)


@router.post("/sync", response_model=SyncResponse)
async def post_sync(
    body: SyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SyncResponse:
    if EmbeddingClient.from_settings() is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="embedding 未配置（AI_EMBEDDING_* 环境变量）")
    if body.rebuild:
        await mark_all_stale(db, current_user.id)
        await db.commit()  # the worker must see blanked fingerprints before it runs
    redis = await create_pool(get_redis_settings())
    try:
        queued = await enqueue_embedding_sync(redis, current_user.id)
        job = await sync_job_state(redis, current_user.id)
    finally:
        await redis.aclose()
    return SyncResponse(queued=queued, job=job)
