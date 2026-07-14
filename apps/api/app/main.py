from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api import knowledge_bases
from app.api.evaluations import router as evaluations_router
from app.api.retrieval import router as retrieval_router
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas.chat import ChatCitation, ChatRequest, ChatResponse
from app.services.deepseek import (
    DeepSeekInvalidCitationError,
    DeepSeekNotConfiguredError,
    DeepSeekProviderError,
    DeepSeekService,
    EvidencePrompt,
)
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
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(knowledge_bases.router)
    app.include_router(evaluations_router)
    app.include_router(retrieval_router)

    @app.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "environment": active_settings.app_env}

    @app.post("/api/chat", response_model=ChatResponse, tags=["chat"])
    async def chat(
        request: ChatRequest,
        session: Session = Depends(get_session),
    ) -> ChatResponse:
        if request.knowledge_base_id is not None:
            knowledge_bases.get_knowledge_base_or_404(session, request.knowledge_base_id)
            try:
                retriever: KnowledgeBaseRetriever = app.state.knowledge_base_retriever_factory()
                hits = retriever.search(request.knowledge_base_id, request.message, top_k=5)
            except Exception as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Vector search is unavailable. Check Qdrant and try again.",
                ) from error

            if not hits:
                return ChatResponse(
                    answer="我无法根据当前知识库中的资料回答这个问题。",
                    model="retrieval-guard",
                    latency_ms=0,
                )

            try:
                grounded = await app.state.chat_service_factory().chat_with_evidence(
                    request.message,
                    [
                        EvidencePrompt(chunk_id=hit.chunk.id, content=hit.chunk.content)
                        for hit in hits
                    ],
                    request.history,
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
                return ChatResponse(
                    answer="我无法根据当前检索到的资料生成带有效引用的回答。",
                    model="retrieval-guard",
                    latency_ms=0,
                )

            hits_by_id = {hit.chunk.id: hit for hit in hits}
            return ChatResponse(
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
            )

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

    return app


app = create_app()
