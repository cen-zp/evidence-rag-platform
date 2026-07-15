import csv
import json
from pathlib import Path

import pytest

from app.evaluation.answer_review import (
    validate_answer_batch_reviews,
    write_pending_answer_review_sheet,
)


def _report() -> dict:
    return {
        "case_count": 3,
        "cases": [
            {
                "case_id": "answer-1",
                "question": "How do I test an API?",
                "reference_answer": "Use TestClient.",
                "outcome": "answered",
                "answer": "Use TestClient.",
                "citations": [
                    {"chunk_id": "chunk-1", "filename": "testing.md", "content": "ignored"}
                ],
                "model": "test-model",
                "model_latency_ms": 123,
                "retrieval_latency_ms": 4.5,
                "usage": None,
            },
            {
                "case_id": "guard-1",
                "question": "Unknown?",
                "reference_answer": None,
                "outcome": "retrieval_guard_no_hits",
                "answer": "I cannot answer.",
                "citations": [],
                "model": "retrieval-guard",
                "model_latency_ms": 0,
                "retrieval_latency_ms": 2.0,
                "usage": None,
            },
            {
                "case_id": "error-1",
                "question": "Unavailable?",
                "reference_answer": None,
                "outcome": "provider_error",
                "answer": "",
                "citations": [],
                "model": None,
                "model_latency_ms": None,
                "retrieval_latency_ms": 1.0,
                "usage": None,
            },
        ],
    }


def _complete_sheet(path: Path) -> None:
    with path.open(encoding="utf-8-sig", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
        headers = input_file.seek(0) or next(csv.reader(input_file))
    rows[0].update(
        review_status="approved",
        answer_verdict="pass",
        citation_verdict="pass",
        refusal_verdict="not_applicable",
        reviewer_alias="reviewer-a",
        reviewed_at_utc="2026-07-15T12:00:00+00:00",
    )
    rows[1].update(
        review_status="approved",
        answer_verdict="not_applicable",
        citation_verdict="not_applicable",
        refusal_verdict="pass",
        reviewer_alias="reviewer-a",
        reviewed_at_utc="2026-07-15T12:00:00+00:00",
    )
    rows[2].update(
        review_status="approved",
        answer_verdict="not_applicable",
        citation_verdict="not_applicable",
        refusal_verdict="not_applicable",
        reviewer_alias="reviewer-a",
        reviewed_at_utc="2026-07-15T12:00:00+00:00",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_answer_review_requires_completed_matching_sheet(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.csv"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    write_pending_answer_review_sheet(_report(), review_path)

    with pytest.raises(ValueError, match="Invalid answer review"):
        validate_answer_batch_reviews(report_path, review_path)

    _complete_sheet(review_path)
    result = validate_answer_batch_reviews(report_path, review_path)

    assert result["case_count"] == 3
    assert result["answer_pass_rate"] == 1.0
    assert result["citation_pass_rate"] == 1.0
    assert result["refusal_pass_rate"] == 1.0
