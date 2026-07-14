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

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge bases"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
SUPPORTED_FILE_TYPES = {
    ".md": {"text/markdown", "text/plain"},
    ".pdf": {"application/pdf"},
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
            detail="Only Markdown (.md) and PDF (.pdf) files are supported",
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
