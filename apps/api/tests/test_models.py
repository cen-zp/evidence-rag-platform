import sqlite3

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Document, DocumentChunk, DocumentStatus, KnowledgeBase


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: sqlite3.Connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_knowledge_document_and_chunk_persist(engine) -> None:
    with Session(engine) as session:
        knowledge_base = KnowledgeBase(name="Engineering handbook")
        document = Document(
            knowledge_base=knowledge_base,
            filename="handbook.md",
            mime_type="text/markdown",
        )
        chunk = DocumentChunk(
            document=document,
            knowledge_base_id=knowledge_base.id,
            content="All production changes require review.",
            chunk_index=0,
            chunk_metadata={"heading": "Release process"},
        )
        session.add(chunk)
        session.flush()

        assert document.status == DocumentStatus.PENDING
        assert chunk.vector_point_id == str(chunk.id)
        session.commit()

        persisted = session.scalar(select(DocumentChunk).where(DocumentChunk.id == chunk.id))
        assert persisted is not None
        assert persisted.document.filename == "handbook.md"
        assert persisted.chunk_metadata == {"heading": "Release process"}


def test_chunk_cannot_reference_document_from_another_knowledge_base(engine) -> None:
    with Session(engine) as session:
        first = KnowledgeBase(name="First")
        second = KnowledgeBase(name="Second")
        document = Document(
            knowledge_base=first,
            filename="first.md",
            mime_type="text/markdown",
        )
        session.add_all([first, second, document])
        session.flush()

        session.add(
            DocumentChunk(
                document_id=document.id,
                knowledge_base_id=second.id,
                content="This must not cross the knowledge-base boundary.",
                chunk_index=0,
            )
        )

        with pytest.raises(IntegrityError):
            session.flush()
