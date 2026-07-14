from uuid import UUID

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.services.document_processing import create_document_processor


async def process_document(ctx: dict, document_id: str, force: bool = False) -> None:
    processor = ctx.get("document_processor") or create_document_processor()
    processor.process(UUID(document_id), force=force)


class WorkerSettings:
    functions = [process_document]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
