from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from math import ceil
from time import perf_counter

from pydantic import BaseModel, Field


class RetrievalEvaluationCase(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_filenames: list[str] = Field(min_length=1)


@dataclass(frozen=True)
class RetrievalEvaluationReport:
    case_count: int
    top_k: int
    recall_at_k: float
    mean_reciprocal_rank: float
    mean_latency_ms: float
    p95_latency_ms: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def evaluate_retrieval(
    cases: Sequence[RetrievalEvaluationCase],
    retrieve_filenames: Callable[[str, int], Sequence[str]],
    top_k: int,
) -> RetrievalEvaluationReport:
    if not cases:
        raise ValueError("At least one evaluation case is required")

    hit_count = 0
    reciprocal_ranks: list[float] = []
    latencies_ms: list[float] = []

    for case in cases:
        started_at = perf_counter()
        retrieved_filenames = retrieve_filenames(case.question, top_k)
        latencies_ms.append((perf_counter() - started_at) * 1000)

        expected_filenames = set(case.expected_filenames)
        matching_ranks = [
            rank
            for rank, filename in enumerate(retrieved_filenames, start=1)
            if filename in expected_filenames
        ]
        if matching_ranks:
            hit_count += 1
            reciprocal_ranks.append(1 / matching_ranks[0])
        else:
            reciprocal_ranks.append(0.0)

    sorted_latencies = sorted(latencies_ms)
    p95_index = ceil(len(sorted_latencies) * 0.95) - 1
    return RetrievalEvaluationReport(
        case_count=len(cases),
        top_k=top_k,
        recall_at_k=hit_count / len(cases),
        mean_reciprocal_rank=sum(reciprocal_ranks) / len(cases),
        mean_latency_ms=sum(latencies_ms) / len(cases),
        p95_latency_ms=sorted_latencies[p95_index],
    )
