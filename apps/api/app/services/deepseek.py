import json
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID

from openai import AsyncOpenAI

from app.core.config import Settings
from app.schemas.chat import ChatResponse


class DeepSeekNotConfiguredError(RuntimeError):
    """Raised when the local DeepSeek API key is unavailable."""


class DeepSeekInvalidCitationError(RuntimeError):
    """Raised when a model response is not grounded in the supplied evidence."""


@dataclass(frozen=True)
class EvidencePrompt:
    chunk_id: UUID
    content: str


@dataclass(frozen=True)
class GroundedModelResponse:
    answer: str
    citation_ids: list[UUID]
    model: str
    latency_ms: int


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

    async def chat_with_evidence(
        self,
        message: str,
        evidence: list[EvidencePrompt],
    ) -> GroundedModelResponse:
        started_at = perf_counter()
        evidence_text = "\n\n".join(
            f"[source:{item.chunk_id}]\n{item.content}" for item in evidence
        )
        completion = await self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Answer only from supplied evidence. Return JSON with two keys: answer "
                        "(string) and citation_ids (a non-empty array of source UUID strings). "
                        "Every citation ID must be a source ID supplied in the evidence. If the "
                        "evidence is insufficient, return an empty answer and empty citation_ids."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question:\n{message}\n\nEvidence:\n{evidence_text}",
                },
            ],
        )
        content = completion.choices[0].message.content
        if not content:
            raise DeepSeekInvalidCitationError("DeepSeek returned an empty grounded response")

        try:
            payload = json.loads(content)
            answer = payload["answer"]
            citation_ids = [UUID(item) for item in payload["citation_ids"]]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise DeepSeekInvalidCitationError("DeepSeek returned invalid grounded JSON") from error

        allowed_ids = {item.chunk_id for item in evidence}
        citations_are_valid = citation_ids and set(citation_ids).issubset(allowed_ids)
        if not isinstance(answer, str) or not citations_are_valid:
            raise DeepSeekInvalidCitationError("DeepSeek returned invalid citations")

        return GroundedModelResponse(
            answer=answer,
            citation_ids=list(dict.fromkeys(citation_ids)),
            model=completion.model or self._model,
            latency_ms=round((perf_counter() - started_at) * 1000),
        )
