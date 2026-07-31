"""Reproducible retrieval evaluation for ObsidianRAG."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from langchain_core.documents import Document


@dataclass(frozen=True)
class EvaluationCase:
    question: str
    expected_sources: tuple[str, ...]


@dataclass(frozen=True)
class CaseResult:
    question: str
    expected_sources: tuple[str, ...]
    retrieved_sources: tuple[str, ...]
    recall: float
    reciprocal_rank: float


@dataclass(frozen=True)
class EvaluationResult:
    cases: tuple[CaseResult, ...]
    recall_at_k: float
    mean_reciprocal_rank: float
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
        cases.append(
            EvaluationCase(
                question=question.strip(),
                expected_sources=tuple(_normalize_relative(source) for source in sources),
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
        sources = _unique_sources(retrieve(case.question), vault_path)[:k]
        expected = set(case.expected_sources)
        hits = expected.intersection(sources)
        first_rank = next(
            (rank for rank, source in enumerate(sources, 1) if source in expected),
            None,
        )
        results.append(
            CaseResult(
                question=case.question,
                expected_sources=case.expected_sources,
                retrieved_sources=tuple(sources),
                recall=len(hits) / len(expected),
                reciprocal_rank=1.0 / first_rank if first_rank else 0.0,
            )
        )

    return EvaluationResult(
        cases=tuple(results),
        recall_at_k=sum(result.recall for result in results) / len(results),
        mean_reciprocal_rank=sum(result.reciprocal_rank for result in results) / len(results),
        k=k,
    )


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
