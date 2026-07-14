from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import create_session_factory
from app.demo_seed import DEMO_KNOWLEDGE_BASE_NAME, seed_demo_knowledge_base
from app.models import Document, KnowledgeBase


class FakeProcessor:
    def __init__(self) -> None:
        self.document_ids: list[UUID] = []

    def process(self, document_id: UUID) -> None:
        self.document_ids.append(document_id)


def test_seed_demo_knowledge_base_copies_sources_and_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    source_paths = [tmp_path / "first.md", tmp_path / "second.md"]
    source_paths[0].write_text("first source", encoding="utf-8")
    source_paths[1].write_text("second source", encoding="utf-8")
    processor = FakeProcessor()
    uploads_root = tmp_path / "uploads"

    try:
        knowledge_base_id, created = seed_demo_knowledge_base(
            session_factory,
            processor,
            uploads_root,
            source_paths,
        )

        assert created is True
        assert len(processor.document_ids) == 2
        with session_factory() as session:
            knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
            documents = list(
                session.scalars(
                    select(Document)
                    .where(Document.knowledge_base_id == knowledge_base_id)
                    .order_by(Document.filename)
                )
            )

        assert knowledge_base is not None
        assert knowledge_base.name == DEMO_KNOWLEDGE_BASE_NAME
        assert [document.filename for document in documents] == ["first.md", "second.md"]
        first_copy = uploads_root / str(documents[0].id) / "first.md"
        second_copy = uploads_root / str(documents[1].id) / "second.md"
        assert first_copy.read_text() == "first source"
        assert second_copy.read_text() == "second source"

        repeated_id, repeated_created = seed_demo_knowledge_base(
            session_factory,
            processor,
            uploads_root,
            source_paths,
        )
        assert repeated_id == knowledge_base_id
        assert repeated_created is False
        assert len(processor.document_ids) == 2
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
