import argparse
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_session_factory
from app.models import Document, DocumentStatus
from app.services.document_processing import DocumentProcessor, create_document_processor


def reindex_knowledge_base(
    knowledge_base_id: UUID,
    session_factory: sessionmaker[Session],
    processor: DocumentProcessor,
) -> int:
    with session_factory() as session:
        document_ids = list(
            session.scalars(
                select(Document.id).where(
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.status == DocumentStatus.READY,
                )
            )
        )

    for document_id in document_ids:
        processor.process(document_id, force=True)
    return len(document_ids)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild a knowledge base with the active embedding model"
    )
    parser.add_argument("--knowledge-base-id", required=True, type=UUID)
    args = parser.parse_args(argv)
    processed = reindex_knowledge_base(
        args.knowledge_base_id,
        get_session_factory(),
        create_document_processor(),
    )
    print(f"Reindexed {processed} ready document(s).")


if __name__ == "__main__":
    main()
