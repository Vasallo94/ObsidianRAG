"""Tests for retrieval evaluation metrics and dataset validation."""

import json

import pytest
from langchain_core.documents import Document

from obsidianrag.evaluation import (
    EvaluationCase,
    _bootstrap_mean_ci,
    compare_evaluation_results,
    evaluate_retrieval,
    load_dataset,
)


def test_load_dataset_validates_and_normalizes_sources(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "question": "Where is the project plan?",
                        "expected_sources": ["./Projects\\Plan.md"],
                    }
                ]
            }
        )
    )

    cases = load_dataset(dataset)

    assert cases == (
        EvaluationCase(
            question="Where is the project plan?",
            expected_sources=("Projects/Plan.md",),
        ),
    )


def test_load_dataset_parses_graded_relevance(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "question": "Which source matters most?",
                        "expected_sources": ["Primary.md", "Related.md"],
                        "relevance_grades": [
                            {"source": "Primary.md", "grade": 3},
                            {"source": "Related.md", "grade": 1},
                        ],
                    }
                ]
            }
        )
    )

    assert load_dataset(dataset)[0].relevance_grades == (
        ("Primary.md", 3.0),
        ("Related.md", 1.0),
    )


def test_load_dataset_rejects_empty_cases(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text('{"cases": []}')

    with pytest.raises(ValueError, match="non-empty 'cases'"):
        load_dataset(dataset)


def test_evaluate_retrieval_deduplicates_chunks_and_computes_metrics(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    cases = (
        EvaluationCase("question one", ("Notes/Expected.md",)),
        EvaluationCase("question two", ("Missing.md",)),
    )

    def retrieve(question: str):
        if question == "question one":
            return [
                Document(page_content="a", metadata={"source": vault / "Other.md"}),
                Document(page_content="b", metadata={"source": vault / "Notes/Expected.md"}),
                Document(page_content="c", metadata={"source": vault / "Notes/Expected.md"}),
            ]
        return [Document(page_content="d", metadata={"source": vault / "Other.md"})]

    result = evaluate_retrieval(retrieve, cases, vault, k=2)

    assert result.cases[0].retrieved_sources == ("Other.md", "Notes/Expected.md")
    assert result.cases[0].precision == 0.5
    assert result.cases[0].recall == 1.0
    assert result.cases[0].hit == 1.0
    assert result.cases[0].reciprocal_rank == 0.5
    assert result.cases[0].average_precision == 0.5
    assert result.cases[0].ndcg == pytest.approx(0.6309297536)
    assert result.cases[1].recall == 0.0
    assert result.precision_at_k == 0.25
    assert result.recall_at_k == 0.5
    assert result.hit_rate_at_k == 0.5
    assert result.mean_reciprocal_rank == 0.25
    assert result.mean_average_precision_at_k == 0.25
    assert result.ndcg_at_k == pytest.approx(0.3154648768)
    for metric, (low, high) in result.confidence_intervals_95.items():
        value = getattr(result, metric)
        assert low <= value <= high
    assert result.mean_latency_seconds >= 0
    assert result.p50_latency_seconds >= 0
    assert result.p95_latency_seconds >= result.p50_latency_seconds


def test_evaluate_retrieval_uses_graded_relevance_for_ndcg(tmp_path):
    case = EvaluationCase(
        "question",
        ("Primary.md", "Related.md"),
        (("Primary.md", 3.0), ("Related.md", 1.0)),
    )
    documents = [
        Document(page_content="related", metadata={"source": "Related.md"}),
        Document(page_content="primary", metadata={"source": "Primary.md"}),
    ]

    result = evaluate_retrieval(lambda _: documents, (case,), tmp_path, k=2)

    assert result.precision_at_k == 1.0
    assert result.recall_at_k == 1.0
    assert result.mean_average_precision_at_k == 1.0
    assert result.ndcg_at_k == pytest.approx(0.7098097414)


def test_compare_evaluation_results_pairs_cases_by_question():
    def case(question, value):
        return {
            "question": question,
            "precision": value,
            "recall": value,
            "hit": value,
            "reciprocal_rank": value,
            "average_precision": value,
            "ndcg": value,
        }

    result = compare_evaluation_results(
        {"engine": "v3", "cases": [case("a", 0.2), case("b", 0.4)]},
        {"engine": "v4", "cases": [case("b", 0.5), case("a", 0.4)]},
        samples=100,
    )

    assert result["baseline_engine"] == "v3"
    assert result["candidate_engine"] == "v4"
    assert result["case_count"] == 2
    assert result["metrics"]["ndcg_at_k"]["delta"] == pytest.approx(0.15)
    assert result["metrics"]["ndcg_at_k"]["improved_queries"] == 2


def test_compare_evaluation_results_rejects_different_questions():
    case = {
        "precision": 1,
        "recall": 1,
        "hit": 1,
        "reciprocal_rank": 1,
        "average_precision": 1,
        "ndcg": 1,
    }
    with pytest.raises(ValueError, match="same questions"):
        compare_evaluation_results(
            {"cases": [{"question": "a", **case}]},
            {"cases": [{"question": "b", **case}]},
        )


def test_bootstrap_interval_is_deterministic_and_handles_one_value():
    assert _bootstrap_mean_ci([0.5], seed=0) == (0.5, 0.5)
    assert _bootstrap_mean_ci([0.0, 1.0], seed=7, samples=100) == _bootstrap_mean_ci(
        [0.0, 1.0], seed=7, samples=100
    )


def test_evaluate_retrieval_rejects_invalid_k(tmp_path):
    with pytest.raises(ValueError, match="at least 1"):
        evaluate_retrieval(lambda _: [], (EvaluationCase("q", ("a.md",)),), tmp_path, k=0)
