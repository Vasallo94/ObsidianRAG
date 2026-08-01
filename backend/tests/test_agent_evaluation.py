"""Tests for external-agent RAG answer evaluation."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from obsidianrag.agent_evaluation import evaluate_with_external_agent, run_agent_command


def test_run_agent_command_uses_json_stdin_stdout(tmp_path):
    script = tmp_path / "agent.py"
    script.write_text("import json,sys; data=json.load(sys.stdin); json.dump(data,sys.stdout)")

    result = run_agent_command(f'{sys.executable} "{script}"', {"task": "test"})

    assert result == {"task": "test"}


def test_external_agent_evaluation_scores_grounded_answer():
    retriever = MagicMock()
    retriever.invoke.return_value = [
        Document(
            page_content="The deployment uses an atomic revision.",
            metadata={"source": "Operations.md", "chunk_id": "chunk-1"},
        )
    ]
    cases = [
        {
            "id": "case-1",
            "question": "How is deployment activated?",
            "ground_truth_answer": "It activates an atomic revision.",
            "required_facts": ["Uses a revision", "Activation is atomic"],
            "expected_sources": ["Operations.md"],
            "supporting_evidence": [{"source": "Operations.md", "quote": "atomic revision"}],
        }
    ]

    def fake_agent(_command, payload, _timeout):
        if payload["task"] == "generate":
            return {
                "answers": [
                    {
                        "id": "case-1",
                        "answer": "It activates an atomic revision.",
                        "citations": ["Operations.md"],
                    }
                ]
            }
        return {
            "judgments": [
                {
                    "id": "case-1",
                    "fact_scores": [1, 1],
                    "correctness": 1.0,
                    "faithfulness": 1.0,
                    "answer_relevance": 1.0,
                    "reason": "Fully supported",
                }
            ]
        }

    with patch("obsidianrag.agent_evaluation.run_agent_command", side_effect=fake_agent):
        result = evaluate_with_external_agent(
            cases,
            retriever,
            generator_command="generator",
            judge_command="judge",
            k=1,
        )

    assert result["case_count"] == 1
    assert result["metrics"]["evidence_recall"]["mean"] == 1.0
    assert result["metrics"]["required_fact_coverage"]["mean"] == 1.0
    assert result["metrics"]["citation_precision"]["mean"] == 1.0
    assert result["metrics"]["faithfulness"]["mean"] == 1.0


def test_external_agent_rejects_wrong_fact_score_count():
    retriever = MagicMock()
    retriever.invoke.return_value = [
        Document(page_content="evidence", metadata={"source": "Note.md"})
    ]
    case = {
        "id": "case-1",
        "question": "Question?",
        "ground_truth_answer": "Answer",
        "required_facts": ["one", "two"],
        "expected_sources": ["Note.md"],
        "supporting_evidence": [{"source": "Note.md", "quote": "evidence"}],
    }
    responses = [
        {"answers": [{"id": "case-1", "answer": "Answer", "citations": ["Note.md"]}]},
        {
            "judgments": [
                {
                    "id": "case-1",
                    "fact_scores": [1],
                    "correctness": 1,
                    "faithfulness": 1,
                    "answer_relevance": 1,
                }
            ]
        },
    ]

    with patch("obsidianrag.agent_evaluation.run_agent_command", side_effect=responses):
        with pytest.raises(RuntimeError, match="wrong number"):
            evaluate_with_external_agent(
                [case], retriever, generator_command="generator", judge_command="judge"
            )
