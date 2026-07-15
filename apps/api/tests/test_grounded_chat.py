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


def create_chat_client(settings: Settings | None = None) -> tuple[TestClient, UUID, DocumentChunk]:
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

    app = create_app(settings or Settings(app_env="test", deepseek_api_key=None, _env_file=None))

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
    assert payload.pop("retrieval_latency_ms") >= 0
    assert payload.pop("total_latency_ms") >= 0
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
        "estimated_cost_call_count": 0,
        "estimated_cost_currency": None,
        "total_estimated_cost": None,
        "mean_estimated_cost": None,
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
    assert payload.pop("retrieval_latency_ms") >= 0
    assert payload.pop("total_latency_ms") >= 0
    assert payload == {
        "answer": "我无法根据当前检索到的资料生成带有效引用的回答。",
        "model": "retrieval-guard",
        "latency_ms": 0,
        "citations": [],
    }


def test_grounded_chat_low_confidence_guard_skips_the_model() -> None:
    client, knowledge_base_id, _ = create_chat_client()
    retriever = StaticRetriever([])
    client.app.state.knowledge_base_retriever_factory = lambda: retriever

    def unexpected_service():
        raise AssertionError("The model must not run without confident evidence")

    client.app.state.chat_service_factory = unexpected_service
    response = client.post(
        "/api/chat",
        json={
            "message": "What is outside this knowledge base?",
            "knowledge_base_id": str(knowledge_base_id),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "retrieval-guard"
    assert payload["citations"] == []
    assert payload["retrieval_latency_ms"] >= 0
    assert payload["total_latency_ms"] >= payload["retrieval_latency_ms"]
    assert retriever.calls == [
        (knowledge_base_id, "What is outside this knowledge base?", 5)
    ]


def test_grounded_chat_records_the_cost_price_snapshot() -> None:
    client, knowledge_base_id, chunk = create_chat_client(
        Settings(
            app_env="test",
            deepseek_api_key=None,
            deepseek_input_cost_per_million_tokens=2.0,
            deepseek_output_cost_per_million_tokens=4.0,
            deepseek_cost_currency="CNY",
            _env_file=None,
        )
    )
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
    usage_response = client.get(
        f"/api/knowledge-bases/{knowledge_base_id}/evaluations/model-usage-summary"
    )
    assert usage_response.json() == {
        "call_count": 1,
        "usage_reported_call_count": 1,
        "prompt_tokens": 50,
        "completion_tokens": 20,
        "total_tokens": 70,
        "mean_latency_ms": 12.0,
        "p95_latency_ms": 12.0,
        "estimated_cost_call_count": 1,
        "estimated_cost_currency": "CNY",
        "total_estimated_cost": 0.00018,
        "mean_estimated_cost": 0.00018,
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


def test_grounded_chat_stream_serializes_low_confidence_guard_without_usage() -> None:
    client, knowledge_base_id, _ = create_chat_client()
    retriever = StaticRetriever([])
    client.app.state.knowledge_base_retriever_factory = lambda: retriever

    def unexpected_service():
        raise AssertionError("The model must not run without confident evidence")

    client.app.state.chat_service_factory = unexpected_service
    response = client.post(
        "/api/chat/stream",
        json={
            "message": "What is outside this knowledge base?",
            "knowledge_base_id": str(knowledge_base_id),
        },
    )

    assert response.status_code == 200
    assert 'event: status\ndata: {"phase": "retrieving"}' in response.text
    assert (
        'event: result\ndata: {"answer": "我无法根据当前知识库中的资料回答这个问题。"'
        in response.text
    )
    assert '"model": "retrieval-guard"' in response.text
    assert '"usage"' not in response.text
    assert 'event: error' not in response.text


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
    assistant_message = messages[1]
    assert assistant_message["retrieval_latency_ms"] >= 0
    assert assistant_message["total_latency_ms"] >= assistant_message["retrieval_latency_ms"]
    assert assistant_message["browser_end_to_end_latency_ms"] is None

    latency_response = client.post(
        f"/api/knowledge-bases/{knowledge_base_id}/conversations/{conversation_id}/messages/"
        f"{assistant_message['id']}/browser-latency",
        json={"browser_end_to_end_latency_ms": 25},
    )
    assert latency_response.status_code == 200
    assert latency_response.json()["browser_end_to_end_latency_ms"] == 25

    latency_summary_response = client.get(
        f"/api/knowledge-bases/{knowledge_base_id}/evaluations/end-to-end-latency-summary"
    )
    assert latency_summary_response.status_code == 200
    latency_summary = latency_summary_response.json()
    assert latency_summary["message_count"] == 1
    assert latency_summary["answered_count"] == 1
    assert latency_summary["guarded_count"] == 0
    assert latency_summary["retrieval_reported_count"] == 1
    assert latency_summary["server_total_reported_count"] == 1
    assert latency_summary["browser_reported_count"] == 1
    assert latency_summary["mean_browser_end_to_end_latency_ms"] == 25.0
    assert latency_summary["p95_browser_end_to_end_latency_ms"] == 25

    feedback_response = client.post(
        f"/api/knowledge-bases/{knowledge_base_id}/conversations/{conversation_id}/messages/"
        f"{messages[1]['id']}/feedback",
        json={"rating": 1, "comment": "Supported by the handbook."},
    )
    assert feedback_response.status_code == 201
    assert feedback_response.json()["rating"] == 1
