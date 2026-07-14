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
from app.services.embedding import EmbeddingProvider, get_embedding_provider
from app.services.reranker import Reranker, get_reranker
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
        embedding_provider: EmbeddingProvider,
        reranker: Reranker | None,
        reranker_candidate_count: int,
    ) -> None:
        self._session_factory = session_factory
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider
        self._reranker = reranker
        self._reranker_candidate_count = reranker_candidate_count

    def search(self, knowledge_base_id: UUID, query: str, top_k: int) -> list[RetrievalHit]:
        vector_hits = self._vector_store.search(
            knowledge_base_id=knowledge_base_id,
            query_vector=self._embedding_provider.embed_query(query),
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
        if self._reranker is None:
            return [
                RetrievalHit(chunk=chunks_by_id[chunk_id], score=score)
                for chunk_id, score in ranked_scores[:top_k]
            ]

        rerank_candidates = [
            (chunk_id, chunks_by_id[chunk_id].content)
            for chunk_id, _ in ranked_scores[: max(top_k, self._reranker_candidate_count)]
        ]
        reranked = self._reranker.rerank(query, rerank_candidates)
        return [
            RetrievalHit(chunk=chunks_by_id[result.chunk_id], score=result.score)
            for result in reranked[:top_k]
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


def create_knowledge_base_retriever(
    reranker_enabled: bool | None = None,
) -> KnowledgeBaseRetriever:
    settings = get_settings()
    use_reranker = settings.reranker_enabled if reranker_enabled is None else reranker_enabled
    return KnowledgeBaseRetriever(
        session_factory=get_session_factory(),
        vector_store=QdrantVectorStore(
            client=QdrantClient(url=settings.qdrant_url),
            collection_name=settings.qdrant_collection,
            vector_size=settings.embedding_dimension,
        ),
        embedding_provider=get_embedding_provider(),
        reranker=get_reranker() if use_reranker else None,
        reranker_candidate_count=settings.reranker_candidate_count,
    )


@lru_cache
def get_knowledge_base_retriever() -> KnowledgeBaseRetriever:
    return create_knowledge_base_retriever()
