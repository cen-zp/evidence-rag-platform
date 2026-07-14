import shutil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT
from app.db.session import get_session
from app.models import Document, DocumentStatus, KnowledgeBase
from app.schemas.knowledge import DocumentRead, KnowledgeBaseCreate, KnowledgeBaseRead
from app.services.task_queue import DocumentTaskQueue, get_document_task_queue
from app.services.vector_store import QdrantVectorStore, get_vector_store

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge bases"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
SUPPORTED_FILE_TYPES = {
    ".md": {"text/markdown", "text/plain"},
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
}


def get_uploads_root() -> Path:
    return PROJECT_ROOT / "uploads"


def get_knowledge_base_or_404(session: Session, knowledge_base_id: UUID) -> KnowledgeBase:
    knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return knowledge_base


def get_document_or_404(
    session: Session,
    knowledge_base_id: UUID,
    document_id: UUID,
) -> Document:
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.knowledge_base_id == knowledge_base_id,
        )
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in this knowledge base",
        )
    return document


def validate_upload(file: UploadFile) -> tuple[str, str]:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A filename is required",
        )

    suffix = Path(filename).suffix.lower()
    allowed_mime_types = SUPPORTED_FILE_TYPES.get(suffix)
    if allowed_mime_types is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only Markdown (.md), PDF (.pdf), and DOCX (.docx) files are supported",
        )

    mime_type = file.content_type or ""
    if mime_type not in allowed_mime_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file content type does not match its supported extension",
        )

    return filename, mime_type


@router.post("", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    session: Session = Depends(get_session),
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(name=payload.name, description=payload.description)
    session.add(knowledge_base)
    session.commit()
    session.refresh(knowledge_base)
    return knowledge_base


@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(session: Session = Depends(get_session)) -> list[KnowledgeBase]:
    return list(session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())))


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    knowledge_base_id: UUID,
    session: Session = Depends(get_session),
    uploads_root: Path = Depends(get_uploads_root),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
) -> None:
    knowledge_base = get_knowledge_base_or_404(session, knowledge_base_id)
    document_ids = list(
        session.scalars(select(Document.id).where(Document.knowledge_base_id == knowledge_base_id))
    )
    try:
        vector_store.delete_knowledge_base_chunks(knowledge_base_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector index is unavailable; knowledge base was not deleted",
        ) from error

    session.delete(knowledge_base)
    session.commit()
    for document_id in document_ids:
        shutil.rmtree(uploads_root / str(document_id), ignore_errors=True)


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    knowledge_base_id: UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    uploads_root: Path = Depends(get_uploads_root),
    task_queue: DocumentTaskQueue = Depends(get_document_task_queue),
) -> Document:
    knowledge_base = get_knowledge_base_or_404(session, knowledge_base_id)
    filename, mime_type = validate_upload(file)
    document = Document(
        knowledge_base=knowledge_base,
        filename=filename,
        mime_type=mime_type,
        status=DocumentStatus.PENDING,
    )
    destination_directory: Path | None = None
    document_stored = False

    try:
        session.add(document)
        session.flush()

        destination_directory = uploads_root / str(document.id)
        destination_directory.mkdir(parents=True, exist_ok=False)
        destination = destination_directory / filename
        bytes_written = 0

        with destination.open("wb") as output_file:
            while chunk := await file.read(READ_CHUNK_BYTES):
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="The file exceeds the 10 MB upload limit",
                    )
                output_file.write(chunk)

        session.commit()
        session.refresh(document)
        document_stored = True
        try:
            await task_queue.enqueue_job("process_document", str(document.id))
        except Exception as error:
            document.status = DocumentStatus.FAILED
            document.error_message = "Document was stored but could not be scheduled for processing"
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Document was stored but the processing queue is unavailable",
            ) from error
        return document
    except HTTPException:
        session.rollback()
        if destination_directory is not None and not document_stored:
            shutil.rmtree(destination_directory, ignore_errors=True)
        raise
    except Exception as error:
        session.rollback()
        if destination_directory is not None:
            shutil.rmtree(destination_directory, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The document could not be stored",
        ) from error
    finally:
        await file.close()


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentRead])
def list_documents(
    knowledge_base_id: UUID,
    session: Session = Depends(get_session),
) -> list[Document]:
    get_knowledge_base_or_404(session, knowledge_base_id)
    statement = (
        select(Document)
        .where(Document.knowledge_base_id == knowledge_base_id)
        .order_by(Document.created_at.desc())
    )
    return list(session.scalars(statement))


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/retry",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_failed_document(
    knowledge_base_id: UUID,
    document_id: UUID,
    session: Session = Depends(get_session),
    uploads_root: Path = Depends(get_uploads_root),
    task_queue: DocumentTaskQueue = Depends(get_document_task_queue),
) -> Document:
    get_knowledge_base_or_404(session, knowledge_base_id)
    document = get_document_or_404(session, knowledge_base_id, document_id)
    if document.status != DocumentStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed documents can be retried",
        )

    source_path = uploads_root / str(document.id) / document.filename
    if not source_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The uploaded source file is missing and cannot be retried",
        )

    document.status = DocumentStatus.PENDING
    document.error_message = None
    session.commit()
    session.refresh(document)
    try:
        await task_queue.enqueue_job("process_document", str(document.id))
    except Exception as error:
        document.status = DocumentStatus.FAILED
        document.error_message = "Document could not be scheduled for retry"
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document queue is unavailable; retry again after Redis recovers",
        ) from error
    return document
