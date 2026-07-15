import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.services.deepseek import (
    DeepSeekInvalidCitationError,
    DeepSeekService,
    EvidencePrompt,
)


def _service_with_response(content: str) -> tuple[DeepSeekService, dict]:
    service = DeepSeekService(Settings(app_env="test", deepseek_api_key="test-key", _env_file=None))
    captured: dict = {}

    async def create_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model="test-model",
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=None,
        )

    service._create_completion = create_completion  # type: ignore[method-assign]
    return service, captured


def test_grounded_chat_uses_compact_source_keys_and_maps_them_to_chunk_ids() -> None:
    first_chunk_id, second_chunk_id = uuid4(), uuid4()
    service, captured = _service_with_response(
        '{"answer":"Use the documented approach.","citation_keys":["S2"]}'
    )

    response = asyncio.run(
        service.chat_with_evidence(
            "How do I do this?",
            [
                EvidencePrompt(chunk_id=first_chunk_id, content="First source."),
                EvidencePrompt(chunk_id=second_chunk_id, content="Second source."),
            ],
            [],
        )
    )

    assert response.citation_ids == [second_chunk_id]
    assert "citation_keys" in captured["messages"][0]["content"]
    assert "[source:S1]" in captured["messages"][-1]["content"]
    assert "[source:S2]" in captured["messages"][-1]["content"]
    assert str(first_chunk_id) not in captured["messages"][-1]["content"]


def test_grounded_chat_rejects_unknown_compact_source_key() -> None:
    service, _ = _service_with_response('{"answer":"Unsupported.","citation_keys":["S9"]}')

    with pytest.raises(DeepSeekInvalidCitationError):
        asyncio.run(
            service.chat_with_evidence(
                "How do I do this?", [EvidencePrompt(chunk_id=uuid4(), content="Source.")], []
            )
        )


def test_grounded_chat_accepts_a_valid_legacy_uuid_response_during_rollout() -> None:
    chunk_id = uuid4()
    service, _ = _service_with_response(
        f'{{"answer":"Supported.","citation_ids":["{chunk_id}"]}}'
    )

    response = asyncio.run(
        service.chat_with_evidence(
            "How do I do this?", [EvidencePrompt(chunk_id=chunk_id, content="Source.")], []
        )
    )

    assert response.citation_ids == [chunk_id]
