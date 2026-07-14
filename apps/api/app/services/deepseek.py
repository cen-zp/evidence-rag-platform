from time import perf_counter

from openai import AsyncOpenAI

from app.core.config import Settings
from app.schemas.chat import ChatResponse


class DeepSeekNotConfiguredError(RuntimeError):
    """Raised when the local DeepSeek API key is unavailable."""


class DeepSeekService:
    def __init__(self, settings: Settings) -> None:
        if settings.deepseek_api_key is None:
            raise DeepSeekNotConfiguredError("DEEPSEEK_API_KEY is not configured")

        self._model = settings.deepseek_chat_model
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key.get_secret_value(),
            base_url=settings.deepseek_base_url,
        )

    async def chat(self, message: str) -> ChatResponse:
        started_at = perf_counter()
        completion = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise assistant for an evidence-based knowledge platform."
                    ),
                },
                {"role": "user", "content": message},
            ],
        )
        answer = completion.choices[0].message.content
        if not answer:
            raise RuntimeError("DeepSeek returned an empty response")

        return ChatResponse(
            answer=answer,
            model=completion.model or self._model,
            latency_ms=round((perf_counter() - started_at) * 1000),
        )
