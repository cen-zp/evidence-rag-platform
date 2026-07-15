from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_serializer


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)
    knowledge_base_id: UUID | None = None
    conversation_id: UUID | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=6)


class ChatCitation(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int | None
    chunk_index: int
    content: str


class ChatUsage(BaseModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class ChatResponse(BaseModel):
    answer: str
    model: str
    latency_ms: int
    retrieval_latency_ms: int | None = None
    total_latency_ms: int | None = None
    citations: list[ChatCitation] = Field(default_factory=list)
    usage: ChatUsage | None = None
    conversation_id: UUID | None = None
    assistant_message_id: UUID | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        result = handler(self)
        for optional_field in ("usage", "retrieval_latency_ms", "total_latency_ms"):
            if result.get(optional_field) is None:
                result.pop(optional_field, None)
        return result
