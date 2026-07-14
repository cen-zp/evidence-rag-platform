import sqlite3
from collections.abc import Generator
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import create_session_factory
from app.models import Document, DocumentChunk, DocumentStatus, KnowledgeBase
from app.services.document_processing import DocumentProcessor


class FakeVectorStore:
    def __init__(self) -> None:
        self.indexed: list[tuple[list[UUID], list[list[float]]]] = []
        self.deleted: list[UUID] = []

    def replace_document_chunks(
        self,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
    ) -> None:
        self.indexed.append(([chunk.id for chunk in chunks], vectors))

    def delete_document_chunks(self, document_id: UUID) -> None:
        self.deleted.append(document_id)


@pytest.fixture
def document_fixture(tmp_path: Path) -> Generator[tuple[object, UUID, Path], None, None]:
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
        knowledge_base = KnowledgeBase(name="Engineering notes")
        document = Document(
            knowledge_base=knowledge_base,
            filename="notes.md",
            mime_type="text/markdown",
            status=DocumentStatus.PENDING,
        )
        session.add(document)
        session.commit()
        document_id = document.id

    source_directory = tmp_path / "uploads" / str(document_id)
    source_directory.mkdir(parents=True)
    yield session_factory, document_id, source_directory

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_processor_marks_markdown_ready_after_chunking_and_indexing(document_fixture) -> None:
    session_factory, document_id, source_directory = document_fixture
    (source_directory / "notes.md").write_text("检索增强生成 " * 300, encoding="utf-8")
    vector_store = FakeVectorStore()
    processor = DocumentProcessor(
        session_factory=session_factory,
        vector_store=vector_store,
        embed=lambda text: [float(len(text)), 0.0],
        uploads_root=source_directory.parent,
    )

    processor.process(document_id)

    with session_factory() as session:
        document = session.get(Document, document_id)
        chunks = list(
            session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
        )

    assert document is not None
    assert document.status == DocumentStatus.READY
    assert len(chunks) == 3
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert vector_store.deleted == []
    assert vector_store.indexed[0][0] == [chunk.id for chunk in chunks]
    assert vector_store.indexed[0][1] == [[float(len(chunk.content)), 0.0] for chunk in chunks]


def test_processor_marks_document_failed_when_markdown_is_not_utf8(document_fixture) -> None:
    session_factory, document_id, source_directory = document_fixture
    (source_directory / "notes.md").write_bytes(b"\xff")
    vector_store = FakeVectorStore()
    processor = DocumentProcessor(
        session_factory=session_factory,
        vector_store=vector_store,
        embed=lambda text: [0.0, 1.0],
        uploads_root=source_directory.parent,
    )

    with pytest.raises(Exception, match="Markdown files must be UTF-8 encoded"):
        processor.process(document_id)

    with session_factory() as session:
        document = session.get(Document, document_id)
        chunks = list(session.scalars(select(DocumentChunk)))

    assert document is not None
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "Markdown files must be UTF-8 encoded"
    assert chunks == []
    assert vector_store.deleted == [document_id]
