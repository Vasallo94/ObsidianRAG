"""Reproducible retrieval evaluation for ObsidianRAG."""

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
    latency_seconds: float


@dataclass(frozen=True)
class EvaluationResult:
    cases: tuple[CaseResult, ...]
    precision_at_k: float
    recall_at_k: float
    hit_rate_at_k: float
    mean_reciprocal_rank: float
    mean_average_precision_at_k: float
    ndcg_at_k: float
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
        cases.append(
            EvaluationCase(
                question=question.strip(),
                expected_sources=expected_sources,
                relevance_grades=tuple(grades),
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
        sources = _unique_sources(retrieve(case.question), vault_path)[:k]
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
                latency_seconds=latency,
            )
        )

    latencies = sorted(result.latency_seconds for result in results)
    p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1)
    metric_values = {
        "precision_at_k": [result.precision for result in results],
        "recall_at_k": [result.recall for result in results],
        "hit_rate_at_k": [result.hit for result in results],
        "mean_reciprocal_rank": [result.reciprocal_rank for result in results],
        "mean_average_precision_at_k": [result.average_precision for result in results],
        "ndcg_at_k": [result.ndcg for result in results],
    }
    return EvaluationResult(
        cases=tuple(results),
        precision_at_k=sum(result.precision for result in results) / len(results),
        recall_at_k=sum(result.recall for result in results) / len(results),
        hit_rate_at_k=sum(result.hit for result in results) / len(results),
        mean_reciprocal_rank=sum(result.reciprocal_rank for result in results) / len(results),
        mean_average_precision_at_k=sum(result.average_precision for result in results)
        / len(results),
        ndcg_at_k=sum(result.ndcg for result in results) / len(results),
        mean_latency_seconds=sum(latencies) / len(latencies),
        p50_latency_seconds=statistics.median(latencies),
        p95_latency_seconds=latencies[p95_index],
        confidence_intervals_95={
            metric: _bootstrap_mean_ci(values, seed=index)
            for index, (metric, values) in enumerate(metric_values.items())
        },
        k=k,
    )


def _bootstrap_mean_ci(
    values: list[float], *, seed: int, samples: int = 2000
) -> tuple[float, float]:
    """Return a deterministic percentile bootstrap interval for a sample mean."""
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples))
    return means[math.floor(0.025 * (samples - 1))], means[math.ceil(0.975 * (samples - 1))]


def _unique_sources(documents: Iterable[Document], vault_path: Path) -> list[str]:
    sources = []
    seen = set()
    vault = vault_path.resolve()

    for document in documents:
        source = str(document.metadata.get("source", ""))
        if not source:
            continue
        path = Path(source)
        if path.is_absolute():
            try:
                source = path.resolve().relative_to(vault).as_posix()
            except ValueError:
                source = path.as_posix()
        else:
            source = _normalize_relative(source)
        if source not in seen:
            seen.add(source)
            sources.append(source)

    return sources


def _normalize_relative(source: str) -> str:
    return source.replace("\\", "/").removeprefix("./").lstrip("/")
