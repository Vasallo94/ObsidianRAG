"""Tests for retrieval evaluation metrics and dataset validation."""

import json

import pytest
from langchain_core.documents import Document

from obsidianrag.evaluation import EvaluationCase, evaluate_retrieval, load_dataset


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
    assert result.cases[0].recall == 1.0
    assert result.cases[0].reciprocal_rank == 0.5
    assert result.cases[1].recall == 0.0
    assert result.recall_at_k == 0.5
    assert result.mean_reciprocal_rank == 0.25


def test_evaluate_retrieval_rejects_invalid_k(tmp_path):
    with pytest.raises(ValueError, match="at least 1"):
        evaluate_retrieval(lambda _: [], (EvaluationCase("q", ("a.md",)),), tmp_path, k=0)
