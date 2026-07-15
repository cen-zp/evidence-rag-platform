import asyncio
import csv
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Protocol
from uuid import UUID, uuid4

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.evaluation.retrieval import RetrievalEvaluationCase
from app.schemas.chat import ChatUsage
from app.services.deepseek import (
    DeepSeekInvalidCitationError,
    DeepSeekProviderError,
    DeepSeekService,
    EvidencePrompt,
    GroundedModelResponse,
    ModelResponseMetadata,
)
from app.services.model_usage import record_model_call
from app.services.retrieval import RetrievalHit, create_knowledge_base_retriever

ANSWER_REVIEW_HEADERS = (
    "case_id",
    "question",
    "reference_answer",
    "answer",
    "citation_filenames",
    "citation_chunk_ids",
    "model",
    "model_latency_ms",
    "retrieval_latency_ms",
    "outcome",
    "review_status",
    "review_method",
    "answer_verdict",
    "citation_verdict",
    "refusal_verdict",
    "reviewer_alias",
    "reviewed_at_utc",
    "notes",
)


class Retriever(Protocol):
    def search(self, knowledge_base_id: UUID, query: str, top_k: int) -> list[RetrievalHit]: ...


class EvidenceChatService(Protocol):
    async def chat_with_evidence(
        self,
        message: str,
        evidence: list[EvidencePrompt],
        history: list,
    ) -> GroundedModelResponse: ...


@dataclass(frozen=True)
class BatchCitation:
    chunk_id: str
    filename: str
    content: str


@dataclass(frozen=True)
class AnswerBatchCaseResult:
    case_id: str
    question: str
    reference_answer: str | None
    outcome: str
    answer: str
    citations: list[BatchCitation]
    model: str | None
    model_latency_ms: int | None
    retrieval_latency_ms: float
    usage: ChatUsage | None


def _answer_result(
    case: RetrievalEvaluationCase,
    *,
    outcome: str,
    answer: str,
    citations: list[BatchCitation],
    model: str | None,
    model_latency_ms: int | None,
    retrieval_latency_ms: float,
    usage: ChatUsage | None,
) -> AnswerBatchCaseResult:
    return AnswerBatchCaseResult(
        case_id=case.id,
        question=case.question,
        reference_answer=case.reference_answer,
        outcome=outcome,
        answer=answer,
        citations=citations,
        model=model,
        model_latency_ms=model_latency_ms,
        retrieval_latency_ms=round(retrieval_latency_ms, 3),
        usage=usage,
    )


async def run_answer_batch(
    knowledge_base_id: UUID,
    cases: Sequence[RetrievalEvaluationCase],
    retriever: Retriever,
    chat_service: EvidenceChatService,
    on_model_response: Callable[[ModelResponseMetadata], None] | None = None,
    top_k: int = 5,
) -> list[AnswerBatchCaseResult]:
    """Generate grounded answers without assigning any automated quality verdict."""
    if not cases:
        raise ValueError("At least one evaluation case is required")
    if top_k < 1:
        raise ValueError("top_k must be positive")

    results: list[AnswerBatchCaseResult] = []
    for case in cases:
        retrieval_started_at = perf_counter()
        try:
            hits = retriever.search(knowledge_base_id, case.question, top_k=top_k)
        except Exception:
            results.append(
                _answer_result(
                    case,
                    outcome="retrieval_error",
                    answer="",
                    citations=[],
                    model=None,
                    model_latency_ms=None,
                    retrieval_latency_ms=(perf_counter() - retrieval_started_at) * 1000,
                    usage=None,
                )
            )
            continue

        retrieval_latency_ms = (perf_counter() - retrieval_started_at) * 1000
        if not hits:
            results.append(
                _answer_result(
                    case,
                    outcome="retrieval_guard_no_hits",
                    answer="我无法根据当前知识库中的资料回答这个问题。",
                    citations=[],
                    model="retrieval-guard",
                    model_latency_ms=0,
                    retrieval_latency_ms=retrieval_latency_ms,
                    usage=None,
                )
            )
            continue

        try:
            grounded = await chat_service.chat_with_evidence(
                case.question,
                [EvidencePrompt(chunk_id=hit.chunk.id, content=hit.chunk.content) for hit in hits],
                [],
            )
        except DeepSeekInvalidCitationError as error:
            if error.response is not None and on_model_response is not None:
                on_model_response(error.response)
            results.append(
                _answer_result(
                    case,
                    outcome="retrieval_guard_invalid_citation",
                    answer="我无法根据当前检索到的资料生成带有效引用的回答。",
                    citations=[],
                    model=error.response.model if error.response is not None else "retrieval-guard",
                    model_latency_ms=(
                        error.response.latency_ms if error.response is not None else 0
                    ),
                    retrieval_latency_ms=retrieval_latency_ms,
                    usage=error.response.usage if error.response is not None else None,
                )
            )
            continue
        except DeepSeekProviderError:
            results.append(
                _answer_result(
                    case,
                    outcome="provider_error",
                    answer="",
                    citations=[],
                    model=None,
                    model_latency_ms=None,
                    retrieval_latency_ms=retrieval_latency_ms,
                    usage=None,
                )
            )
            continue

        if on_model_response is not None:
            on_model_response(grounded)
        hits_by_id = {hit.chunk.id: hit for hit in hits}
        citations = [
            BatchCitation(
                chunk_id=str(hit.chunk.id),
                filename=hit.chunk.document.filename,
                content=hit.chunk.content,
            )
            for citation_id in grounded.citation_ids
            if (hit := hits_by_id.get(citation_id)) is not None
        ]
        results.append(
            _answer_result(
                case,
                outcome="answered",
                answer=grounded.answer,
                citations=citations,
                model=grounded.model,
                model_latency_ms=grounded.latency_ms,
                retrieval_latency_ms=retrieval_latency_ms,
                usage=grounded.usage,
            )
        )
    return results


def build_answer_batch_report(
    results: Sequence[AnswerBatchCaseResult],
    *,
    batch_id: UUID | None = None,
    pricing_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    model_latencies = sorted(
        result.model_latency_ms
        for result in results
        if result.outcome == "answered" and result.model_latency_ms is not None
    )
    usage = [result.usage for result in results if result.usage is not None]
    model_completions = [
        result
        for result in results
        if result.model is not None and result.model != "retrieval-guard"
    ]
    completion_latencies = sorted(
        result.model_latency_ms
        for result in model_completions
        if result.model_latency_ms is not None
    )
    completion_p95_index = ceil(len(completion_latencies) * 0.95) - 1 if completion_latencies else 0
    input_price = (
        pricing_snapshot.get("input_cost_per_million_tokens")
        if pricing_snapshot is not None
        else None
    )
    output_price = (
        pricing_snapshot.get("output_cost_per_million_tokens")
        if pricing_snapshot is not None
        else None
    )
    estimated_costs = [
        cost
        for result in model_completions
        if (cost := _estimate_usage_cost(result.usage, input_price, output_price)) is not None
    ]
    p95_index = ceil(len(model_latencies) * 0.95) - 1 if model_latencies else 0
    return {
        "case_count": len(results),
        "answered_count": sum(result.outcome == "answered" for result in results),
        "guarded_count": sum(result.outcome.startswith("retrieval_guard") for result in results),
        "failed_count": sum(
            result.outcome in {"provider_error", "retrieval_error"} for result in results
        ),
        "mean_model_latency_ms": (
            sum(model_latencies) / len(model_latencies) if model_latencies else None
        ),
        "p95_model_latency_ms": model_latencies[p95_index] if model_latencies else None,
        "prompt_tokens": sum(item.prompt_tokens for item in usage),
        "completion_tokens": sum(item.completion_tokens for item in usage),
        "total_tokens": sum(item.total_tokens for item in usage),
        "usage_reported_count": len(usage),
        "estimated_cost_coverage_count": len(estimated_costs),
        "estimated_total_cost": round(sum(estimated_costs), 8) if estimated_costs else None,
        "estimated_mean_cost_per_model_completion": (
            round(sum(estimated_costs) / len(model_completions), 8)
            if len(estimated_costs) == len(model_completions) and model_completions
            else None
        ),
        "model_completion_count": len(model_completions),
        "mean_model_completion_latency_ms": (
            sum(completion_latencies) / len(completion_latencies) if completion_latencies else None
        ),
        "p95_model_completion_latency_ms": (
            completion_latencies[completion_p95_index] if completion_latencies else None
        ),
        "batch_id": str(batch_id) if batch_id is not None else None,
        "pricing_snapshot": pricing_snapshot,
        "cases": [
            {
                **asdict(result),
                "usage": result.usage.model_dump() if result.usage is not None else None,
                "estimated_cost": _estimate_usage_cost(result.usage, input_price, output_price),
            }
            for result in results
        ],
    }


def _estimate_usage_cost(
    usage: ChatUsage | None,
    input_cost_per_million_tokens: object,
    output_cost_per_million_tokens: object,
) -> float | None:
    if (
        usage is None
        or not isinstance(input_cost_per_million_tokens, (int, float))
        or not isinstance(output_cost_per_million_tokens, (int, float))
    ):
        return None
    return round(
        (
            usage.prompt_tokens * input_cost_per_million_tokens
            + usage.completion_tokens * output_cost_per_million_tokens
        )
        / 1_000_000,
        8,
    )


def write_answer_review_sheet(results: Sequence[AnswerBatchCaseResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=ANSWER_REVIEW_HEADERS)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "case_id": result.case_id,
                    "question": result.question,
                    "reference_answer": result.reference_answer or "",
                    "answer": result.answer,
                    "citation_filenames": "; ".join(
                        citation.filename for citation in result.citations
                    ),
                    "citation_chunk_ids": "; ".join(
                        citation.chunk_id for citation in result.citations
                    ),
                    "model": result.model or "",
                    "model_latency_ms": result.model_latency_ms or "",
                    "retrieval_latency_ms": result.retrieval_latency_ms,
                    "outcome": result.outcome,
                    "review_status": "pending",
                    "review_method": "",
                    "answer_verdict": "pending",
                    "citation_verdict": "pending",
                    "refusal_verdict": "pending",
                    "reviewer_alias": "",
                    "reviewed_at_utc": "",
                    "notes": "",
                }
            )


def _record_model_response(
    knowledge_base_id: UUID, settings: Settings, batch_id: UUID
) -> Callable[[ModelResponseMetadata], None]:
    session_factory = get_session_factory()

    def callback(response: ModelResponseMetadata) -> None:
        with session_factory() as session:
            record_model_call(
                session,
                knowledge_base_id,
                batch_id=batch_id,
                model=response.model,
                latency_ms=response.latency_ms,
                usage=response.usage,
                input_cost_per_million_tokens=settings.deepseek_input_cost_per_million_tokens,
                output_cost_per_million_tokens=settings.deepseek_output_cost_per_million_tokens,
                cost_currency=settings.deepseek_cost_currency,
            )

    return callback


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a paid grounded-answer batch and create a blank human-review worksheet"
    )
    parser.add_argument("--knowledge-base-id", required=True, type=UUID)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review-output", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--disable-reranker", action="store_true")
    parser.add_argument("--pricing-source-url")
    parser.add_argument("--pricing-checked-at-utc")
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive")

    from app.evaluation.runner import build_run_metadata, load_cases

    settings = get_settings()
    if (settings.deepseek_input_cost_per_million_tokens is None) != (
        settings.deepseek_output_cost_per_million_tokens is None
    ):
        parser.error("Configure both DeepSeek token prices or neither one")
    if (
        settings.deepseek_input_cost_per_million_tokens is not None
        and (not args.pricing_source_url or not args.pricing_checked_at_utc)
    ):
        parser.error(
            "Configured token prices require --pricing-source-url and --pricing-checked-at-utc"
        )
    batch_id = uuid4()
    reranker_enabled = not args.disable_reranker
    results = asyncio.run(
        run_answer_batch(
            args.knowledge_base_id,
            load_cases(args.cases),
            create_knowledge_base_retriever(reranker_enabled=reranker_enabled),
            DeepSeekService(settings),
            on_model_response=_record_model_response(args.knowledge_base_id, settings, batch_id),
            top_k=args.top_k,
        )
    )
    report = build_answer_batch_report(
        results,
        batch_id=batch_id,
        pricing_snapshot={
            "source_url": args.pricing_source_url,
            "checked_at_utc": args.pricing_checked_at_utc,
            "currency": settings.deepseek_cost_currency,
            "input_price_basis": "cache_miss",
            "input_cost_per_million_tokens": settings.deepseek_input_cost_per_million_tokens,
            "output_cost_per_million_tokens": settings.deepseek_output_cost_per_million_tokens,
        },
    )
    report["run_metadata"] = build_run_metadata(settings, reranker_enabled, warmup_queries=0) | {
        "top_k": args.top_k
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_answer_review_sheet(results, args.review_output)
    print(
        "Answer batch completed: "
        f"answered={report['answered_count']}, guarded={report['guarded_count']}, "
        f"failed={report['failed_count']}, review_sheet={args.review_output}"
    )


if __name__ == "__main__":
    main()
