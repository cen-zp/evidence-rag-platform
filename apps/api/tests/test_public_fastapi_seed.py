from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import create_session_factory
from app.evaluation.retrieval import RetrievalEvaluationCase
from app.models import Document, EvaluationCase, KnowledgeBase, User
from app.public_fastapi_seed import (
    PUBLIC_KNOWLEDGE_BASE_NAME,
    seed_public_fastapi_knowledge_base,
)


class FakeProcessor:
    def __init__(self) -> None:
        self.document_ids: list[UUID] = []

    def process(self, document_id: UUID) -> None:
        self.document_ids.append(document_id)


def test_seed_public_corpus_is_idempotent_and_keeps_account_scope(tmp_path: Path) -> None:
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
    source_paths = [tmp_path / "path.md", tmp_path / "query.md"]
    source_paths[0].write_text("path source", encoding="utf-8")
    source_paths[1].write_text("query source", encoding="utf-8")
    cases = [
        RetrievalEvaluationCase(
            id="path-01", question="如何声明路径参数？", expected_filenames=["path.md"]
        ),
        RetrievalEvaluationCase(
            id="query-01", question="如何声明查询参数？", expected_filenames=["query.md"]
        ),
    ]
    processor = FakeProcessor()

    try:
        with session_factory() as session:
            session.add(User(email="owner@example.com", password_hash="not-a-real-password"))
            session.commit()

        result = seed_public_fastapi_knowledge_base(
            session_factory, processor, tmp_path / "uploads", source_paths, cases
        )
        assert result.documents_created == 2
        assert result.evaluation_cases_created == 2
        assert len(processor.document_ids) == 2

        with session_factory() as session:
            knowledge_base = session.get(KnowledgeBase, result.knowledge_base_id)
            documents = list(
                session.scalars(
                    select(Document).where(Document.knowledge_base_id == result.knowledge_base_id)
                )
            )
            evaluation_cases = list(
                session.scalars(
                    select(EvaluationCase).where(
                        EvaluationCase.knowledge_base_id == result.knowledge_base_id
                    )
                )
            )

        assert knowledge_base is not None
        assert knowledge_base.name == PUBLIC_KNOWLEDGE_BASE_NAME
        assert knowledge_base.owner_id is not None
        assert len(documents) == 2
        assert len(evaluation_cases) == 2

        repeated = seed_public_fastapi_knowledge_base(
            session_factory, processor, tmp_path / "uploads", source_paths, cases
        )
        assert repeated.knowledge_base_id == result.knowledge_base_id
        assert repeated.documents_created == 0
        assert repeated.evaluation_cases_created == 0
        assert len(processor.document_ids) == 2
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_seed_public_corpus_requires_exactly_one_account(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    source_path = tmp_path / "path.md"
    source_path.write_text("path source", encoding="utf-8")

    try:
        with session_factory() as session:
            session.add_all(
                [
                    User(email="one@example.com", password_hash="not-a-real-password"),
                    User(email="two@example.com", password_hash="not-a-real-password"),
                ]
            )
            session.commit()

        with pytest.raises(RuntimeError, match="exactly one local account"):
            seed_public_fastapi_knowledge_base(
                session_factory,
                FakeProcessor(),
                tmp_path / "uploads",
                [source_path],
                [],
            )
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
