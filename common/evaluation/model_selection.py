"""Deterministic bookkeeping for the Architecture 1 Cypher-model sweep."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from common.config.models import CypherModelCandidate


@dataclass(frozen=True)
class ModelRunResult:
    candidate: CypherModelCandidate
    raw_score: int
    accuracy_count: int
    false_positive_count: int
    no_answer_count: int
    run_id: str | None = None


def select_baseline(results: Iterable[ModelRunResult]) -> ModelRunResult:
    """Select the strongest candidate using the agreed score and stable ties.

    The actual model calls and MLflow runs are deliberately outside this pure
    selector. This keeps selection reproducible once the sweep artifact exists.
    """
    materialized = list(results)
    if not materialized:
        raise ValueError("At least one model run is required")
    return max(
        materialized,
        key=lambda item: (
            item.raw_score,
            item.accuracy_count,
            -item.false_positive_count,
            item.candidate.name,
        ),
    )


__all__ = ["ModelRunResult", "select_baseline"]
