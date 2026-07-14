import sqlite3
from uuid import UUID, uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import create_session_factory
from app.models import Document, DocumentChunk, DocumentStatus, KnowledgeBase
from app.services.bm25 import rank_bm25
from app.services.retrieval import KnowledgeBaseRetriever
from app.services.vector_store import VectorSearchHit


class FakeVectorStore:
    def __init__(self, hits: list[VectorSearchHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[UUID, list[float], int]] = []

    def search(
        self,
        knowledge_base_id: UUID,
        query_vector: list[float],
        limit: int,
    ) -> list[VectorSearchHit]:
        self.calls.append((knowledge_base_id, query_vector, limit))
        return self.hits


def test_retriever_enforces_knowledge_base_and_ready_document_filters() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: sqlite3.Connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        target_knowledge_base = KnowledgeBase(name="Target")
        other_knowledge_base = KnowledgeBase(name="Other")
        target_document = Document(
            knowledge_base=target_knowledge_base,
            filename="target.md",
            mime_type="text/markdown",
            status=DocumentStatus.READY,
        )
        other_document = Document(
            knowledge_base=other_knowledge_base,
            filename="other.md",
            mime_type="text/markdown",
            status=DocumentStatus.READY,
        )
        pending_document = Document(
            knowledge_base=target_knowledge_base,
            filename="pending.md",
            mime_type="text/markdown",
            status=DocumentStatus.PROCESSING,
        )
        session.add_all([target_document, other_document, pending_document])
        session.flush()
        target_chunk = DocumentChunk(
            document_id=target_document.id,
            knowledge_base_id=target_knowledge_base.id,
            content="target evidence",
            chunk_index=0,
        )
        other_chunk = DocumentChunk(
            document_id=other_document.id,
            knowledge_base_id=other_knowledge_base.id,
            content="other evidence",
            chunk_index=0,
        )
        pending_chunk = DocumentChunk(
            document_id=pending_document.id,
            knowledge_base_id=target_knowledge_base.id,
            content="not ready evidence",
            chunk_index=0,
        )
        session.add_all([target_chunk, other_chunk, pending_chunk])
        session.commit()

        target_knowledge_base_id = target_knowledge_base.id
        target_chunk_id = target_chunk.id
        other_chunk_id = other_chunk.id
        pending_chunk_id = pending_chunk.id

    vector_store = FakeVectorStore(
        [
            VectorSearchHit(chunk_id=other_chunk_id, score=0.99),
            VectorSearchHit(chunk_id=pending_chunk_id, score=0.95),
            VectorSearchHit(chunk_id=target_chunk_id, score=0.9),
        ]
    )
    retriever = KnowledgeBaseRetriever(
        session_factory=session_factory,
        vector_store=vector_store,
        embed=lambda query: [1.0, 0.0],
    )

    hits = retriever.search(target_knowledge_base_id, "target question", top_k=3)

    assert [hit.chunk.id for hit in hits] == [target_chunk_id]
    assert hits[0].chunk.document.filename == "target.md"
    assert hits[0].score > 0
    assert vector_store.calls == [(target_knowledge_base_id, [1.0, 0.0], 20)]

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_bm25_ranks_matching_chunk_above_unrelated_chunk() -> None:
    unrelated_chunk_id = uuid4()
    matching_chunk_id = uuid4()

    ranked_chunk_ids = rank_bm25(
        "release verification",
        [
            (unrelated_chunk_id, "meeting notes about design tokens"),
            (matching_chunk_id, "release verification checklist and release notes"),
        ],
    )

    assert ranked_chunk_ids == [matching_chunk_id]
