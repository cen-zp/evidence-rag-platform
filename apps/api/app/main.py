from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.knowledge_bases import router as knowledge_bases_router
from app.core.config import Settings, get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.deepseek import DeepSeekNotConfiguredError, DeepSeekService
from app.services.task_queue import close_document_task_queue


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await close_document_task_queue(app)

    app = FastAPI(title=active_settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[active_settings.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(knowledge_bases_router)

    @app.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "environment": active_settings.app_env}

    @app.post("/api/chat", response_model=ChatResponse, tags=["chat"])
    async def chat(request: ChatRequest) -> ChatResponse:
        try:
            service = DeepSeekService(active_settings)
        except DeepSeekNotConfiguredError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "AI provider is not configured. Add DEEPSEEK_API_KEY to the local .env file."
                ),
            ) from error

        return await service.chat(request.message)

    return app


app = create_app()
