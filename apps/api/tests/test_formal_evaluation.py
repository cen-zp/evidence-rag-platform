import json
from pathlib import Path

import pytest

from app.evaluation.formal import validate_formal_dataset
from app.evaluation.retrieval import RetrievalEvaluationCase


def create_cases(count: int = 60) -> list[RetrievalEvaluationCase]:
    return [
        RetrievalEvaluationCase(
            id=f"case-{index}",
            question=f"Independent question {index}?",
            expected_filenames=["source.md"],
        )
        for index in range(count)
    ]


def write_manifest(path) -> None:
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
            }
        ),
        encoding="utf-8",
    )


def test_formal_dataset_requires_independent_manifest_and_unique_60_cases(tmp_path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path)

    result = validate_formal_dataset(create_cases(), manifest_path, cases_path)

    assert result["case_count"] == 60
    assert result["dataset_origin"] == "independent"
    assert len(result["dataset_sha256"]) == 64


def test_committed_fastapi_dataset_is_a_reviewable_independent_draft() -> None:
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
    assert manifest["human_review_status"] == "needs_human_review"

    with pytest.raises(ValueError, match="Formal evaluation manifest is invalid"):
        validate_formal_dataset(cases, manifest_path, cases_path)


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
