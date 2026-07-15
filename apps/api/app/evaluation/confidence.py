import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, Field

from app.services.bm25 import rank_bm25
from app.services.chunking import chunk_pages
from app.services.document_parsing import parse_document
from app.services.embedding import LocalBgeEmbedding
from app.services.reranker import LocalBgeReranker
from app.services.retrieval import _reciprocal_rank_fusion


class UnsupportedCalibrationCase(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    reason: str = Field(min_length=10)


@dataclass(frozen=True)
class ConfidenceSample:
    case_id: str
    label: str
    top_score: float
    expected_hit: bool
    top_filenames: list[str]


@dataclass(frozen=True)
class ThresholdMetrics:
    threshold: float
    supported_acceptance: float
    unsupported_rejection: float
    balanced_accuracy: float
    supported_false_refusal_count: int
    unsupported_false_acceptance_count: int
    expected_retrieval_recall_at_k: float
    expected_retrieval_recall_after_threshold: float


def evaluate_threshold(
    samples: list[ConfidenceSample], threshold: float
) -> ThresholdMetrics:
    supported = [sample for sample in samples if sample.label == "supported"]
    unsupported = [sample for sample in samples if sample.label == "unsupported"]
    if not supported or not unsupported:
        raise ValueError("Calibration requires both supported and unsupported samples")

    supported_accepted = [sample for sample in supported if sample.top_score >= threshold]
    unsupported_rejected = [sample for sample in unsupported if sample.top_score < threshold]
    expected_hits = [sample for sample in supported if sample.expected_hit]
    expected_hits_after_threshold = [
        sample for sample in expected_hits if sample.top_score >= threshold
    ]
    supported_acceptance = len(supported_accepted) / len(supported)
    unsupported_rejection = len(unsupported_rejected) / len(unsupported)
    return ThresholdMetrics(
        threshold=threshold,
        supported_acceptance=supported_acceptance,
        unsupported_rejection=unsupported_rejection,
        balanced_accuracy=(supported_acceptance + unsupported_rejection) / 2,
        supported_false_refusal_count=len(supported) - len(supported_accepted),
        unsupported_false_acceptance_count=len(unsupported) - len(unsupported_rejected),
        expected_retrieval_recall_at_k=len(expected_hits) / len(supported),
        expected_retrieval_recall_after_threshold=len(expected_hits_after_threshold)
        / len(supported),
    )


def select_threshold(
    samples: list[ConfidenceSample],
    *,
    minimum_supported_acceptance: float,
    threshold_step: float,
) -> ThresholdMetrics:
    if not 0 < minimum_supported_acceptance <= 1:
        raise ValueError("minimum_supported_acceptance must be in (0, 1]")
    if not 0 < threshold_step <= 1:
        raise ValueError("threshold_step must be in (0, 1]")

    step_count = round(1 / threshold_step)
    candidates = [
        evaluate_threshold(samples, round(index * threshold_step, 10))
        for index in range(step_count + 1)
    ]
    eligible = [
        metrics
        for metrics in candidates
        if metrics.supported_acceptance >= minimum_supported_acceptance
    ]
    if not eligible:
        raise ValueError("No threshold preserves the requested supported acceptance")
    return max(
        eligible,
        key=lambda metrics: (
            metrics.unsupported_rejection,
            metrics.balanced_accuracy,
            metrics.threshold,
        ),
    )


def _load_supported_cases(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_unsupported_cases(path: Path) -> list[UnsupportedCalibrationCase]:
    return [
        UnsupportedCalibrationCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _corpus_hash(paths: list[Path]) -> str:
    digest = sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run_calibration(
    *,
    corpus_dir: Path,
    supported_cases_path: Path,
    unsupported_cases_path: Path,
    embedding_model: str,
    reranker_model: str,
    device: str,
    top_k: int,
    candidate_count: int,
    minimum_supported_acceptance: float,
    threshold_step: float,
) -> dict[str, object]:
    corpus_paths = sorted(corpus_dir.glob("*.md"))
    if not corpus_paths:
        raise ValueError("Calibration corpus must contain Markdown files")
    supported_cases = _load_supported_cases(supported_cases_path)
    unsupported_cases = _load_unsupported_cases(unsupported_cases_path)

    chunks: list[tuple[UUID, str, str]] = []
    for path in corpus_paths:
        for index, (content, _, _) in enumerate(
            chunk_pages(parse_document(path, "text/markdown"))
        ):
            chunk_id = uuid5(NAMESPACE_URL, f"{path.name}:{index}:{content}")
            chunks.append((chunk_id, path.name, content))

    questions = [str(case["question"]) for case in supported_cases] + [
        case.question for case in unsupported_cases
    ]
    embedding = LocalBgeEmbedding(
        model_name=embedding_model,
        dimension=512,
        device=device,
    )
    reranker = LocalBgeReranker(model_name=reranker_model, device=device)
    document_vectors = embedding.embed_documents([content for _, _, content in chunks])
    query_vectors = embedding.embed_documents(questions)
    chunk_texts = [(chunk_id, content) for chunk_id, _, content in chunks]
    content_by_id = {chunk_id: content for chunk_id, _, content in chunks}
    filename_by_id = {chunk_id: filename for chunk_id, filename, _ in chunks}

    samples: list[ConfidenceSample] = []
    for question_index, (question, query_vector) in enumerate(
        zip(questions, query_vectors, strict=True)
    ):
        dense_ranked = sorted(
            (
                (
                    chunk_id,
                    sum(a * b for a, b in zip(query_vector, vector, strict=True)),
                )
                for (chunk_id, _, _), vector in zip(chunks, document_vectors, strict=True)
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        dense_ranks = {
            chunk_id: rank
            for rank, (chunk_id, _) in enumerate(dense_ranked[:20], start=1)
        }
        lexical_ranks = {
            chunk_id: rank
            for rank, chunk_id in enumerate(rank_bm25(question, chunk_texts), start=1)
        }
        fused_scores = _reciprocal_rank_fusion(dense_ranks, lexical_ranks)
        candidate_ids = [
            chunk_id
            for chunk_id, _ in sorted(
                fused_scores.items(), key=lambda item: item[1], reverse=True
            )[:candidate_count]
        ]
        reranked = reranker.rerank(
            question,
            [(chunk_id, content_by_id[chunk_id]) for chunk_id in candidate_ids],
        )[:top_k]
        if not reranked:
            raise ValueError(f"Calibration produced no candidates for question {question_index}")

        if question_index < len(supported_cases):
            case = supported_cases[question_index]
            expected_filenames = set(case["expected_filenames"])
            label = "supported"
            case_id = str(case["id"])
        else:
            case = unsupported_cases[question_index - len(supported_cases)]
            expected_filenames = set()
            label = "unsupported"
            case_id = case.id
        top_filenames = [filename_by_id[result.chunk_id] for result in reranked]
        samples.append(
            ConfidenceSample(
                case_id=case_id,
                label=label,
                top_score=round(reranked[0].score, 8),
                expected_hit=bool(expected_filenames.intersection(top_filenames)),
                top_filenames=top_filenames,
            )
        )

    selected = select_threshold(
        samples,
        minimum_supported_acceptance=minimum_supported_acceptance,
        threshold_step=threshold_step,
    )
    return {
        "calibrated_at_utc": datetime.now(UTC).isoformat(),
        "method": "offline_labeled_top_reranker_score",
        "selected_threshold": selected.threshold,
        "selection_constraints": {
            "minimum_supported_acceptance": minimum_supported_acceptance,
            "threshold_step": threshold_step,
        },
        "metrics": asdict(selected),
        "sample_count": len(samples),
        "supported_count": len(supported_cases),
        "unsupported_count": len(unsupported_cases),
        "chunk_count": len(chunks),
        "top_k": top_k,
        "embedding_model": embedding_model,
        "reranker_model": reranker_model,
        "reranker_candidate_count": candidate_count,
        "device": device,
        "corpus_sha256": _corpus_hash(corpus_paths),
        "supported_cases_sha256": sha256(supported_cases_path.read_bytes()).hexdigest(),
        "unsupported_cases_sha256": sha256(unsupported_cases_path.read_bytes()).hexdigest(),
        "evidence_boundary": (
            "The supported cases retain their existing single-reviewer provenance. "
            "The unsupported cases are developer-curated obvious out-of-corpus topics, "
            "not an independent third-party review."
        ),
        "samples": [asdict(sample) for sample in samples],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate a low-confidence guard without calling a language model"
    )
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--supported-cases", required=True, type=Path)
    parser.add_argument("--unsupported-cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--reranker-model", default="BAAI/bge-reranker-base")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-count", type=int, default=10)
    parser.add_argument("--minimum-supported-acceptance", type=float, default=0.9)
    parser.add_argument("--threshold-step", type=float, default=0.01)
    args = parser.parse_args()
    if args.top_k < 1 or args.candidate_count < args.top_k:
        parser.error("candidate-count must be at least top-k, and top-k must be positive")

    report = run_calibration(
        corpus_dir=args.corpus_dir,
        supported_cases_path=args.supported_cases,
        unsupported_cases_path=args.unsupported_cases,
        embedding_model=args.embedding_model,
        reranker_model=args.reranker_model,
        device=args.device,
        top_k=args.top_k,
        candidate_count=args.candidate_count,
        minimum_supported_acceptance=args.minimum_supported_acceptance,
        threshold_step=args.threshold_step,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Confidence calibration completed: "
        f"threshold={report['selected_threshold']}, output={args.output}"
    )


if __name__ == "__main__":
    main()
