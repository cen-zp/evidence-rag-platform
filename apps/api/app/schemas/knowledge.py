from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2_000)


class KnowledgeBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID | None
    name: str
    description: str | None
    created_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_base_id: UUID
    filename: str
    mime_type: str
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=10)


class RetrievalHitRead(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    content: str
    page_number: int | None
    chunk_index: int
    score: float


class EvaluationCaseCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    expected_filenames: list[str] = Field(min_length=1, max_length=10)
    reference_answer: str | None = Field(default=None, max_length=8_000)


class EvaluationCaseRead(EvaluationCaseCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_base_id: UUID
    created_at: datetime


class RetrievalEvaluationReportRead(BaseModel):
    case_count: int
    top_k: int
    recall_at_k: float
    mean_reciprocal_rank: float
    mean_latency_ms: float
    p95_latency_ms: float


class ReviewVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class AnswerReviewCreate(BaseModel):
    answer: str = Field(min_length=1, max_length=8_000)
    model: str = Field(min_length=1, max_length=120)
    latency_ms: int = Field(ge=0, le=600_000)
    citation_chunk_ids: list[UUID] = Field(default_factory=list, max_length=5)
    answer_verdict: ReviewVerdict
    citation_verdict: ReviewVerdict
    refusal_verdict: ReviewVerdict
    notes: str | None = Field(default=None, max_length=2_000)


class AnswerReviewRead(AnswerReviewCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evaluation_case_id: UUID
    citation_filenames: list[str]
    created_at: datetime


class AnswerReviewSummaryRead(BaseModel):
    case_count: int
    review_count: int
    unreviewed_case_count: int
    answer_pass_rate: float | None
    citation_pass_rate: float | None
    refusal_pass_rate: float | None


class ModelUsageSummaryRead(BaseModel):
    call_count: int
    usage_reported_call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    mean_latency_ms: float | None
    p95_latency_ms: float | None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_base_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str
    citations: list[dict]
    model: str | None
    latency_ms: int | None
    created_at: datetime


class MessageFeedbackCreate(BaseModel):
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=2_000)


class MessageFeedbackRead(MessageFeedbackCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message_id: UUID
    created_at: datetime
