from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.evaluation.retrieval import RetrievalEvaluationCase
from app.evaluation.review import validate_case_reviews


class FormalEvaluationManifest(BaseModel):
    dataset_name: str = Field(min_length=3, max_length=120)
    dataset_origin: str = Field(pattern="^independent$")
    corpus_description: str = Field(min_length=20, max_length=2_000)
    question_authoring: str = Field(min_length=20, max_length=2_000)
    source_labeling: str = Field(min_length=20, max_length=2_000)
    human_review_status: Literal["approved"]
    review_file: str = Field(min_length=1, max_length=255)


def validate_formal_dataset(
    cases: list[RetrievalEvaluationCase], manifest_path: Path, case_path: Path
) -> dict[str, str | int]:
    if not 60 <= len(cases) <= 100:
        raise ValueError("Formal evaluation datasets must contain 60-100 cases")

    case_ids = [case.id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Formal evaluation dataset case IDs must be unique")

    normalized_questions = [" ".join(case.question.split()).casefold() for case in cases]
    if len(set(normalized_questions)) != len(normalized_questions):
        raise ValueError("Formal evaluation dataset questions must be unique")

    try:
        manifest = FormalEvaluationManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise ValueError("Formal evaluation manifest is invalid") from error

    review_path = manifest_path.parent / manifest.review_file
    review_evidence = validate_case_reviews(cases, review_path)
    return {
        "dataset_name": manifest.dataset_name,
        "dataset_origin": manifest.dataset_origin,
        "case_count": len(cases),
        "dataset_sha256": sha256(case_path.read_bytes()).hexdigest(),
        "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
        **review_evidence,
    }
