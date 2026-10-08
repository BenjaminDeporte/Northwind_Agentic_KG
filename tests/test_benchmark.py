import pytest

from common.evaluation import aggregate_scores, load_benchmark, score_answer


def test_load_benchmark_preserves_questions_and_ground_truth_metadata():
    rows = load_benchmark("benchmark/northwind_questions.csv")
    assert len(rows) == 20
    assert rows[0].question == "Give me all your data"
    assert "Testing router refusal" in rows[0].comment


def test_score_answer_distinguishes_correct_wrong_and_missing():
    assert score_answer("There are 91 customers.", "91") == 1
    assert score_answer("I do not know.", "91") == -1
    assert score_answer(None, "91") == 0


def test_aggregate_scores_returns_counts_that_sum_to_question_count():
    assert aggregate_scores([1, 1, 0, -1]) == {
        "question_count": 4,
        "raw_score": 1,
        "accuracy_count": 2,
        "false_positive_count": 1,
        "no_answer_count": 1,
    }
    with pytest.raises(ValueError, match="-1, 0, or 1"):
        aggregate_scores([2])
