import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ModelCall
from app.schemas.chat import ChatUsage

logger = logging.getLogger(__name__)


def record_model_call(
    session: Session,
    knowledge_base_id: UUID,
    *,
    model: str,
    latency_ms: int,
    usage: ChatUsage | None,
) -> None:
    """Persist metadata only; never store a prompt, answer, or citation content."""
    session.add(
        ModelCall(
            knowledge_base_id=knowledge_base_id,
            model=model,
            latency_ms=latency_ms,
            prompt_tokens=usage.prompt_tokens if usage is not None else None,
            completion_tokens=usage.completion_tokens if usage is not None else None,
            total_tokens=usage.total_tokens if usage is not None else None,
        )
    )
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Failed to record model-call metadata")
