import sqlite3
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_session_factory, get_session
from app.main import create_app
from app.models import Document, DocumentChunk, DocumentStatus, KnowledgeBase
from app.services.deepseek import DeepSeekInvalidCitationError, GroundedModelResponse
from app.services.retrieval import RetrievalHit, get_knowledge_base_retriever


class StaticRetriever:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[UUID, str, int]] = []

    def search(self, knowledge_base_id: UUID, query: str, top_k: int) -> list[RetrievalHit]:
        self.calls.append((knowledge_base_id, query, top_k))
        return self.hits


class SuccessfulGroundedService:
    def __init__(self, chunk_id: UUID) -> None:
        self.chunk_id = chunk_id

    async def chat_with_evidence(self, message, evidence) -> GroundedModelResponse:
        assert message == "What is the release process?"
        assert [item.chunk_id for item in evidence] == [self.chunk_id]
        return GroundedModelResponse(
            answer="Use the documented release process.",
            citation_ids=[self.chunk_id],
            model="test-model",
            latency_ms=12,
        )


class InvalidCitationService:
    async def chat_with_evidence(self, message, evidence) -> GroundedModelResponse:
        raise DeepSeekInvalidCitationError("The model invented a citation")


def create_chat_client() -> tuple[TestClient, UUID, DocumentChunk]:
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
        knowledge_base = KnowledgeBase(name="Handbook")
        document = Document(
            knowledge_base=knowledge_base,
            filename="handbook.md",
            mime_type="text/markdown",
            status=DocumentStatus.READY,
        )
        session.add(document)
        session.flush()
        chunk = DocumentChunk(
            document=document,
            knowledge_base_id=knowledge_base.id,
            content="The release process is documented here.",
            chunk_index=0,
        )
        session.add(chunk)
        session.commit()
        knowledge_base_id = knowledge_base.id

    app = create_app(Settings(app_env="test", deepseek_api_key=None, _env_file=None))

    def override_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    return client, knowledge_base_id, chunk


def test_grounded_chat_returns_only_validated_retrieval_citations() -> None:
    client, knowledge_base_id, chunk = create_chat_client()
    retriever = StaticRetriever([RetrievalHit(chunk=chunk, score=0.9)])
    client.app.dependency_overrides[get_knowledge_base_retriever] = lambda: retriever
    client.app.state.chat_service_factory = lambda: SuccessfulGroundedService(chunk.id)

    response = client.post(
        "/api/chat",
        json={
            "message": "What is the release process?",
            "knowledge_base_id": str(knowledge_base_id),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Use the documented release process.",
        "model": "test-model",
        "latency_ms": 12,
        "citations": [
            {
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "filename": "handbook.md",
                "page_number": None,
                "chunk_index": 0,
                "content": "The release process is documented here.",
            }
        ],
    }
    assert retriever.calls == [(knowledge_base_id, "What is the release process?", 5)]


def test_grounded_chat_refuses_when_model_citations_are_invalid() -> None:
    client, knowledge_base_id, chunk = create_chat_client()
    client.app.dependency_overrides[get_knowledge_base_retriever] = lambda: StaticRetriever(
        [RetrievalHit(chunk=chunk, score=0.9)]
    )
    client.app.state.chat_service_factory = lambda: InvalidCitationService()

    response = client.post(
        "/api/chat",
        json={
            "message": "What is the release process?",
            "knowledge_base_id": str(knowledge_base_id),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "我无法根据当前检索到的资料生成带有效引用的回答。",
        "model": "retrieval-guard",
        "latency_ms": 0,
        "citations": [],
    }
