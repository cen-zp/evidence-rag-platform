import argparse
import shutil
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import PROJECT_ROOT
from app.db.session import get_session_factory
from app.models import Document, KnowledgeBase
from app.services.document_processing import DocumentProcessor, create_document_processor

DEMO_KNOWLEDGE_BASE_NAME = "验收演示知识库（非简历指标）"
DEMO_DOCUMENT_PATHS = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "docs" / "document-processing.md",
    PROJECT_ROOT / "docs" / "retrieval.md",
    PROJECT_ROOT / "docs" / "evaluation.md",
    PROJECT_ROOT / "docs" / "verification.md",
)


def seed_demo_knowledge_base(
    session_factory: sessionmaker[Session],
    processor: DocumentProcessor,
    uploads_root: Path,
    source_paths: Sequence[Path] = DEMO_DOCUMENT_PATHS,
) -> tuple[UUID, bool]:
    with session_factory() as session:
        existing_id = session.scalar(
            select(KnowledgeBase.id).where(KnowledgeBase.name == DEMO_KNOWLEDGE_BASE_NAME)
        )
        if existing_id is not None:
            return existing_id, False

        knowledge_base = KnowledgeBase(name=DEMO_KNOWLEDGE_BASE_NAME)
        session.add(knowledge_base)
        session.commit()
        session.refresh(knowledge_base)
        knowledge_base_id = knowledge_base.id

    for source_path in source_paths:
        if not source_path.is_file():
            raise FileNotFoundError(f"Demo source file is missing: {source_path}")

        with session_factory() as session:
            document = Document(
                knowledge_base_id=knowledge_base_id,
                filename=source_path.name,
                mime_type="text/markdown",
            )
            session.add(document)
            session.commit()
            session.refresh(document)
            document_id = document.id

        destination_directory = uploads_root / str(document_id)
        destination_directory.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(source_path, destination_directory / source_path.name)
        processor.process(document_id)

    return knowledge_base_id, True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the non-resume demonstration evaluation corpus"
    )
    parser.parse_args()
    knowledge_base_id, created = seed_demo_knowledge_base(
        get_session_factory(),
        create_document_processor(),
        PROJECT_ROOT / "uploads",
    )
    status = "Created" if created else "Already exists"
    print(f"{status}: {DEMO_KNOWLEDGE_BASE_NAME} ({knowledge_base_id})")


if __name__ == "__main__":
    main()
