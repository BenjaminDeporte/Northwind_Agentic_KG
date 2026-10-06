import pytest

from common.config.models import CypherModelCandidate
from common.evaluation.model_selection import ModelRunResult, select_baseline


def test_select_baseline_uses_score_then_accuracy_and_is_deterministic():
    a = CypherModelCandidate("model-a", "test")
    b = CypherModelCandidate("model-b", "test")
    selected = select_baseline(
        [
            ModelRunResult(a, raw_score=10, accuracy_count=15, false_positive_count=5, no_answer_count=0),
            ModelRunResult(b, raw_score=10, accuracy_count=16, false_positive_count=4, no_answer_count=0),
        ]
    )
    assert selected.candidate == b


def test_select_baseline_requires_results():
    with pytest.raises(ValueError, match="At least one"):
        select_baseline([])
