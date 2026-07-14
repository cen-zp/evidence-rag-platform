from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)
    knowledge_base_id: UUID | None = None


class ChatCitation(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int | None
    chunk_index: int
    content: str


class ChatResponse(BaseModel):
    answer: str
    model: str
    latency_ms: int
    citations: list[ChatCitation] = Field(default_factory=list)
