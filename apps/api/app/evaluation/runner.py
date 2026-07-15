import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.core.config import Settings, get_settings
from app.evaluation.formal import validate_formal_dataset
from app.evaluation.retrieval import (
    RetrievalEvaluationCase,
    RetrievalEvaluationReport,
    evaluate_retrieval,
)
from app.services.retrieval import create_knowledge_base_retriever


def load_cases(path: Path) -> list[RetrievalEvaluationCase]:
    cases: list[RetrievalEvaluationCase] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            cases.append(RetrievalEvaluationCase.model_validate_json(raw_line))
        except ValueError as error:
            raise ValueError(f"Invalid evaluation case on line {line_number}") from error
    return cases


def run(
    knowledge_base_id: UUID,
    cases: Sequence[RetrievalEvaluationCase],
    top_k: int,
    reranker_enabled: bool = True,
    warmup_queries: int = 0,
) -> RetrievalEvaluationReport:
    if warmup_queries < 0:
        raise ValueError("warmup_queries must not be negative")
    retriever = create_knowledge_base_retriever(reranker_enabled=reranker_enabled)

    def retrieve_filenames(question: str, limit: int) -> list[str]:
        return [
            hit.chunk.document.filename
            for hit in retriever.search(knowledge_base_id, question, top_k=limit)
        ]

    for case in cases[:warmup_queries]:
        retrieve_filenames(case.question, top_k)

    return evaluate_retrieval(cases, retrieve_filenames, top_k=top_k)


def build_run_metadata(
    settings: Settings, reranker_enabled: bool, warmup_queries: int
) -> dict[str, object]:
    """Capture retrieval settings that affect a report without exposing secrets."""
    return {
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "embedding_device": settings.embedding_device,
        "qdrant_collection": settings.qdrant_collection,
        "reranker_model": settings.reranker_model if reranker_enabled else None,
        "reranker_candidate_count": settings.reranker_candidate_count
        if reranker_enabled
        else None,
        "retrieval_min_score": settings.retrieval_min_score if reranker_enabled else None,
        "warmup_queries_excluded": warmup_queries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against a JSONL case set")
    parser.add_argument("--knowledge-base-id", required=True, type=UUID)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--disable-reranker",
        action="store_true",
        help="Evaluate the Dense + BM25 + RRF baseline without CrossEncoder reranking",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--warmup-queries",
        type=int,
        default=0,
        help="Run the first N cases before measurement to warm local retrieval models",
    )
    parser.add_argument(
        "--formal-manifest",
        type=Path,
        help=(
            "Require a 60-100 case independent dataset and include provenance hashes in the report"
        ),
    )
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive")
    if args.warmup_queries < 0:
        parser.error("--warmup-queries must not be negative")

    reranker_enabled = not args.disable_reranker
    cases = load_cases(args.cases)
    formal_dataset = (
        validate_formal_dataset(cases, args.formal_manifest, args.cases)
        if args.formal_manifest
        else None
    )
    report = run(
        args.knowledge_base_id,
        cases,
        args.top_k,
        reranker_enabled=reranker_enabled,
        warmup_queries=args.warmup_queries,
    )
    report_data = report.to_dict() | {
        "reranker_enabled": reranker_enabled,
        "run_metadata": build_run_metadata(
            get_settings(), reranker_enabled, args.warmup_queries
        ),
    }
    if formal_dataset is not None:
        report_data["formal_dataset"] = formal_dataset
    serialized_report = json.dumps(report_data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized_report + "\n", encoding="utf-8")
    print(serialized_report)


if __name__ == "__main__":
    main()
