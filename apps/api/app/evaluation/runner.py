import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

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
) -> RetrievalEvaluationReport:
    retriever = create_knowledge_base_retriever(reranker_enabled=reranker_enabled)

    def retrieve_filenames(question: str, limit: int) -> list[str]:
        return [
            hit.chunk.document.filename
            for hit in retriever.search(knowledge_base_id, question, top_k=limit)
        ]

    return evaluate_retrieval(cases, retrieve_filenames, top_k=top_k)


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
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive")

    reranker_enabled = not args.disable_reranker
    report = run(
        args.knowledge_base_id,
        load_cases(args.cases),
        args.top_k,
        reranker_enabled=reranker_enabled,
    )
    report_data = report.to_dict() | {"reranker_enabled": reranker_enabled}
    serialized_report = json.dumps(report_data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized_report + "\n", encoding="utf-8")
    print(serialized_report)


if __name__ == "__main__":
    main()
