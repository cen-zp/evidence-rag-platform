from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol
from uuid import UUID

from app.core.config import get_settings


@dataclass(frozen=True)
class RerankResult:
    chunk_id: UUID
    score: float


class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: Sequence[tuple[UUID, str]],
    ) -> list[RerankResult]: ...


class LocalBgeReranker:
    """A local cross-encoder reranker for the top hybrid-retrieval candidates."""

    def __init__(self, model_name: str, device: str, model: Any | None = None) -> None:
        if model is None:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(model_name, device=device, max_length=512)
        self._model = model

    def rerank(
        self,
        query: str,
        candidates: Sequence[tuple[UUID, str]],
    ) -> list[RerankResult]:
        if not candidates:
            return []
        scores = self._model.predict(
            [(query, content) for _, content in candidates],
            show_progress_bar=False,
        )
        values = scores.tolist() if hasattr(scores, "tolist") else scores
        return sorted(
            [
                RerankResult(chunk_id=chunk_id, score=float(score))
                for (chunk_id, _), score in zip(candidates, values, strict=True)
            ],
            key=lambda result: result.score,
            reverse=True,
        )


@lru_cache
def get_reranker() -> LocalBgeReranker:
    settings = get_settings()
    return LocalBgeReranker(
        model_name=settings.reranker_model,
        device=settings.reranker_device,
    )
