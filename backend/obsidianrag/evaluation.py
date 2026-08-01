"""Reproducible retrieval evaluation for ObsidianRAG."""

import hashlib
import json
import math
import random
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from langchain_core.documents import Document


@dataclass(frozen=True)
class EvaluationCase:
    question: str
    expected_sources: tuple[str, ...]
    relevance_grades: tuple[tuple[str, float], ...] = ()
    supporting_evidence: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CaseResult:
    question: str
    expected_sources: tuple[str, ...]
    retrieved_sources: tuple[str, ...]
    precision: float
    recall: float
    hit: float
    reciprocal_rank: float
    average_precision: float
    ndcg: float
    evidence_recall: float | None
    latency_seconds: float
    annotation_fingerprint: str


@dataclass(frozen=True)
class EvaluationResult:
    cases: tuple[CaseResult, ...]
    precision_at_k: float
    recall_at_k: float
    hit_rate_at_k: float
    mean_reciprocal_rank: float
    mean_average_precision_at_k: float
    ndcg_at_k: float
    evidence_recall_at_k: float | None
    mean_latency_seconds: float
    p50_latency_seconds: float
    p95_latency_seconds: float
    confidence_intervals_95: dict[str, tuple[float, float]]
    k: int

    def to_dict(self) -> dict:
        return asdict(self)


def load_dataset(path: Path) -> tuple[EvaluationCase, ...]:
    """Load and validate a retrieval evaluation dataset."""
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Dataset must contain a non-empty 'cases' list")

    cases = []
    for index, raw in enumerate(raw_cases, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Case {index} must be an object")
        question = raw.get("question")
        sources = raw.get("expected_sources")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Case {index} must have a non-empty question")
        if (
            not isinstance(sources, list)
            or not sources
            or not all(isinstance(source, str) and source.strip() for source in sources)
        ):
            raise ValueError(f"Case {index} must have non-empty expected_sources")
        expected_sources = tuple(_normalize_relative(source) for source in sources)
        raw_grades = raw.get("relevance_grades", [])
        if not isinstance(raw_grades, list):
            raise ValueError(f"Case {index} relevance_grades must be a list")
        grades = []
        for grade in raw_grades:
            if (
                not isinstance(grade, dict)
                or not isinstance(grade.get("source"), str)
                or not isinstance(grade.get("grade"), (int, float))
                or grade["grade"] <= 0
            ):
                raise ValueError(f"Case {index} has an invalid relevance grade")
            source = _normalize_relative(grade["source"])
            if source not in expected_sources:
                raise ValueError(f"Case {index} grades a source not listed in expected_sources")
            grades.append((source, float(grade["grade"])))
        raw_evidence = raw.get("supporting_evidence", [])
        if not isinstance(raw_evidence, list):
            raise ValueError(f"Case {index} supporting_evidence must be a list")
        evidence = []
        for item in raw_evidence:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("source"), str)
                or not isinstance(item.get("quote"), str)
                or not item["quote"]
            ):
                raise ValueError(f"Case {index} has invalid supporting evidence")
            source = _normalize_relative(item["source"])
            if source not in expected_sources:
                raise ValueError(f"Case {index} evidence source is not expected")
            evidence.append((source, item["quote"]))
        cases.append(
            EvaluationCase(
                question=question.strip(),
                expected_sources=expected_sources,
                relevance_grades=tuple(grades),
                supporting_evidence=tuple(evidence),
            )
        )

    return tuple(cases)


def evaluate_retrieval(
    retrieve: Callable[[str], Iterable[Document]],
    cases: tuple[EvaluationCase, ...],
    vault_path: Path,
    k: int = 10,
) -> EvaluationResult:
    """Measure source recall and reciprocal rank for a retriever."""
    if k < 1:
        raise ValueError("k must be at least 1")

    results = []
    for case in cases:
        started = time.perf_counter()
        documents = _unique_documents_by_source(retrieve(case.question), vault_path)[:k]
        sources = [_document_source(document, vault_path) for document in documents]
        latency = time.perf_counter() - started
        grades = {source: 1.0 for source in case.expected_sources}
        grades.update(dict(case.relevance_grades))
        gains = [grades.get(source, 0.0) for source in sources]
        hits = sum(gain > 0 for gain in gains)
        first_rank = next((rank for rank, gain in enumerate(gains, 1) if gain > 0), None)
        relevant_seen = 0
        precision_sum = 0.0
        for rank, gain in enumerate(gains, 1):
            if gain > 0:
                relevant_seen += 1
                precision_sum += relevant_seen / rank
        ideal_gains = sorted(grades.values(), reverse=True)[:k]
        dcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, 1))
        ideal_dcg = sum(
            (2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(ideal_gains, 1)
        )
        evidence_hits = sum(
            any(
                _document_source(document, vault_path) == source and quote in document.page_content
                for document in documents
            )
            for source, quote in case.supporting_evidence
        )
        evidence_recall = (
            evidence_hits / len(case.supporting_evidence) if case.supporting_evidence else None
        )
        results.append(
            CaseResult(
                question=case.question,
                expected_sources=case.expected_sources,
                retrieved_sources=tuple(sources),
                precision=hits / k,
                recall=hits / len(grades),
                hit=float(hits > 0),
                reciprocal_rank=1.0 / first_rank if first_rank else 0.0,
                average_precision=precision_sum / min(len(grades), k),
                ndcg=dcg / ideal_dcg if ideal_dcg else 0.0,
                evidence_recall=evidence_recall,
                latency_seconds=latency,
                annotation_fingerprint=_annotation_fingerprint(case),
            )
        )

    latencies = sorted(result.latency_seconds for result in results)
    p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1)
    evidence_values = [
        result.evidence_recall for result in results if result.evidence_recall is not None
    ]
    metric_values = {
        "precision_at_k": [result.precision for result in results],
        "recall_at_k": [result.recall for result in results],
        "hit_rate_at_k": [result.hit for result in results],
        "mean_reciprocal_rank": [result.reciprocal_rank for result in results],
        "mean_average_precision_at_k": [result.average_precision for result in results],
        "ndcg_at_k": [result.ndcg for result in results],
    }
    if evidence_values:
        metric_values["evidence_recall_at_k"] = evidence_values
    return EvaluationResult(
        cases=tuple(results),
        precision_at_k=sum(result.precision for result in results) / len(results),
        recall_at_k=sum(result.recall for result in results) / len(results),
        hit_rate_at_k=sum(result.hit for result in results) / len(results),
        mean_reciprocal_rank=sum(result.reciprocal_rank for result in results) / len(results),
        mean_average_precision_at_k=sum(result.average_precision for result in results)
        / len(results),
        ndcg_at_k=sum(result.ndcg for result in results) / len(results),
        evidence_recall_at_k=(statistics.fmean(evidence_values) if evidence_values else None),
        mean_latency_seconds=sum(latencies) / len(latencies),
        p50_latency_seconds=statistics.median(latencies),
        p95_latency_seconds=latencies[p95_index],
        confidence_intervals_95={
            metric: _bootstrap_mean_ci(values, seed=index)
            for index, (metric, values) in enumerate(metric_values.items())
        },
        k=k,
    )


def compare_evaluation_results(baseline: dict, candidate: dict, *, samples: int = 10000) -> dict:
    """Compare two evaluation result payloads with paired bootstrap intervals."""
    fields = {
        "precision_at_k": "precision",
        "recall_at_k": "recall",
        "hit_rate_at_k": "hit",
        "mean_reciprocal_rank": "reciprocal_rank",
        "mean_average_precision_at_k": "average_precision",
        "ndcg_at_k": "ndcg",
    }
    baseline_cases = _cases_by_question(baseline)
    candidate_cases = _cases_by_question(candidate)
    if baseline_cases.keys() != candidate_cases.keys():
        raise ValueError("Evaluation results must contain the same questions")
    baseline_k = baseline.get("k")
    candidate_k = candidate.get("k")
    if (
        type(baseline_k) is not int
        or type(candidate_k) is not int
        or baseline_k < 1
        or baseline_k != candidate_k
    ):
        raise ValueError("Evaluation results must use the same k")
    for question, baseline_case in baseline_cases.items():
        candidate_case = candidate_cases[question]
        baseline_fingerprint = baseline_case.get("annotation_fingerprint")
        candidate_fingerprint = candidate_case.get("annotation_fingerprint")
        if (baseline_fingerprint is None) != (candidate_fingerprint is None) or (
            baseline_fingerprint is not None and baseline_fingerprint != candidate_fingerprint
        ):
            raise ValueError("Evaluation results must use the same ground-truth annotations")
        baseline_sources = baseline_case.get("expected_sources")
        candidate_sources = candidate_case.get("expected_sources")
        if (
            not isinstance(baseline_sources, list)
            or not all(isinstance(source, str) for source in baseline_sources)
            or not isinstance(candidate_sources, list)
            or not all(isinstance(source, str) for source in candidate_sources)
            or sorted(map(_normalize_relative, baseline_sources))
            != sorted(map(_normalize_relative, candidate_sources))
        ):
            raise ValueError("Evaluation results must use the same expected sources")
    if all(
        case.get("evidence_recall") is not None
        and candidate_cases[question].get("evidence_recall") is not None
        for question, case in baseline_cases.items()
    ):
        fields["evidence_recall_at_k"] = "evidence_recall"

    metrics = {}
    for seed, (name, field) in enumerate(fields.items()):
        baseline_values = [float(case[field]) for case in baseline_cases.values()]
        candidate_values = [float(candidate_cases[question][field]) for question in baseline_cases]
        deltas = [candidate - base for base, candidate in zip(baseline_values, candidate_values)]
        metrics[name] = {
            "baseline": statistics.fmean(baseline_values),
            "candidate": statistics.fmean(candidate_values),
            "delta": statistics.fmean(deltas),
            "confidence_interval_95": _bootstrap_mean_ci(deltas, seed=seed, samples=samples),
            "improved_queries": sum(delta > 0 for delta in deltas),
            "regressed_queries": sum(delta < 0 for delta in deltas),
            "tied_queries": sum(delta == 0 for delta in deltas),
        }
    return {
        "baseline_engine": baseline.get("engine", "baseline"),
        "candidate_engine": candidate.get("engine", "candidate"),
        "case_count": len(baseline_cases),
        "metrics": metrics,
    }


def _annotation_fingerprint(case: EvaluationCase) -> str:
    payload = {
        "expected_sources": sorted(case.expected_sources),
        "relevance_grades": sorted(case.relevance_grades),
        "supporting_evidence": sorted(case.supporting_evidence),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _cases_by_question(payload: dict) -> dict[str, dict]:
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Evaluation result must contain a non-empty cases list")
    cases = {}
    for case in raw_cases:
        question = case.get("question") if isinstance(case, dict) else None
        if not isinstance(question, str) or not question or question in cases:
            raise ValueError("Evaluation result questions must be non-empty and unique")
        cases[question] = case
    return cases


def _bootstrap_mean_ci(
    values: list[float], *, seed: int, samples: int = 2000
) -> tuple[float, float]:
    """Return a deterministic percentile bootstrap interval for a sample mean."""
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples))
    return means[math.floor(0.025 * (samples - 1))], means[math.ceil(0.975 * (samples - 1))]


def _unique_documents_by_source(documents: Iterable[Document], vault_path: Path) -> list[Document]:
    unique = []
    seen = set()
    for document in documents:
        source = _document_source(document, vault_path)
        if source and source not in seen:
            seen.add(source)
            unique.append(document)
    return unique


def _document_source(document: Document, vault_path: Path) -> str:
    source = str(document.metadata.get("source", ""))
    if not source:
        return ""
    path = Path(source)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(vault_path.resolve()).as_posix()
        except ValueError:
            return path.as_posix()
    return _normalize_relative(source)


def _normalize_relative(source: str) -> str:
    return source.replace("\\", "/").removeprefix("./").lstrip("/")
