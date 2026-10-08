"""Canonical benchmark loading and deliberately conservative answer scoring."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class BenchmarkQuestion:
    group: str
    question: str
    expected_answer: str
    comment: str


def load_benchmark(path: str | Path) -> list[BenchmarkQuestion]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [
            BenchmarkQuestion(
                group=row["Group"],
                question=row["Question"],
                expected_answer=row["Answer"],
                comment=row["Comment"],
            )
            for row in csv.DictReader(handle)
        ]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def score_answer(answer: str | None, expected_answer: str) -> int:
    """Return 1, 0, or -1 using a transparent first-pass heuristic."""
    if not answer or not answer.strip():
        return 0
    return 1 if _normalize(expected_answer) in _normalize(answer) else -1


def aggregate_scores(scores: Iterable[int]) -> dict[str, int]:
    """Aggregate question scores and enforce the three-outcome contract."""
    values = list(scores)
    invalid = [score for score in values if score not in {-1, 0, 1}]
    if invalid:
        raise ValueError(f"Scores must be -1, 0, or 1; got {invalid!r}")
    summary = {
        "question_count": len(values),
        "raw_score": sum(values),
        "accuracy_count": values.count(1),
        "false_positive_count": values.count(-1),
        "no_answer_count": values.count(0),
    }
    if (
        summary["accuracy_count"]
        + summary["false_positive_count"]
        + summary["no_answer_count"]
        != summary["question_count"]
    ):
        raise AssertionError("Benchmark outcome counts must sum to question_count")
    return summary


__all__ = ["BenchmarkQuestion", "aggregate_scores", "load_benchmark", "score_answer"]
