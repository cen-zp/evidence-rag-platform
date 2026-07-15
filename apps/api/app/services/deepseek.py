import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import UUID

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from app.core.config import Settings
from app.schemas.chat import ChatHistoryMessage, ChatResponse, ChatUsage


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
    usage: ChatUsage | None = None


@dataclass(frozen=True)
class ModelResponseMetadata:
    """Usage metadata for a provider completion, including guarded completions."""

    model: str
    latency_ms: int
    usage: ChatUsage | None = None


class DeepSeekNotConfiguredError(RuntimeError):
    """Raised when the local DeepSeek API key is unavailable."""


class DeepSeekInvalidCitationError(RuntimeError):
    """Raised when a model response is not grounded in the supplied evidence."""

    def __init__(self, detail: str, *, response: ModelResponseMetadata | None = None) -> None:
        super().__init__(detail)
        self.response = response


class DeepSeekProviderError(RuntimeError):
    """A safe, user-facing representation of a DeepSeek provider failure."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class DeepSeekService:
    def __init__(self, settings: Settings) -> None:
        if settings.deepseek_api_key is None:
            raise DeepSeekNotConfiguredError("DEEPSEEK_API_KEY is not configured")

        self._model = settings.deepseek_chat_model
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key.get_secret_value(),
            base_url=settings.deepseek_base_url,
            timeout=settings.deepseek_timeout_seconds,
            max_retries=0,
        )

    async def chat(self, message: str, history: list[ChatHistoryMessage]) -> ChatResponse:
        started_at = perf_counter()
        completion = await self._create_completion(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise assistant for an evidence-based knowledge platform."
                    ),
                },
                *[{"role": item.role, "content": item.content} for item in history],
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
            usage=_completion_usage(completion),
        )

    async def chat_with_evidence(
        self,
        message: str,
        evidence: list[EvidencePrompt],
        history: list[ChatHistoryMessage],
    ) -> GroundedModelResponse:
        started_at = perf_counter()
        source_keys = {f"S{index}": item.chunk_id for index, item in enumerate(evidence, start=1)}
        evidence_text = "\n\n".join(
            f"[source:{source_key}]\n{item.content}"
            for source_key, item in zip(source_keys, evidence, strict=True)
        )
        completion = await self._create_completion(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Answer only from supplied evidence. Return JSON with two keys: answer "
                        "(string) and citation_keys (a non-empty array of source labels such as "
                        "S1). Every citation key must exactly match a source label supplied in the "
                        "evidence. If the evidence is insufficient, return an empty answer and "
                        "empty citation_keys."
                    ),
                },
                *[{"role": item.role, "content": item.content} for item in history],
                {
                    "role": "user",
                    "content": f"Question:\n{message}\n\nEvidence:\n{evidence_text}",
                },
            ],
        )
        content = completion.choices[0].message.content
        response_metadata = ModelResponseMetadata(
            model=completion.model or self._model,
            latency_ms=round((perf_counter() - started_at) * 1000),
            usage=_completion_usage(completion),
        )
        if not content:
            raise DeepSeekInvalidCitationError(
                "DeepSeek returned an empty grounded response", response=response_metadata
            )

        try:
            payload = json.loads(content)
            answer = payload["answer"]
            citation_ids = _citation_ids_from_payload(payload, source_keys)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise DeepSeekInvalidCitationError(
                "DeepSeek returned invalid grounded JSON", response=response_metadata
            ) from error

        if not isinstance(answer, str) or not answer.strip() or not citation_ids:
            raise DeepSeekInvalidCitationError(
                "DeepSeek returned invalid citations", response=response_metadata
            )

        return GroundedModelResponse(
            answer=answer,
            citation_ids=list(dict.fromkeys(citation_ids)),
            model=response_metadata.model,
            latency_ms=response_metadata.latency_ms,
            usage=response_metadata.usage,
        )

    async def _create_completion(self, **kwargs: Any) -> Any:
        try:
            return await self._client.chat.completions.create(**kwargs)
        except APITimeoutError as error:
            raise DeepSeekProviderError(
                status_code=504,
                detail="AI provider timed out. Please try again.",
            ) from error
        except APIConnectionError as error:
            raise DeepSeekProviderError(
                status_code=502,
                detail="AI provider is unreachable. Please try again.",
            ) from error
        except APIStatusError as error:
            raise _provider_status_error(error) from error


def _citation_ids_from_payload(payload: dict[str, Any], source_keys: dict[str, UUID]) -> list[UUID]:
    """Map compact model-facing source labels back to immutable chunk IDs.

    UUIDs are difficult for a model to reproduce exactly.  The client-facing response
    still returns UUIDs, but the model only has to select from short, per-request labels.
    The legacy UUID key is accepted during rollout so an in-flight provider response
    cannot silently lose its citations.
    """
    citation_keys = payload.get("citation_keys")
    if isinstance(citation_keys, list):
        return [source_keys[str(item)] for item in citation_keys]

    legacy_citation_ids = payload.get("citation_ids")
    if not isinstance(legacy_citation_ids, list):
        raise ValueError("Grounded response is missing citation keys")
    citation_ids = [UUID(str(item)) for item in legacy_citation_ids]
    allowed_ids = set(source_keys.values())
    if not set(citation_ids).issubset(allowed_ids):
        raise ValueError("Grounded response contains an unknown citation")
    return citation_ids

def _provider_status_error(error: APIStatusError) -> DeepSeekProviderError:
    if error.status_code in {401, 403}:
        return DeepSeekProviderError(
            status_code=503,
            detail="AI provider authentication failed. Verify the local API key.",
        )
    if error.status_code == 429:
        return DeepSeekProviderError(
            status_code=429,
            detail="AI provider rate limit reached. Please retry shortly.",
        )
    return DeepSeekProviderError(
        status_code=502,
        detail="AI provider returned an upstream error. Please try again.",
    )


def _completion_usage(completion: Any) -> ChatUsage | None:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return None

    values = (
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
        getattr(usage, "total_tokens", None),
    )
    if not all(isinstance(value, int) and value >= 0 for value in values):
        return None

    return ChatUsage(
        prompt_tokens=values[0],
        completion_tokens=values[1],
        total_tokens=values[2],
    )
