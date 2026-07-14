from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.knowledge_bases import get_knowledge_base_or_404
from app.db.session import get_session
from app.evaluation.retrieval import RetrievalEvaluationCase, evaluate_retrieval
from app.models import AnswerReview, DocumentChunk, EvaluationCase, ModelCall, User
from app.schemas.knowledge import (
    AnswerReviewCreate,
    AnswerReviewRead,
    AnswerReviewSummaryRead,
    EvaluationCaseCreate,
    EvaluationCaseRead,
    ModelUsageSummaryRead,
    RetrievalEvaluationReportRead,
    ReviewVerdict,
)
from app.services.auth import get_current_user
from app.services.retrieval import get_knowledge_base_retriever

router = APIRouter(prefix="/api/knowledge-bases", tags=["evaluations"])


def get_evaluation_case_or_404(
    session: Session,
    knowledge_base_id: UUID,
    evaluation_case_id: UUID,
) -> EvaluationCase:
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
    return evaluation_case


@router.post(
    "/{knowledge_base_id}/evaluation-cases",
    response_model=EvaluationCaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_evaluation_case(
    knowledge_base_id: UUID,
    payload: EvaluationCaseCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> EvaluationCase:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
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
    current_user: User = Depends(get_current_user),
) -> list[EvaluationCase]:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
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
    current_user: User = Depends(get_current_user),
) -> None:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    evaluation_case = get_evaluation_case_or_404(session, knowledge_base_id, evaluation_case_id)
    session.delete(evaluation_case)
    session.commit()


@router.post(
    "/{knowledge_base_id}/evaluation-cases/{evaluation_case_id}/answer-reviews",
    response_model=AnswerReviewRead,
    status_code=status.HTTP_201_CREATED,
)
def create_answer_review(
    knowledge_base_id: UUID,
    evaluation_case_id: UUID,
    payload: AnswerReviewCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AnswerReview:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    evaluation_case = get_evaluation_case_or_404(session, knowledge_base_id, evaluation_case_id)
    if len(set(payload.citation_chunk_ids)) != len(payload.citation_chunk_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Citation chunk IDs must be unique",
        )

    chunks = list(
        session.scalars(
            select(DocumentChunk)
            .options(selectinload(DocumentChunk.document))
            .where(
                DocumentChunk.knowledge_base_id == knowledge_base_id,
                DocumentChunk.id.in_(payload.citation_chunk_ids),
            )
        )
    )
    chunks_by_id = {chunk.id: chunk for chunk in chunks}
    if len(chunks_by_id) != len(payload.citation_chunk_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Citation chunks must belong to the current knowledge base",
        )

    answer_review = AnswerReview(
        evaluation_case=evaluation_case,
        answer=payload.answer,
        model=payload.model,
        latency_ms=payload.latency_ms,
        citation_chunk_ids=[str(chunk_id) for chunk_id in payload.citation_chunk_ids],
        citation_filenames=[
            chunks_by_id[chunk_id].document.filename for chunk_id in payload.citation_chunk_ids
        ],
        answer_verdict=payload.answer_verdict,
        citation_verdict=payload.citation_verdict,
        refusal_verdict=payload.refusal_verdict,
        notes=payload.notes,
    )
    session.add(answer_review)
    session.commit()
    session.refresh(answer_review)
    return answer_review


@router.get(
    "/{knowledge_base_id}/evaluation-cases/{evaluation_case_id}/answer-reviews",
    response_model=list[AnswerReviewRead],
)
def list_answer_reviews(
    knowledge_base_id: UUID,
    evaluation_case_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AnswerReview]:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    get_evaluation_case_or_404(session, knowledge_base_id, evaluation_case_id)
    statement = (
        select(AnswerReview)
        .where(AnswerReview.evaluation_case_id == evaluation_case_id)
        .order_by(AnswerReview.created_at.desc())
    )
    return list(session.scalars(statement))


@router.get(
    "/{knowledge_base_id}/evaluations/answer-review-summary",
    response_model=AnswerReviewSummaryRead,
)
def get_answer_review_summary(
    knowledge_base_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AnswerReviewSummaryRead:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    evaluation_cases = list(
        session.scalars(
            select(EvaluationCase)
            .options(selectinload(EvaluationCase.answer_reviews))
            .where(EvaluationCase.knowledge_base_id == knowledge_base_id)
        )
    )
    reviews = [
        review for evaluation_case in evaluation_cases for review in evaluation_case.answer_reviews
    ]

    def pass_rate(attribute: str) -> float | None:
        applicable_reviews = [
            review
            for review in reviews
            if getattr(review, attribute) != ReviewVerdict.NOT_APPLICABLE
        ]
        if not applicable_reviews:
            return None
        return sum(
            getattr(review, attribute) == ReviewVerdict.PASS for review in applicable_reviews
        ) / len(applicable_reviews)

    return AnswerReviewSummaryRead(
        case_count=len(evaluation_cases),
        review_count=len(reviews),
        unreviewed_case_count=sum(
            not evaluation_case.answer_reviews for evaluation_case in evaluation_cases
        ),
        answer_pass_rate=pass_rate("answer_verdict"),
        citation_pass_rate=pass_rate("citation_verdict"),
        refusal_pass_rate=pass_rate("refusal_verdict"),
    )


@router.get(
    "/{knowledge_base_id}/evaluations/model-usage-summary",
    response_model=ModelUsageSummaryRead,
)
def get_model_usage_summary(
    knowledge_base_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ModelUsageSummaryRead:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    calls = list(
        session.scalars(
            select(ModelCall)
            .where(ModelCall.knowledge_base_id == knowledge_base_id)
            .order_by(ModelCall.created_at.asc())
        )
    )
    latencies = sorted(call.latency_ms for call in calls)
    p95_index = max(0, (len(latencies) * 95 + 99) // 100 - 1)

    return ModelUsageSummaryRead(
        call_count=len(calls),
        usage_reported_call_count=sum(call.total_tokens is not None for call in calls),
        prompt_tokens=sum(call.prompt_tokens or 0 for call in calls),
        completion_tokens=sum(call.completion_tokens or 0 for call in calls),
        total_tokens=sum(call.total_tokens or 0 for call in calls),
        mean_latency_ms=(sum(latencies) / len(latencies)) if latencies else None,
        p95_latency_ms=latencies[p95_index] if latencies else None,
    )


@router.post(
    "/{knowledge_base_id}/evaluations/retrieval",
    response_model=RetrievalEvaluationReportRead,
)
def run_retrieval_evaluation(
    knowledge_base_id: UUID,
    top_k: int = 5,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RetrievalEvaluationReportRead:
    if not 1 <= top_k <= 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="top_k must be 1-10",
        )

    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
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
        retriever = get_knowledge_base_retriever()
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
