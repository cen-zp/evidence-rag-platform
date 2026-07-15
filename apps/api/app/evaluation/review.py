import csv
from collections.abc import Sequence
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.evaluation.retrieval import RetrievalEvaluationCase

REVIEW_HEADERS = (
    "case_id",
    "question",
    "reference_answer",
    "expected_filenames",
    "review_status",
    "question_verdict",
    "reference_answer_verdict",
    "source_label_verdict",
    "reviewer_alias",
    "reviewed_at_utc",
    "notes",
)


class CaseReview(BaseModel):
    case_id: str = Field(min_length=1)
    review_status: Literal["approved"]
    question_verdict: Literal["pass"]
    reference_answer_verdict: Literal["pass"]
    source_label_verdict: Literal["pass"]
    reviewer_alias: str = Field(min_length=2, max_length=120)
    reviewed_at_utc: datetime


def write_review_sheet(cases: Sequence[RetrievalEvaluationCase], output_path: Path) -> None:
    """Create an editable CSV worksheet without asserting that any review occurred."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=REVIEW_HEADERS)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case.id,
                    "question": case.question,
                    "reference_answer": case.reference_answer or "",
                    "expected_filenames": "; ".join(case.expected_filenames),
                    "review_status": "pending",
                    "question_verdict": "",
                    "reference_answer_verdict": "",
                    "source_label_verdict": "",
                    "reviewer_alias": "",
                    "reviewed_at_utc": "",
                    "notes": "",
                }
            )


def validate_case_reviews(
    cases: Sequence[RetrievalEvaluationCase], review_path: Path
) -> dict[str, str | int]:
    """Verify that every formal case has an explicit, declared human review record.

    The CSV is an audit artifact, not proof of a reviewer's real-world identity. The
    project documentation requires that the named reviewer is independent of the
    dataset author before a formal result can be claimed.
    """
    try:
        with review_path.open(encoding="utf-8-sig", newline="") as input_file:
            reader = csv.DictReader(input_file)
            if reader.fieldnames is None or set(REVIEW_HEADERS) - set(reader.fieldnames):
                raise ValueError("Review sheet is missing required columns")
            rows = list(reader)
    except OSError as error:
        raise ValueError("Formal evaluation review sheet is unavailable") from error

    reviews: dict[str, CaseReview] = {}
    for line_number, row in enumerate(rows, start=2):
        try:
            review = CaseReview.model_validate(row)
        except ValueError as error:
            raise ValueError(f"Invalid review on line {line_number}") from error
        if review.case_id in reviews:
            raise ValueError("Formal evaluation review case IDs must be unique")
        reviews[review.case_id] = review

    expected_case_ids = {case.id for case in cases}
    reviewed_case_ids = set(reviews)
    if reviewed_case_ids != expected_case_ids:
        raise ValueError("Formal evaluation review sheet must cover exactly the case set")

    cases_by_id = {case.id: case for case in cases}
    for row in rows:
        case = cases_by_id[row["case_id"]]
        if (
            row["question"] != case.question
            or row["reference_answer"] != (case.reference_answer or "")
            or row["expected_filenames"] != "; ".join(case.expected_filenames)
        ):
            raise ValueError("Formal evaluation review sheet must preserve case content")

    return {
        "reviewed_case_count": len(reviews),
        "reviewer_count": len({review.reviewer_alias for review in reviews.values()}),
        "review_sha256": sha256(review_path.read_bytes()).hexdigest(),
    }
