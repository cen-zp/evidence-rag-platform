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
    input_cost_per_million_tokens: float | None,
    output_cost_per_million_tokens: float | None,
    cost_currency: str,
) -> None:
    """Persist metadata only; never store a prompt, answer, or citation content."""
    estimated_cost = _calculate_estimated_cost(
        usage,
        input_cost_per_million_tokens,
        output_cost_per_million_tokens,
    )
    session.add(
        ModelCall(
            knowledge_base_id=knowledge_base_id,
            model=model,
            latency_ms=latency_ms,
            prompt_tokens=usage.prompt_tokens if usage is not None else None,
            completion_tokens=usage.completion_tokens if usage is not None else None,
            total_tokens=usage.total_tokens if usage is not None else None,
            input_cost_per_million_tokens=(
                input_cost_per_million_tokens if estimated_cost is not None else None
            ),
            output_cost_per_million_tokens=(
                output_cost_per_million_tokens if estimated_cost is not None else None
            ),
            estimated_cost=estimated_cost,
            cost_currency=cost_currency if estimated_cost is not None else None,
        )
    )
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Failed to record model-call metadata")


def _calculate_estimated_cost(
    usage: ChatUsage | None,
    input_cost_per_million_tokens: float | None,
    output_cost_per_million_tokens: float | None,
) -> float | None:
    if (
        usage is None
        or input_cost_per_million_tokens is None
        or output_cost_per_million_tokens is None
    ):
        return None
    return round(
        (usage.prompt_tokens * input_cost_per_million_tokens
        + usage.completion_tokens * output_cost_per_million_tokens)
        / 1_000_000,
        8,
    )
