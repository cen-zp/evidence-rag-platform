from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import HTTPException, Request, status

from app.core.config import get_settings


class DocumentTaskQueue(Protocol):
    async def enqueue_job(self, function: str, *args: str) -> object: ...


async def get_document_task_queue(request: Request) -> ArqRedis:
    queue = getattr(request.app.state, "document_task_queue", None)
    if queue is not None:
        return queue

    try:
        queue = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document queue is unavailable. Start Redis and try again.",
        ) from error

    request.app.state.document_task_queue = queue
    return queue


async def close_document_task_queue(app: object) -> None:
    queue = getattr(app.state, "document_task_queue", None)
    if queue is not None:
        await queue.close()
