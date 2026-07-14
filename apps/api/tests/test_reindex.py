from uuid import UUID, uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import create_session_factory
from app.models import Document, DocumentStatus, KnowledgeBase
from app.reindex import reindex_knowledge_base


class FakeProcessor:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, bool]] = []

    def process(self, document_id: UUID, force: bool = False) -> None:
        self.calls.append((document_id, force))


def test_reindex_knowledge_base_processes_only_ready_documents() -> None:
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
    try:
        with session_factory() as session:
            target = KnowledgeBase(name="Target")
            other = KnowledgeBase(name="Other")
            ready = Document(
                knowledge_base=target,
                filename="ready.md",
                mime_type="text/markdown",
                status=DocumentStatus.READY,
            )
            pending = Document(
                knowledge_base=target,
                filename="pending.md",
                mime_type="text/markdown",
                status=DocumentStatus.PENDING,
            )
            other_ready = Document(
                knowledge_base=other,
                filename="other.md",
                mime_type="text/markdown",
                status=DocumentStatus.READY,
            )
            session.add_all([ready, pending, other_ready])
            session.commit()
            knowledge_base_id = target.id
            ready_id = ready.id

        processor = FakeProcessor()

        count = reindex_knowledge_base(knowledge_base_id, session_factory, processor)

        assert count == 1
        assert processor.calls == [(ready_id, True)]
        assert reindex_knowledge_base(uuid4(), session_factory, processor) == 0
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
