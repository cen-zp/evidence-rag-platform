"""Seed the public FastAPI corpus into the only local account for workflow verification.

This command is deliberately conservative: it does not inspect account emails, does not
delete data, and stops unless exactly one local account exists. The included cases are
an AI-assisted draft, so this command supports product testing rather than a formal
quality claim.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import PROJECT_ROOT
from app.db.session import get_session_factory
from app.evaluation.retrieval import RetrievalEvaluationCase
from app.evaluation.runner import load_cases
from app.models import Document, EvaluationCase, KnowledgeBase, User
from app.services.document_processing import DocumentProcessor, create_document_processor

PUBLIC_KNOWLEDGE_BASE_NAME = "FastAPI 官方文档评测语料（题集待人工复核）"
PUBLIC_KNOWLEDGE_BASE_DESCRIPTION = (
    "9 篇 FastAPI 官方公开教程；72 条中文 AI 协助评测草案。"
    "在独立人工逐条复核题目、答案和来源前，不得用于正式质量结论或简历指标。"
)
OFFICIAL_CORPUS_DIR = PROJECT_ROOT / "evals" / "corpora" / "fastapi-official-2026-07-14"
OFFICIAL_CASES_PATH = PROJECT_ROOT / "evals" / "independent" / "fastapi-official-cases.jsonl"


@dataclass(frozen=True)
class PublicCorpusSeedResult:
    knowledge_base_id: UUID
    documents_created: int
    evaluation_cases_created: int


def seed_public_fastapi_knowledge_base(
    session_factory: sessionmaker[Session],
    processor: DocumentProcessor,
    uploads_root: Path,
    source_paths: Sequence[Path],
    cases: Sequence[RetrievalEvaluationCase],
) -> PublicCorpusSeedResult:
    """Create missing corpus records and process only files not already imported."""
    if not source_paths:
        raise ValueError("At least one public source document is required")

    for source_path in source_paths:
        if not source_path.is_file():
            raise FileNotFoundError(f"Public source file is missing: {source_path}")

    with session_factory() as session:
        owner_ids = list(session.scalars(select(User.id)))
        if len(owner_ids) != 1:
            raise RuntimeError(
                "Public corpus seeding requires exactly one local account; "
                "use the authenticated upload flow when multiple accounts exist."
            )
        owner_id = owner_ids[0]
        knowledge_base = session.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.owner_id == owner_id,
                KnowledgeBase.name == PUBLIC_KNOWLEDGE_BASE_NAME,
            )
        )
        if knowledge_base is None:
            knowledge_base = KnowledgeBase(
                owner_id=owner_id,
                name=PUBLIC_KNOWLEDGE_BASE_NAME,
                description=PUBLIC_KNOWLEDGE_BASE_DESCRIPTION,
            )
            session.add(knowledge_base)
            session.flush()

        knowledge_base_id = knowledge_base.id
        existing_filenames = set(
            session.scalars(
                select(Document.filename).where(Document.knowledge_base_id == knowledge_base_id)
            )
        )
        documents_to_process: list[tuple[UUID, Path]] = []
        for source_path in source_paths:
            if source_path.name in existing_filenames:
                continue
            document = Document(
                knowledge_base_id=knowledge_base_id,
                filename=source_path.name,
                mime_type="text/markdown",
            )
            session.add(document)
            session.flush()
            documents_to_process.append((document.id, source_path))

        existing_questions = set(
            session.scalars(
                select(EvaluationCase.question).where(
                    EvaluationCase.knowledge_base_id == knowledge_base_id
                )
            )
        )
        evaluation_cases_created = 0
        for case in cases:
            if case.question in existing_questions:
                continue
            session.add(
                EvaluationCase(
                    knowledge_base_id=knowledge_base_id,
                    question=case.question,
                    expected_filenames=case.expected_filenames,
                    reference_answer=case.reference_answer,
                )
            )
            evaluation_cases_created += 1
        session.commit()

    for document_id, source_path in documents_to_process:
        destination_directory = uploads_root / str(document_id)
        destination_directory.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(source_path, destination_directory / source_path.name)
        processor.process(document_id)

    return PublicCorpusSeedResult(
        knowledge_base_id=knowledge_base_id,
        documents_created=len(documents_to_process),
        evaluation_cases_created=evaluation_cases_created,
    )


def main() -> None:
    source_paths = sorted(OFFICIAL_CORPUS_DIR.glob("*.md"))
    cases = load_cases(OFFICIAL_CASES_PATH)
    result = seed_public_fastapi_knowledge_base(
        get_session_factory(),
        create_document_processor(),
        PROJECT_ROOT / "uploads",
        source_paths,
        cases,
    )
    print(
        "Knowledge base "
        f"{result.knowledge_base_id}: imported {result.documents_created} document(s), "
        f"{result.evaluation_cases_created} draft evaluation case(s)."
    )


if __name__ == "__main__":
    main()
