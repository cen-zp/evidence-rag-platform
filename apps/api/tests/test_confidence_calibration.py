import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.evaluation.confidence import (
    ConfidenceSample,
    evaluate_threshold,
    select_threshold,
)


def sample(case_id: str, label: str, score: float, expected_hit: bool = False):
    return ConfidenceSample(
        case_id=case_id,
        label=label,
        top_score=score,
        expected_hit=expected_hit,
        top_filenames=[],
    )


def test_select_threshold_preserves_supported_cases_and_rejects_unsupported_cases() -> None:
    samples = [
        sample("s1", "supported", 0.8, expected_hit=True),
        sample("s2", "supported", 0.2, expected_hit=True),
        sample("u1", "unsupported", 0.1),
        sample("u2", "unsupported", 0.01),
    ]

    result = select_threshold(
        samples,
        minimum_supported_acceptance=1.0,
        threshold_step=0.1,
    )

    assert result.threshold == 0.2
    assert result.supported_acceptance == 1.0
    assert result.unsupported_rejection == 1.0
    assert result.expected_retrieval_recall_after_threshold == 1.0


def test_threshold_metrics_report_guard_tradeoffs() -> None:
    result = evaluate_threshold(
        [
            sample("s1", "supported", 0.8, expected_hit=True),
            sample("s2", "supported", 0.1),
            sample("u1", "unsupported", 0.3),
            sample("u2", "unsupported", 0.01),
        ],
        threshold=0.2,
    )

    assert result.supported_acceptance == 0.5
    assert result.unsupported_rejection == 0.5
    assert result.supported_false_refusal_count == 1
    assert result.unsupported_false_acceptance_count == 1
    assert result.expected_retrieval_recall_at_k == 0.5
    assert result.expected_retrieval_recall_after_threshold == 0.5


def test_threshold_metrics_require_both_labels() -> None:
    with pytest.raises(ValueError, match="both supported and unsupported"):
        evaluate_threshold([sample("s1", "supported", 0.8)], threshold=0.2)


def test_default_threshold_matches_the_committed_calibration_report() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    report = json.loads(
        (
            repository_root
            / "evals/results/fastapi-official-confidence-calibration.json"
        ).read_text(encoding="utf-8")
    )

    settings = Settings(_env_file=None)

    assert settings.reranker_enabled is True
    assert settings.retrieval_min_score == report["selected_threshold"]
