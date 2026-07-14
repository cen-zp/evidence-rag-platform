from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.knowledge_bases import get_knowledge_base_or_404
from app.db.session import get_session
from app.evaluation.retrieval import RetrievalEvaluationCase, evaluate_retrieval
from app.models import EvaluationCase
from app.schemas.knowledge import (
    EvaluationCaseCreate,
    EvaluationCaseRead,
    RetrievalEvaluationReportRead,
)
from app.services.retrieval import KnowledgeBaseRetriever, get_knowledge_base_retriever

router = APIRouter(prefix="/api/knowledge-bases", tags=["evaluations"])


@router.post(
    "/{knowledge_base_id}/evaluation-cases",
    response_model=EvaluationCaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_evaluation_case(
    knowledge_base_id: UUID,
    payload: EvaluationCaseCreate,
    session: Session = Depends(get_session),
) -> EvaluationCase:
    get_knowledge_base_or_404(session, knowledge_base_id)
    evaluation_case = EvaluationCase(
        knowledge_base_id=knowledge_base_id,
        question=payload.question,
        expected_filenames=payload.expected_filenames,
        reference_answer=payload.reference_answer,
    )
    session.add(evaluation_case)
    session.commit()
    session.refresh(evaluation_case)
    return evaluation_case


@router.get("/{knowledge_base_id}/evaluation-cases", response_model=list[EvaluationCaseRead])
def list_evaluation_cases(
    knowledge_base_id: UUID,
    session: Session = Depends(get_session),
) -> list[EvaluationCase]:
    get_knowledge_base_or_404(session, knowledge_base_id)
    statement = (
        select(EvaluationCase)
        .where(EvaluationCase.knowledge_base_id == knowledge_base_id)
        .order_by(EvaluationCase.created_at.desc())
    )
    return list(session.scalars(statement))


@router.delete(
    "/{knowledge_base_id}/evaluation-cases/{evaluation_case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_evaluation_case(
    knowledge_base_id: UUID,
    evaluation_case_id: UUID,
    session: Session = Depends(get_session),
) -> None:
    get_knowledge_base_or_404(session, knowledge_base_id)
    evaluation_case = session.scalar(
        select(EvaluationCase).where(
            EvaluationCase.id == evaluation_case_id,
            EvaluationCase.knowledge_base_id == knowledge_base_id,
        )
    )
    if evaluation_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation case not found in this knowledge base",
        )
    session.delete(evaluation_case)
    session.commit()


@router.post(
    "/{knowledge_base_id}/evaluations/retrieval",
    response_model=RetrievalEvaluationReportRead,
)
def run_retrieval_evaluation(
    knowledge_base_id: UUID,
    top_k: int = 5,
    session: Session = Depends(get_session),
    retriever: KnowledgeBaseRetriever = Depends(get_knowledge_base_retriever),
) -> RetrievalEvaluationReportRead:
    if not 1 <= top_k <= 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="top_k must be 1-10",
        )

    get_knowledge_base_or_404(session, knowledge_base_id)
    evaluation_cases = list(
        session.scalars(
            select(EvaluationCase).where(EvaluationCase.knowledge_base_id == knowledge_base_id)
        )
    )
    cases = [
        RetrievalEvaluationCase(
            id=str(evaluation_case.id),
            question=evaluation_case.question,
            expected_filenames=evaluation_case.expected_filenames,
        )
        for evaluation_case in evaluation_cases
    ]
    if not cases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one evaluation case before running retrieval evaluation",
        )

    try:
        report = evaluate_retrieval(
            cases,
            lambda question, limit: [
                hit.chunk.document.filename
                for hit in retriever.search(knowledge_base_id, question, top_k=limit)
            ],
            top_k=top_k,
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retrieval evaluation is unavailable. Check Qdrant and try again.",
        ) from error

    return RetrievalEvaluationReportRead(**report.to_dict())
