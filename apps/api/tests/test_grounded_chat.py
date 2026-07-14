import sqlite3
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_session_factory, get_session
from app.main import create_app
from app.models import Document, DocumentChunk, DocumentStatus, KnowledgeBase, User
from app.schemas.chat import ChatUsage
from app.services.auth import get_current_user
from app.services.deepseek import DeepSeekInvalidCitationError, GroundedModelResponse
from app.services.retrieval import RetrievalHit


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

    async def chat_with_evidence(self, message, evidence, history) -> GroundedModelResponse:
        assert message == "What is the release process?"
        assert [item.chunk_id for item in evidence] == [self.chunk_id]
        assert [(item.role, item.content) for item in history] == [
            ("user", "Tell me about the handbook."),
            ("assistant", "It contains the release process."),
        ]
        return GroundedModelResponse(
            answer="Use the documented release process.",
            citation_ids=[self.chunk_id],
            model="test-model",
            latency_ms=12,
            usage=ChatUsage(prompt_tokens=50, completion_tokens=20, total_tokens=70),
        )


class InvalidCitationService:
    async def chat_with_evidence(self, message, evidence, history) -> GroundedModelResponse:
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
        user = User(email="test@example.com", password_hash="test-hash")
        knowledge_base = KnowledgeBase(name="Handbook", owner=user)
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
        user_id = user.id

    app = create_app(Settings(app_env="test", deepseek_api_key=None, _env_file=None))

    def override_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        email="test@example.com",
        password_hash="test-hash",
    )
    client = TestClient(app)
    return client, knowledge_base_id, chunk


def test_grounded_chat_returns_only_validated_retrieval_citations() -> None:
    client, knowledge_base_id, chunk = create_chat_client()
    retriever = StaticRetriever([RetrievalHit(chunk=chunk, score=0.9)])
    client.app.state.knowledge_base_retriever_factory = lambda: retriever
    client.app.state.chat_service_factory = lambda: SuccessfulGroundedService(chunk.id)

    response = client.post(
        "/api/chat",
        json={
            "message": "What is the release process?",
            "knowledge_base_id": str(knowledge_base_id),
            "history": [
                {"role": "user", "content": "Tell me about the handbook."},
                {"role": "assistant", "content": "It contains the release process."},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert UUID(payload.pop("conversation_id"))
    assert UUID(payload.pop("assistant_message_id"))
    assert payload == {
        "answer": "Use the documented release process.",
        "model": "test-model",
        "latency_ms": 12,
        "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
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

    usage_response = client.get(
        f"/api/knowledge-bases/{knowledge_base_id}/evaluations/model-usage-summary"
    )
    assert usage_response.status_code == 200
    assert usage_response.json() == {
        "call_count": 1,
        "usage_reported_call_count": 1,
        "prompt_tokens": 50,
        "completion_tokens": 20,
        "total_tokens": 70,
        "mean_latency_ms": 12.0,
        "p95_latency_ms": 12.0,
    }


def test_grounded_chat_refuses_when_model_citations_are_invalid() -> None:
    client, knowledge_base_id, chunk = create_chat_client()
    client.app.state.knowledge_base_retriever_factory = lambda: StaticRetriever(
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
    payload = response.json()
    assert UUID(payload.pop("conversation_id"))
    assert UUID(payload.pop("assistant_message_id"))
    assert payload == {
        "answer": "我无法根据当前检索到的资料生成带有效引用的回答。",
        "model": "retrieval-guard",
        "latency_ms": 0,
        "citations": [],
    }


def test_grounded_chat_stream_returns_progress_then_validated_result() -> None:
    client, knowledge_base_id, chunk = create_chat_client()
    client.app.state.knowledge_base_retriever_factory = lambda: StaticRetriever(
        [RetrievalHit(chunk=chunk, score=0.9)]
    )
    client.app.state.chat_service_factory = lambda: SuccessfulGroundedService(chunk.id)

    response = client.post(
        "/api/chat/stream",
        json={
            "message": "What is the release process?",
            "knowledge_base_id": str(knowledge_base_id),
            "history": [
                {"role": "user", "content": "Tell me about the handbook."},
                {"role": "assistant", "content": "It contains the release process."},
            ],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: status\ndata: {"phase": "retrieving"}' in response.text
    assert 'event: result\ndata: {"answer": "Use the documented release process."' in response.text
    assert '"citations": [{"chunk_id":' in response.text


def test_grounded_chat_persists_conversation_messages_and_feedback() -> None:
    client, knowledge_base_id, chunk = create_chat_client()
    client.app.state.knowledge_base_retriever_factory = lambda: StaticRetriever(
        [RetrievalHit(chunk=chunk, score=0.9)]
    )
    client.app.state.chat_service_factory = lambda: SuccessfulGroundedService(chunk.id)

    response = client.post(
        "/api/chat",
        json={
            "message": "What is the release process?",
            "knowledge_base_id": str(knowledge_base_id),
            "history": [
                {"role": "user", "content": "Tell me about the handbook."},
                {"role": "assistant", "content": "It contains the release process."},
            ],
        },
    )

    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]
    messages_response = client.get(
        f"/api/knowledge-bases/{knowledge_base_id}/conversations/{conversation_id}/messages"
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", "What is the release process?"),
        ("assistant", "Use the documented release process."),
    ]

    feedback_response = client.post(
        f"/api/knowledge-bases/{knowledge_base_id}/conversations/{conversation_id}/messages/"
        f"{messages[1]['id']}/feedback",
        json={"rating": 1, "comment": "Supported by the handbook."},
    )
    assert feedback_response.status_code == 201
    assert feedback_response.json()["rating"] == 1
