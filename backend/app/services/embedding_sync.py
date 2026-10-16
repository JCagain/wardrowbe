"""Embedding sync job plumbing shared by the API and the image worker (fixes #29)."""

from typing import Literal
from uuid import UUID

from arq.jobs import Job, JobStatus

from app.workers.queues import IMAGE_QUEUE

SYNC_JOB_NAME = "sync_embeddings_job"


def sync_job_id(user_id: UUID | str) -> str:
    # One id per user: arq refuses to enqueue a second job with a live id, which is
    # the dedupe. The job is registered with keep_result=0 so the id frees on finish.
    return f"embedding-sync:{user_id}"


async def enqueue_embedding_sync(redis, user_id: UUID | str) -> bool:
    job = await redis.enqueue_job(
        SYNC_JOB_NAME, str(user_id), _job_id=sync_job_id(user_id), _queue_name=IMAGE_QUEUE
    )
    return job is not None


async def sync_job_state(redis, user_id: UUID | str) -> Literal["idle", "queued", "running"]:
    status = await Job(sync_job_id(user_id), redis, _queue_name=IMAGE_QUEUE).status()
    if status in (JobStatus.queued, JobStatus.deferred):
        return "queued"
    if status == JobStatus.in_progress:
        return "running"
    return "idle"
