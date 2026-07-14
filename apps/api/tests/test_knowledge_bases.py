import sqlite3
from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.knowledge_bases import MAX_UPLOAD_BYTES, get_uploads_root
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_session_factory, get_session
from app.main import create_app
from app.models import User
from app.services.auth import get_current_user
from app.services.task_queue import get_document_task_queue
from app.services.vector_store import get_vector_store


class FakeTaskQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[str, ...]]] = []

    async def enqueue_job(self, function: str, *args: str) -> None:
        self.jobs.append((function, args))


class FailingTaskQueue:
    async def enqueue_job(self, function: str, *args: str) -> None:
        raise OSError("Redis is unavailable")


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted_knowledge_bases: list[str] = []

    def delete_knowledge_base_chunks(self, knowledge_base_id) -> None:
        self.deleted_knowledge_bases.append(str(knowledge_base_id))


class FailingVectorStore:
    def delete_knowledge_base_chunks(self, knowledge_base_id) -> None:
        raise OSError("Qdrant is unavailable")


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
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
        session.add(user)
        session.commit()
        user_id = user.id
    app = create_app(Settings(app_env="test", deepseek_api_key=None, _env_file=None))
    task_queue = FakeTaskQueue()
    vector_store = FakeVectorStore()

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        email="test@example.com",
        password_hash="test-hash",
    )
    app.dependency_overrides[get_uploads_root] = lambda: tmp_path / "uploads"
    app.dependency_overrides[get_document_task_queue] = lambda: task_queue
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.state.task_queue = task_queue
    app.state.vector_store = vector_store

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def create_knowledge_base(client: TestClient) -> dict:
    response = client.post("/api/knowledge-bases", json={"name": "Team handbook"})
    assert response.status_code == 201
    return response.json()


def test_create_and_list_knowledge_bases(client: TestClient) -> None:
    created = create_knowledge_base(client)

    response = client.get("/api/knowledge-bases")

    assert response.status_code == 200
    assert response.json() == [created]


def test_delete_knowledge_base_cleans_vector_records_and_uploads(
    client: TestClient,
    tmp_path,
) -> None:
    knowledge_base = create_knowledge_base(client)
    uploaded = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents",
        files={"file": ("handbook.md", b"# Release process", "text/markdown")},
    ).json()

    response = client.delete(f"/api/knowledge-bases/{knowledge_base['id']}")

    assert response.status_code == 204
    assert client.get("/api/knowledge-bases").json() == []
    assert not (tmp_path / "uploads" / uploaded["id"]).exists()
    assert client.app.state.vector_store.deleted_knowledge_bases == [knowledge_base["id"]]


def test_delete_knowledge_base_keeps_records_when_vector_cleanup_fails(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)
    client.app.dependency_overrides[get_vector_store] = lambda: FailingVectorStore()

    response = client.delete(f"/api/knowledge-bases/{knowledge_base['id']}")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Vector index is unavailable; knowledge base was not deleted"
    )
    assert client.get("/api/knowledge-bases").json() == [knowledge_base]


def test_upload_markdown_creates_pending_document(client: TestClient, tmp_path) -> None:
    knowledge_base = create_knowledge_base(client)

    response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents",
        files={"file": ("handbook.md", b"# Release process", "text/markdown")},
    )

    assert response.status_code == 201
    document = response.json()
    assert document["status"] == "pending"
    assert (tmp_path / "uploads" / document["id"] / "handbook.md").read_bytes() == (
        b"# Release process"
    )
    assert client.app.state.task_queue.jobs == [("process_document", (document["id"],))]

    documents_response = client.get(f"/api/knowledge-bases/{knowledge_base['id']}/documents")
    assert documents_response.status_code == 200
    assert documents_response.json() == [document]


def test_upload_rejects_unsupported_file_type(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)

    response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents",
        files={"file": ("notes.txt", b"not supported", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == (
        "Only Markdown (.md), PDF (.pdf), and DOCX (.docx) files are supported"
    )


def test_upload_accepts_docx_content_type(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)

    response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents",
        files={
            "file": (
                "handbook.docx",
                b"docx content is parsed by the worker",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["mime_type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_upload_rejects_file_larger_than_limit(client: TestClient, tmp_path) -> None:
    knowledge_base = create_knowledge_base(client)

    response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents",
        files={
            "file": (
                "too-large.md",
                b"a" * (MAX_UPLOAD_BYTES + 1),
                "text/markdown",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "The file exceeds the 10 MB upload limit"
    uploads_root = tmp_path / "uploads"
    assert uploads_root.exists()
    assert list(uploads_root.iterdir()) == []


def test_upload_marks_document_failed_when_queue_enqueue_fails(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)
    client.app.dependency_overrides[get_document_task_queue] = lambda: FailingTaskQueue()

    response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents",
        files={"file": ("handbook.md", b"# Release process", "text/markdown")},
    )

    assert response.status_code == 503
    documents_response = client.get(f"/api/knowledge-bases/{knowledge_base['id']}/documents")
    assert documents_response.status_code == 200
    assert documents_response.json()[0]["status"] == "failed"
    assert documents_response.json()[0]["error_message"] == (
        "Document was stored but could not be scheduled for processing"
    )


def test_retry_failed_document_requeues_stored_file(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)
    client.app.dependency_overrides[get_document_task_queue] = lambda: FailingTaskQueue()

    failed_upload = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents",
        files={"file": ("handbook.md", b"# Release process", "text/markdown")},
    )
    assert failed_upload.status_code == 503
    documents_response = client.get(f"/api/knowledge-bases/{knowledge_base['id']}/documents")
    document_id = documents_response.json()[0]["id"]

    retry_queue = FakeTaskQueue()
    client.app.dependency_overrides[get_document_task_queue] = lambda: retry_queue
    retry_response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents/{document_id}/retry"
    )

    assert retry_response.status_code == 202
    assert retry_response.json()["status"] == "pending"
    assert retry_response.json()["error_message"] is None
    assert retry_queue.jobs == [("process_document", (document_id,))]


def test_retry_rejects_document_that_is_not_failed(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)
    pending_upload = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents",
        files={"file": ("handbook.md", b"# Release process", "text/markdown")},
    )

    response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/documents/{pending_upload.json()['id']}/retry"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Only failed documents can be retried"


def test_create_and_list_evaluation_cases(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)

    response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/evaluation-cases",
        json={
            "question": "Where is the release process?",
            "expected_filenames": ["handbook.md"],
            "reference_answer": "The handbook documents the release process.",
        },
    )

    assert response.status_code == 201
    evaluation_case = response.json()
    assert evaluation_case["knowledge_base_id"] == knowledge_base["id"]
    assert evaluation_case["expected_filenames"] == ["handbook.md"]

    list_response = client.get(f"/api/knowledge-bases/{knowledge_base['id']}/evaluation-cases")
    assert list_response.status_code == 200
    assert list_response.json() == [evaluation_case]

    delete_response = client.delete(
        f"/api/knowledge-bases/{knowledge_base['id']}/evaluation-cases/{evaluation_case['id']}"
    )
    assert delete_response.status_code == 204
    assert client.get(f"/api/knowledge-bases/{knowledge_base['id']}/evaluation-cases").json() == []


def test_run_evaluation_requires_cases(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)

    response = client.post(f"/api/knowledge-bases/{knowledge_base['id']}/evaluations/retrieval")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Add at least one evaluation case before running retrieval evaluation"
    )


def test_capture_and_summarize_human_answer_review(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)
    evaluation_case = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/evaluation-cases",
        json={
            "question": "Where is the release process?",
            "expected_filenames": ["handbook.md"],
        },
    ).json()

    response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/evaluation-cases/"
        f"{evaluation_case['id']}/answer-reviews",
        json={
            "answer": "The release process is documented in the handbook.",
            "model": "test-model",
            "latency_ms": 12,
            "citation_chunk_ids": [],
            "answer_verdict": "pass",
            "citation_verdict": "not_applicable",
            "refusal_verdict": "not_applicable",
            "notes": "Manually reviewed for the API contract.",
        },
    )

    assert response.status_code == 201
    answer_review = response.json()
    assert answer_review["evaluation_case_id"] == evaluation_case["id"]
    assert answer_review["citation_filenames"] == []

    list_response = client.get(
        f"/api/knowledge-bases/{knowledge_base['id']}/evaluation-cases/"
        f"{evaluation_case['id']}/answer-reviews"
    )
    assert list_response.status_code == 200
    assert list_response.json() == [answer_review]

    summary_response = client.get(
        f"/api/knowledge-bases/{knowledge_base['id']}/evaluations/answer-review-summary"
    )
    assert summary_response.status_code == 200
    assert summary_response.json() == {
        "case_count": 1,
        "review_count": 1,
        "unreviewed_case_count": 0,
        "answer_pass_rate": 1.0,
        "citation_pass_rate": None,
        "refusal_pass_rate": None,
    }


def test_answer_review_rejects_citation_outside_current_knowledge_base(client: TestClient) -> None:
    knowledge_base = create_knowledge_base(client)
    evaluation_case = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/evaluation-cases",
        json={
            "question": "Where is the release process?",
            "expected_filenames": ["handbook.md"],
        },
    ).json()

    response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/evaluation-cases/"
        f"{evaluation_case['id']}/answer-reviews",
        json={
            "answer": "The release process is documented in the handbook.",
            "model": "test-model",
            "latency_ms": 12,
            "citation_chunk_ids": [str(uuid4())],
            "answer_verdict": "pass",
            "citation_verdict": "pass",
            "refusal_verdict": "not_applicable",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Citation chunks must belong to the current knowledge base"
