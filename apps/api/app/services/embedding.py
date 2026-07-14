from collections.abc import Sequence
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import get_settings


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class LocalBgeEmbedding:
    """Local sentence-transformer embeddings for Chinese-first retrieval."""

    def __init__(
        self,
        model_name: str,
        dimension: int,
        device: str,
        model: Any | None = None,
    ) -> None:
        if model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name, device=device)

        actual_dimension = model.get_embedding_dimension()
        if actual_dimension != dimension:
            raise ValueError(
                "Embedding model dimension "
                f"{actual_dimension} does not match configured {dimension}"
            )
        self.dimension = dimension
        self._model = model

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        encoded = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        values = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        vectors = [[float(value) for value in vector] for vector in values]
        if any(len(vector) != self.dimension for vector in vectors):
            raise ValueError("Embedding model returned a vector with an unexpected dimension")
        return vectors


@lru_cache
def get_embedding_provider() -> LocalBgeEmbedding:
    settings = get_settings()
    return LocalBgeEmbedding(
        model_name=settings.embedding_model,
        dimension=settings.embedding_dimension,
        device=settings.embedding_device,
    )
