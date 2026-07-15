"""Audit helpers for a completed grounded-answer batch.

This module deliberately validates a human-filled worksheet instead of assigning
quality verdicts automatically.  Its output is an integrity record for a batch,
not evidence of a reviewer's real-world identity or independence.
"""

import argparse
import csv
import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.evaluation.answer_batch import ANSWER_REVIEW_HEADERS


class AnswerBatchReview(BaseModel):
    case_id: str = Field(min_length=1)
    review_status: Literal["approved"]
    answer_verdict: Literal["pass", "fail", "not_applicable"]
    citation_verdict: Literal["pass", "fail", "not_applicable"]
    refusal_verdict: Literal["pass", "fail", "not_applicable"]
    reviewer_alias: str = Field(min_length=2, max_length=120)
    reviewed_at_utc: str = Field(min_length=20, max_length=40)


def _report_text(value: object) -> str:
    return "" if value is None else str(value)


def _citation_values(case: dict[str, Any]) -> tuple[str, str]:
    citations = case.get("citations", [])
    return (
        "; ".join(str(citation["filename"]) for citation in citations),
        "; ".join(str(citation["chunk_id"]) for citation in citations),
    )


def _expected_row(case: dict[str, Any]) -> dict[str, str]:
    citation_filenames, citation_chunk_ids = _citation_values(case)
    return {
        "case_id": _report_text(case.get("case_id")),
        "question": _report_text(case.get("question")),
        "reference_answer": _report_text(case.get("reference_answer")),
        "answer": _report_text(case.get("answer")),
        "citation_filenames": citation_filenames,
        "citation_chunk_ids": citation_chunk_ids,
        "model": _report_text(case.get("model")),
        "model_latency_ms": _report_text(case.get("model_latency_ms")),
        "retrieval_latency_ms": _report_text(case.get("retrieval_latency_ms")),
        "outcome": _report_text(case.get("outcome")),
    }


def write_pending_answer_review_sheet(report: dict[str, Any], output_path: Path) -> None:
    """Create or refresh a blank worksheet from a saved batch without model calls."""
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Answer batch report must contain at least one case")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=ANSWER_REVIEW_HEADERS)
        writer.writeheader()
        for case in cases:
            if not isinstance(case, dict):
                raise ValueError("Answer batch report contains an invalid case")
            writer.writerow(
                {
                    **_expected_row(case),
                    "review_status": "pending",
                    "answer_verdict": "pending",
                    "citation_verdict": "pending",
                    "refusal_verdict": "pending",
                    "reviewer_alias": "",
                    "reviewed_at_utc": "",
                    "notes": "",
                }
            )


def _validate_verdicts(row: AnswerBatchReview, outcome: str) -> None:
    if outcome == "answered":
        if row.answer_verdict == "not_applicable" or row.citation_verdict == "not_applicable":
            raise ValueError("Answered cases require answer and citation verdicts")
        if row.refusal_verdict != "not_applicable":
            raise ValueError("Answered cases require refusal_verdict=not_applicable")
        return
    if outcome.startswith("retrieval_guard_"):
        if row.answer_verdict != "not_applicable" or row.citation_verdict != "not_applicable":
            raise ValueError("Guarded cases require non-answer verdicts to be not_applicable")
        if row.refusal_verdict == "not_applicable":
            raise ValueError("Guarded cases require a refusal verdict")
        return
    if outcome in {"provider_error", "retrieval_error"}:
        if any(
            verdict != "not_applicable"
            for verdict in (row.answer_verdict, row.citation_verdict, row.refusal_verdict)
        ):
            raise ValueError("Failed cases require all verdicts to be not_applicable")
        return
    raise ValueError("Answer batch report has an unsupported outcome")


def _pass_rate(rows: list[AnswerBatchReview], attribute: str) -> float | None:
    applicable = [row for row in rows if getattr(row, attribute) != "not_applicable"]
    if not applicable:
        return None
    return sum(getattr(row, attribute) == "pass" for row in applicable) / len(applicable)


def validate_answer_batch_reviews(
    report_path: Path, review_path: Path
) -> dict[str, str | int | float | None]:
    """Validate a fully completed worksheet against one immutable batch report."""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        cases = report["cases"]
    except (OSError, ValueError, KeyError) as error:
        raise ValueError("Answer batch report is unavailable or invalid") from error
    if not isinstance(cases, list) or len(cases) != report.get("case_count"):
        raise ValueError("Answer batch report case count is invalid")

    expected_rows: dict[str, dict[str, str]] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Answer batch report contains an invalid case")
        expected = _expected_row(case)
        case_id = expected["case_id"]
        if not case_id or case_id in expected_rows:
            raise ValueError("Answer batch report case IDs must be unique")
        expected_rows[case_id] = expected

    try:
        with review_path.open(encoding="utf-8-sig", newline="") as input_file:
            reader = csv.DictReader(input_file)
            if reader.fieldnames is None or set(ANSWER_REVIEW_HEADERS) - set(reader.fieldnames):
                raise ValueError("Answer review sheet is missing required columns")
            raw_rows = list(reader)
    except OSError as error:
        raise ValueError("Answer review sheet is unavailable") from error

    reviews: dict[str, AnswerBatchReview] = {}
    for line_number, raw_row in enumerate(raw_rows, start=2):
        try:
            review = AnswerBatchReview.model_validate(raw_row)
        except ValueError as error:
            raise ValueError(f"Invalid answer review on line {line_number}") from error
        if review.case_id in reviews:
            raise ValueError("Answer review case IDs must be unique")
        expected = expected_rows.get(review.case_id)
        if expected is None:
            raise ValueError("Answer review sheet contains an unknown case")
        for field, expected_value in expected.items():
            if raw_row.get(field, "") != expected_value:
                raise ValueError("Answer review sheet must preserve generated batch content")
        _validate_verdicts(review, expected["outcome"])
        reviews[review.case_id] = review

    if set(reviews) != set(expected_rows):
        raise ValueError("Answer review sheet must cover exactly the batch case set")

    completed_reviews = list(reviews.values())
    return {
        "case_count": len(completed_reviews),
        "reviewer_count": len({review.reviewer_alias for review in completed_reviews}),
        "report_sha256": sha256(report_path.read_bytes()).hexdigest(),
        "review_sha256": sha256(review_path.read_bytes()).hexdigest(),
        "answer_pass_rate": _pass_rate(completed_reviews, "answer_verdict"),
        "citation_pass_rate": _pass_rate(completed_reviews, "citation_verdict"),
        "refusal_pass_rate": _pass_rate(completed_reviews, "refusal_verdict"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or validate an answer review worksheet")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument(
        "--initialize",
        action="store_true",
        help="write a blank pending worksheet from the report without model calls",
    )
    args = parser.parse_args()

    if args.initialize:
        try:
            report = json.loads(args.report.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SystemExit("Answer batch report is unavailable or invalid") from error
        write_pending_answer_review_sheet(report, args.review)
        print(f"Pending answer review sheet written to {args.review}")
        return

    print(json.dumps(validate_answer_batch_reviews(args.report, args.review), ensure_ascii=False))


if __name__ == "__main__":
    main()
