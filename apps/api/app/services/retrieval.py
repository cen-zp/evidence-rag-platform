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
            limit=top_k,
        )
        if not vector_hits:
            return []

        chunk_ids = [hit.chunk_id for hit in vector_hits]
        with self._session_factory() as session:
            statement = (
                select(DocumentChunk)
                .join(Document)
                .options(selectinload(DocumentChunk.document))
                .where(
                    DocumentChunk.id.in_(chunk_ids),
                    DocumentChunk.knowledge_base_id == knowledge_base_id,
                    Document.status == DocumentStatus.READY,
                )
            )
            chunks_by_id = {chunk.id: chunk for chunk in session.scalars(statement)}

        return [
            RetrievalHit(chunk=chunks_by_id[hit.chunk_id], score=hit.score)
            for hit in vector_hits
            if hit.chunk_id in chunks_by_id
        ]


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
