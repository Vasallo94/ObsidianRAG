"""External-agent answer generation and judging for private RAG evaluations."""

import json
import shlex
import subprocess
from typing import Any

from langchain_core.documents import Document

from obsidianrag.evaluation import _bootstrap_mean_ci, _normalize_relative


def run_agent_command(command: str, payload: dict, timeout: int = 300) -> dict:
    """Run a JSON stdin/stdout agent command without invoking a shell."""
    arguments = shlex.split(command)
    if not arguments:
        raise ValueError("Agent command cannot be empty")
    try:
        result = subprocess.run(
            arguments,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Agent command failed: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip()[-500:] or f"exit code {result.returncode}"
        raise RuntimeError(f"Agent command failed: {detail}")
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Agent command did not return valid JSON") from error
    if not isinstance(response, dict):
        raise RuntimeError("Agent command must return a JSON object")
    return response


def evaluate_with_external_agent(
    raw_cases: list[dict],
    retriever: Any,
    *,
    generator_command: str,
    judge_command: str,
    k: int = 5,
    batch_size: int = 6,
    timeout: int = 300,
) -> dict:
    """Retrieve contexts, generate grounded answers, and judge them externally."""
    if k < 1 or batch_size < 1:
        raise ValueError("k and batch_size must be at least 1")
    cases = [_validate_case(case) for case in raw_cases]
    generation_cases = []
    contexts_by_id = {}
    for case in cases:
        documents = _unique_source_documents(retriever.invoke(case["question"], k=k * 5))[:k]
        contexts = [
            {
                "source": _normalize_relative(str(document.metadata.get("source", ""))),
                "chunk_id": str(document.metadata.get("chunk_id", "")),
                "text": document.page_content,
            }
            for document in documents
        ]
        contexts_by_id[case["id"]] = contexts
        generation_cases.append(
            {"id": case["id"], "question": case["question"], "contexts": contexts}
        )

    answers = []
    for batch in _batches(generation_cases, batch_size):
        response = run_agent_command(
            generator_command,
            {"protocol_version": 1, "task": "generate", "cases": batch},
            timeout,
        )
        answers.extend(_validated_items(response, "answers", batch, _validate_answer))
    answers_by_id = {answer["id"]: answer for answer in answers}

    judgments = []
    judge_cases = []
    for case in cases:
        answer = answers_by_id[case["id"]]
        judge_cases.append(
            {
                "id": case["id"],
                "question": case["question"],
                "ground_truth_answer": case["ground_truth_answer"],
                "required_facts": case["required_facts"],
                "supporting_evidence": case["supporting_evidence"],
                "candidate_answer": answer["answer"],
                "candidate_citations": answer["citations"],
            }
        )
    for batch in _batches(judge_cases, batch_size):
        response = run_agent_command(
            judge_command,
            {"protocol_version": 1, "task": "judge", "cases": batch},
            timeout,
        )
        judgments.extend(_validated_items(response, "judgments", batch, _validate_judgment))
    judgments_by_id = {judgment["id"]: judgment for judgment in judgments}

    results = []
    for case in cases:
        answer = answers_by_id[case["id"]]
        judgment = judgments_by_id[case["id"]]
        if len(judgment["fact_scores"]) != len(case["required_facts"]):
            raise RuntimeError("Judge returned the wrong number of fact scores")
        contexts = contexts_by_id[case["id"]]
        expected = set(case["expected_sources"])
        retrieved = {context["source"] for context in contexts}
        cited = set(answer["citations"])
        evidence_hits = sum(
            any(
                context["source"] == evidence["source"] and evidence["quote"] in context["text"]
                for context in contexts
            )
            for evidence in case["supporting_evidence"]
        )
        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "answer": answer["answer"],
                "citations": answer["citations"],
                "retrieved_sources": [context["source"] for context in contexts],
                "judgment": judgment,
                "source_recall": len(retrieved & expected) / len(expected),
                "evidence_recall": evidence_hits / len(case["supporting_evidence"]),
                "required_fact_coverage": sum(judgment["fact_scores"])
                / len(case["required_facts"]),
                "citation_precision": len(cited & expected) / len(cited) if cited else 0.0,
                "citation_recall": len(cited & expected) / len(expected),
            }
        )

    metric_fields = {
        "source_recall": lambda item: item["source_recall"],
        "evidence_recall": lambda item: item["evidence_recall"],
        "required_fact_coverage": lambda item: item["required_fact_coverage"],
        "citation_precision": lambda item: item["citation_precision"],
        "citation_recall": lambda item: item["citation_recall"],
        "correctness": lambda item: item["judgment"]["correctness"],
        "faithfulness": lambda item: item["judgment"]["faithfulness"],
        "answer_relevance": lambda item: item["judgment"]["answer_relevance"],
    }
    metrics = {}
    for seed, (name, getter) in enumerate(metric_fields.items()):
        values = [float(getter(item)) for item in results]
        metrics[name] = {
            "mean": sum(values) / len(values),
            "confidence_interval_95": _bootstrap_mean_ci(values, seed=seed),
        }
    return {"protocol_version": 1, "case_count": len(results), "metrics": metrics, "cases": results}


def _validate_case(case: dict) -> dict:
    required = (
        "id",
        "question",
        "ground_truth_answer",
        "required_facts",
        "expected_sources",
        "supporting_evidence",
    )
    if not isinstance(case, dict) or any(not case.get(field) for field in required):
        raise ValueError("Every agent evaluation case needs complete private ground truth")
    normalized = dict(case)
    normalized["expected_sources"] = [
        _normalize_relative(source) for source in case["expected_sources"]
    ]
    normalized["supporting_evidence"] = [
        {"source": _normalize_relative(item["source"]), "quote": item["quote"]}
        for item in case["supporting_evidence"]
    ]
    return normalized


def _validate_answer(item: dict) -> dict:
    if (
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("answer"), str)
        or not isinstance(item.get("citations"), list)
        or not all(isinstance(citation, str) for citation in item["citations"])
    ):
        raise RuntimeError("Generator returned an invalid answer")
    return item


def _validate_judgment(item: dict) -> dict:
    scores = ("correctness", "faithfulness", "answer_relevance")
    if (
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("fact_scores"), list)
        or not all(score in (0, 1) for score in item["fact_scores"])
        or any(not isinstance(item.get(score), (int, float)) for score in scores)
        or any(not 0 <= item[score] <= 1 for score in scores)
    ):
        raise RuntimeError("Judge returned an invalid judgment")
    return item


def _validated_items(response: dict, key: str, batch: list[dict], validator) -> list[dict]:
    items = response.get(key)
    if not isinstance(items, list) or len(items) != len(batch):
        raise RuntimeError(f"Agent response must contain one {key} item per case")
    validated = [validator(item) for item in items]
    if {item["id"] for item in validated} != {item["id"] for item in batch}:
        raise RuntimeError("Agent response IDs do not match the request")
    return validated


def _unique_source_documents(documents: list[Document]) -> list[Document]:
    unique = []
    seen = set()
    for document in documents:
        source = _normalize_relative(str(document.metadata.get("source", "")))
        if source and source not in seen:
            seen.add(source)
            unique.append(document)
    return unique


def _batches(items: list[dict], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]
