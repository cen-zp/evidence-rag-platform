from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from qdrant_client import QdrantClient
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import get_session_factory
from app.models import Document, DocumentChunk, DocumentStatus
from app.services.chunking import chunk_pages
from app.services.document_parsing import parse_document
from app.services.local_hash_embedding import LocalHashEmbedding
from app.services.vector_store import QdrantVectorStore


class DocumentProcessor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        vector_store: QdrantVectorStore,
        embed: Callable[[str], list[float]],
        uploads_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._vector_store = vector_store
        self._embed = embed
        self._uploads_root = uploads_root

    def process(self, document_id: UUID) -> None:
        try:
            with self._session_factory() as session:
                document = session.get(Document, document_id)
                if document is None or document.status == DocumentStatus.READY:
                    return

                document.status = DocumentStatus.PROCESSING
                document.error_message = None
                session.commit()

                source_path = self._uploads_root / str(document.id) / document.filename
                pages = parse_document(source_path, document.mime_type)
                chunk_drafts = chunk_pages(pages)
                if not chunk_drafts:
                    raise ValueError("No extractable text was found in the document")

                session.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
                )
                chunks = [
                    DocumentChunk(
                        document_id=document.id,
                        knowledge_base_id=document.knowledge_base_id,
                        content=content,
                        page_number=page_number,
                        chunk_index=index,
                        chunk_metadata=metadata,
                    )
                    for index, (content, page_number, metadata) in enumerate(chunk_drafts)
                ]
                session.add_all(chunks)
                session.flush()

                vectors = [self._embed(chunk.content) for chunk in chunks]
                self._vector_store.replace_document_chunks(chunks, vectors)
                document.status = DocumentStatus.READY
                session.commit()
        except Exception as error:
            try:
                self._vector_store.delete_document_chunks(document_id)
            except Exception:
                pass
            self._mark_failed(document_id, error)
            raise

    def _mark_failed(self, document_id: UUID, error: Exception) -> None:
        with self._session_factory() as session:
            document = session.get(Document, document_id)
            if document is None:
                return
            document.status = DocumentStatus.FAILED
            document.error_message = str(error)[:1000]
            session.commit()


def create_document_processor() -> DocumentProcessor:
    settings = get_settings()
    embedder = LocalHashEmbedding(settings.embedding_dimension)
    vector_store = QdrantVectorStore(
        client=QdrantClient(url=settings.qdrant_url),
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_dimension,
    )
    return DocumentProcessor(
        session_factory=get_session_factory(),
        vector_store=vector_store,
        embed=embedder.embed,
        uploads_root=PROJECT_ROOT / "uploads",
    )
