import csv
import json
from pathlib import Path

import pytest

from app.evaluation.formal import validate_formal_dataset
from app.evaluation.retrieval import RetrievalEvaluationCase
from app.evaluation.review import REVIEW_HEADERS, write_review_sheet


def create_cases(count: int = 60) -> list[RetrievalEvaluationCase]:
    return [
        RetrievalEvaluationCase(
            id=f"case-{index}",
            question=f"Independent question {index}?",
            expected_filenames=["source.md"],
        )
        for index in range(count)
    ]


def write_manifest(path, review_file: str = "reviews.csv") -> None:
    path.write_text(
        json.dumps(
            {
                "dataset_name": "Independent test set",
                "dataset_origin": "independent",
                "corpus_description": (
                    "Questions are evaluated against an independently selected corpus."
                ),
                "question_authoring": (
                    "Questions were written without copying the source document wording."
                ),
                "source_labeling": (
                    "Expected source files were manually labeled before retrieval runs."
                ),
                "human_review_status": "approved",
                "review_file": review_file,
            }
        ),
        encoding="utf-8",
    )


def write_approved_reviews(path: Path, cases: list[RetrievalEvaluationCase]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=REVIEW_HEADERS)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case.id,
                    "question": case.question,
                    "reference_answer": case.reference_answer or "",
                    "expected_filenames": "; ".join(case.expected_filenames),
                    "review_status": "approved",
                    "question_verdict": "pass",
                    "reference_answer_verdict": "pass",
                    "source_label_verdict": "pass",
                    "reviewer_alias": "reviewer-01",
                    "reviewed_at_utc": "2026-07-15T10:00:00+00:00",
                    "notes": "",
                }
            )


def test_formal_dataset_requires_independent_manifest_and_unique_60_cases(tmp_path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path)
    cases = create_cases()
    write_approved_reviews(tmp_path / "reviews.csv", cases)

    result = validate_formal_dataset(cases, manifest_path, cases_path)

    assert result["case_count"] == 60
    assert result["dataset_origin"] == "independent"
    assert len(result["dataset_sha256"]) == 64
    assert result["reviewed_case_count"] == 60
    assert result["reviewer_count"] == 1
    assert len(result["review_sha256"]) == 64


def test_review_sheet_exports_pending_cases_and_formal_mode_requires_all_approvals(
    tmp_path: Path,
) -> None:
    cases = create_cases()
    review_path = tmp_path / "reviews.csv"
    write_review_sheet(cases, review_path)
    with review_path.open(encoding="utf-8-sig", newline="") as input_file:
        rows = list(csv.DictReader(input_file))

    assert len(rows) == 60
    assert {row["review_status"] for row in rows} == {"pending"}
    assert rows[0]["reference_answer"] == ""

    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path)
    with pytest.raises(ValueError, match="Invalid review"):
        validate_formal_dataset(cases, manifest_path, cases_path)

    write_approved_reviews(review_path, cases[:-1])
    with pytest.raises(ValueError, match="cover exactly"):
        validate_formal_dataset(cases, manifest_path, cases_path)


def test_committed_fastapi_dataset_is_human_reviewed_and_formal_ready() -> None:
    project_root = Path(__file__).resolve().parents[3]
    cases_path = project_root / "evals" / "independent" / "fastapi-official-cases.jsonl"
    manifest_path = project_root / "evals" / "independent" / "fastapi-official.manifest.json"

    cases = [
        RetrievalEvaluationCase.model_validate_json(line)
        for line in cases_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(cases) == 72
    assert len({case.id for case in cases}) == 72
    assert len({case.question for case in cases}) == 72
    assert manifest["dataset_origin"] == "independent"
    assert manifest["human_review_status"] == "approved"

    result = validate_formal_dataset(cases, manifest_path, cases_path)
    assert result["reviewed_case_count"] == 72
    assert result["reviewer_count"] == 1


def test_formal_dataset_rejects_wrong_case_count_and_duplicate_questions(tmp_path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path)

    with pytest.raises(ValueError, match="60-100"):
        validate_formal_dataset(create_cases(59), manifest_path, cases_path)

    cases = create_cases()
    cases[1] = RetrievalEvaluationCase(
        id="case-1", question=cases[0].question, expected_filenames=["source.md"]
    )
    with pytest.raises(ValueError, match="questions must be unique"):
        validate_formal_dataset(cases, manifest_path, cases_path)
