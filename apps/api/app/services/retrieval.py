from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import Document, DocumentChunk, DocumentStatus
from app.services.bm25 import rank_bm25
from app.services.local_hash_embedding import LocalHashEmbedding
from app.services.vector_store import QdrantVectorStore


@dataclass(frozen=True)
class RetrievalHit:
    chunk: DocumentChunk
    score: float


class KnowledgeBaseRetriever:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        vector_store: QdrantVectorStore,
        embed: Callable[[str], list[float]],
    ) -> None:
        self._session_factory = session_factory
        self._vector_store = vector_store
        self._embed = embed

    def search(self, knowledge_base_id: UUID, query: str, top_k: int) -> list[RetrievalHit]:
        vector_hits = self._vector_store.search(
            knowledge_base_id=knowledge_base_id,
            query_vector=self._embed(query),
            limit=max(top_k * 4, 20),
        )
        with self._session_factory() as session:
            statement = (
                select(DocumentChunk)
                .join(Document)
                .options(selectinload(DocumentChunk.document))
                .where(
                    DocumentChunk.knowledge_base_id == knowledge_base_id,
                    Document.status == DocumentStatus.READY,
                )
            )
            ready_chunks = list(session.scalars(statement))

        chunks_by_id = {chunk.id: chunk for chunk in ready_chunks}
        dense_ranks = {
            hit.chunk_id: rank
            for rank, hit in enumerate(vector_hits, start=1)
            if hit.chunk_id in chunks_by_id
        }
        lexical_ranks = {
            chunk_id: rank
            for rank, chunk_id in enumerate(
                rank_bm25(query, [(chunk.id, chunk.content) for chunk in ready_chunks]),
                start=1,
            )
        }
        fused_scores = _reciprocal_rank_fusion(dense_ranks, lexical_ranks)

        ranked_scores = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)
        return [
            RetrievalHit(chunk=chunks_by_id[chunk_id], score=score)
            for chunk_id, score in ranked_scores[:top_k]
        ]


def _reciprocal_rank_fusion(
    dense_ranks: dict[UUID, int],
    lexical_ranks: dict[UUID, int],
    k: int = 60,
) -> dict[UUID, float]:
    scores: dict[UUID, float] = {}
    for rankings in (dense_ranks, lexical_ranks):
        for chunk_id, rank in rankings.items():
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + rank)
    return scores


@lru_cache
def get_knowledge_base_retriever() -> KnowledgeBaseRetriever:
    settings = get_settings()
    return KnowledgeBaseRetriever(
        session_factory=get_session_factory(),
        vector_store=QdrantVectorStore(
            client=QdrantClient(url=settings.qdrant_url),
            collection_name=settings.qdrant_collection,
            vector_size=settings.embedding_dimension,
        ),
        embed=LocalHashEmbedding(settings.embedding_dimension).embed,
    )
