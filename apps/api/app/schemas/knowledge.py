from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2_000)


class KnowledgeBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
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
