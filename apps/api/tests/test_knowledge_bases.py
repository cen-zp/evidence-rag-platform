import sqlite3
from collections.abc import Generator

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
from app.services.task_queue import get_document_task_queue


class FakeTaskQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[str, ...]]] = []

    async def enqueue_job(self, function: str, *args: str) -> None:
        self.jobs.append((function, args))


class FailingTaskQueue:
    async def enqueue_job(self, function: str, *args: str) -> None:
        raise OSError("Redis is unavailable")


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
    app = create_app(Settings(app_env="test", deepseek_api_key=None, _env_file=None))
    task_queue = FakeTaskQueue()

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_uploads_root] = lambda: tmp_path / "uploads"
    app.dependency_overrides[get_document_task_queue] = lambda: task_queue
    app.state.task_queue = task_queue

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
