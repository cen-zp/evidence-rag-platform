import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import knowledge_bases
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.evaluations import router as evaluations_router
from app.api.retrieval import router as retrieval_router
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models import Conversation, ConversationMessage, User
from app.schemas.chat import ChatCitation, ChatHistoryMessage, ChatRequest, ChatResponse
from app.services.auth import get_current_user
from app.services.deepseek import (
    DeepSeekInvalidCitationError,
    DeepSeekNotConfiguredError,
    DeepSeekProviderError,
    DeepSeekService,
    EvidencePrompt,
)
from app.services.model_usage import record_model_call
from app.services.retrieval import KnowledgeBaseRetriever, get_knowledge_base_retriever
from app.services.task_queue import close_document_task_queue


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await close_document_task_queue(app)

    app = FastAPI(title=active_settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.chat_service_factory = lambda: DeepSeekService(active_settings)
    app.state.knowledge_base_retriever_factory = get_knowledge_base_retriever
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[active_settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(knowledge_bases.router)
    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(evaluations_router)
    app.include_router(retrieval_router)

    @app.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "environment": active_settings.app_env}

    @app.post("/api/chat", response_model=ChatResponse, tags=["chat"])
    async def chat(
        request: ChatRequest,
        session: Session = Depends(get_session),
        current_user: User = Depends(get_current_user),
    ) -> ChatResponse:
        if request.knowledge_base_id is not None:
            knowledge_bases.get_knowledge_base_or_404(
                session,
                request.knowledge_base_id,
                current_user.id,
            )
            conversation = _get_or_create_conversation(session, request, current_user)
            history = (
                _conversation_history(session, conversation)
                if request.conversation_id is not None
                else request.history
            )
            try:
                retriever: KnowledgeBaseRetriever = app.state.knowledge_base_retriever_factory()
                hits = retriever.search(request.knowledge_base_id, request.message, top_k=5)
            except Exception as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Vector search is unavailable. Check Qdrant and try again.",
                ) from error

            if not hits:
                response = ChatResponse(
                    answer="我无法根据当前知识库中的资料回答这个问题。",
                    model="retrieval-guard",
                    latency_ms=0,
                    conversation_id=conversation.id,
                )
                response.assistant_message_id = _persist_conversation_turn(
                    session, conversation, request.message, response
                ).id
                session.commit()
                return response

            try:
                grounded = await app.state.chat_service_factory().chat_with_evidence(
                    request.message,
                    [
                        EvidencePrompt(chunk_id=hit.chunk.id, content=hit.chunk.content)
                        for hit in hits
                    ],
                    history,
                )
            except DeepSeekNotConfiguredError as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "AI provider is not configured. "
                        "Add DEEPSEEK_API_KEY to the local .env file."
                    ),
                ) from error
            except DeepSeekProviderError as error:
                raise HTTPException(status_code=error.status_code, detail=error.detail) from error
            except DeepSeekInvalidCitationError:
                response = ChatResponse(
                    answer="我无法根据当前检索到的资料生成带有效引用的回答。",
                    model="retrieval-guard",
                    latency_ms=0,
                    conversation_id=conversation.id,
                )
                response.assistant_message_id = _persist_conversation_turn(
                    session, conversation, request.message, response
                ).id
                session.commit()
                return response

            hits_by_id = {hit.chunk.id: hit for hit in hits}
            response = ChatResponse(
                answer=grounded.answer,
                model=grounded.model,
                latency_ms=grounded.latency_ms,
                citations=[
                    ChatCitation(
                        chunk_id=hit.chunk.id,
                        document_id=hit.chunk.document_id,
                        filename=hit.chunk.document.filename,
                        page_number=hit.chunk.page_number,
                        chunk_index=hit.chunk.chunk_index,
                        content=hit.chunk.content,
                    )
                    for citation_id in grounded.citation_ids
                    if (hit := hits_by_id.get(citation_id)) is not None
                ],
                usage=grounded.usage,
                conversation_id=conversation.id,
            )
            response.assistant_message_id = _persist_conversation_turn(
                session, conversation, request.message, response
            ).id
            record_model_call(
                session,
                request.knowledge_base_id,
                model=response.model,
                latency_ms=response.latency_ms,
                usage=response.usage,
            )
            return response

        try:
            service = app.state.chat_service_factory()
        except DeepSeekNotConfiguredError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "AI provider is not configured. Add DEEPSEEK_API_KEY to the local .env file."
                ),
            ) from error
        try:
            return await service.chat(request.message, request.history)
        except DeepSeekProviderError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    @app.post("/api/chat/stream", tags=["chat"])
    async def chat_stream(
        request: ChatRequest,
        session: Session = Depends(get_session),
        current_user: User = Depends(get_current_user),
    ) -> StreamingResponse:
        async def event_stream():
            yield _sse_event("status", {"phase": "retrieving"})
            try:
                response = await chat(request, session, current_user)
            except HTTPException as error:
                yield _sse_event(
                    "error",
                    {"status_code": error.status_code, "detail": str(error.detail)},
                )
                return
            except Exception:
                yield _sse_event(
                    "error",
                    {"status_code": 500, "detail": "The chat request could not be completed."},
                )
                return
            yield _sse_event("result", response.model_dump(mode="json", exclude_none=True))

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_or_create_conversation(
    session: Session,
    request: ChatRequest,
    current_user: User,
) -> Conversation:
    if request.conversation_id is not None:
        conversation = session.scalar(
            select(Conversation).where(
                Conversation.id == request.conversation_id,
                Conversation.knowledge_base_id == request.knowledge_base_id,
                Conversation.owner_id == current_user.id,
            )
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return conversation

    conversation = Conversation(
        knowledge_base_id=request.knowledge_base_id,
        owner_id=current_user.id,
        title=request.message.strip()[:120],
    )
    session.add(conversation)
    session.flush()
    return conversation


def _conversation_history(session: Session, conversation: Conversation) -> list[ChatHistoryMessage]:
    messages = list(
        session.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(6)
        )
    )
    return [
        ChatHistoryMessage(role=message.role, content=message.content[:2_000])
        for message in reversed(messages)
    ]


def _persist_conversation_turn(
    session: Session,
    conversation: Conversation,
    user_message: str,
    response: ChatResponse,
) -> ConversationMessage:
    assistant_message = ConversationMessage(
        conversation=conversation,
        role="assistant",
        content=response.answer,
        citations=[citation.model_dump(mode="json") for citation in response.citations],
        model=response.model,
        latency_ms=response.latency_ms,
    )
    session.add_all(
        [
            ConversationMessage(conversation=conversation, role="user", content=user_message),
            assistant_message,
        ]
    )
    conversation.updated_at = datetime.now(UTC)
    session.flush()
    return assistant_message


app = create_app()
