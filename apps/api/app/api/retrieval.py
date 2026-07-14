from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.knowledge_bases import get_knowledge_base_or_404
from app.db.session import get_session
from app.models import User
from app.schemas.knowledge import RetrievalHitRead, RetrievalRequest
from app.services.auth import get_current_user
from app.services.retrieval import KnowledgeBaseRetriever, get_knowledge_base_retriever

router = APIRouter(prefix="/api/knowledge-bases", tags=["retrieval"])


@router.post("/{knowledge_base_id}/search", response_model=list[RetrievalHitRead])
def search_knowledge_base(
    knowledge_base_id: UUID,
    payload: RetrievalRequest,
    session: Session = Depends(get_session),
    retriever: KnowledgeBaseRetriever = Depends(get_knowledge_base_retriever),
    current_user: User = Depends(get_current_user),
) -> list[RetrievalHitRead]:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    try:
        hits = retriever.search(knowledge_base_id, payload.query, payload.top_k)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector search is unavailable. Check Qdrant and try again.",
        ) from error

    return [
        RetrievalHitRead(
            chunk_id=hit.chunk.id,
            document_id=hit.chunk.document_id,
            filename=hit.chunk.document.filename,
            content=hit.chunk.content,
            page_number=hit.chunk.page_number,
            chunk_index=hit.chunk.chunk_index,
            score=hit.score,
        )
        for hit in hits
    ]
