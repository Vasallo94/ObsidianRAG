"""Integration tests for the experimental v4 index vertical."""

import asyncio
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.embeddings import Embeddings

pytest.importorskip("lancedb")

from obsidianrag.config import configure_from_vault
from obsidianrag.core.query_pipeline import QueryPipeline
from obsidianrag.v4 import (
    LexicalRetriever,
    Retriever,
    active_revision,
    build_index,
)


class KeywordEmbeddings(Embeddings):
    terms = ("rollback", "credenciales", "org-429", "copias", "cartography", "art")

    def _embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(term)) for term in self.terms]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def copy_sample_vault(tmp_path: Path) -> Path:
    source = Path(__file__).parents[1] / "evaluation" / "sample-vault"
    vault = tmp_path / "vault"
    shutil.copytree(source, vault)
    return vault


def test_build_and_search_experimental_index(tmp_path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()

    result = build_index(vault, embeddings)
    retriever = Retriever(vault, embeddings)
    try:
        documents = retriever.invoke("What does ORG-429 mean?", k=3)
    finally:
        retriever.close()

    assert result.notes == 6
    assert result.chunks >= result.notes
    lexical = LexicalRetriever(vault)
    try:
        lexical_documents = lexical.invoke("What does ORG-429 mean?", k=3)
    finally:
        lexical.close()

    assert documents[0].metadata["source"] == "Reference/Error Codes.md"
    assert documents[0].metadata["retrieval_type"] == "hybrid-source+lexical-chunk"
    assert documents[0].metadata["lexical_score"] > 0
    assert len({document.metadata["source"] for document in documents}) == len(documents)
    assert lexical_documents[0].metadata["source"] == "Reference/Error Codes.md"
    assert lexical_documents[0].metadata["retrieval_type"] == "lexical"


def test_hybrid_rrf_fuses_different_chunks_from_the_same_source():
    retriever = Retriever.__new__(Retriever)
    retriever.connection = sqlite3.connect(":memory:")
    retriever.connection.execute(
        "CREATE TABLE chunks (chunk_id TEXT, note_path TEXT, ordinal INTEGER, text TEXT)"
    )
    retriever.connection.executemany(
        "INSERT INTO chunks VALUES (?, ?, ?, ?)",
        [
            ("b1", "B.md", 0, "B"),
            ("a1", "A.md", 0, "A lexical"),
            ("a2", "A.md", 1, "A vector"),
            ("c1", "C.md", 0, "C"),
        ],
    )
    try:
        with (
            patch.object(retriever, "_lexical_search", return_value=["b1", "a1"]),
            patch.object(retriever, "_vector_search", return_value=["a2", "c1"]),
            patch.object(
                retriever,
                "_best_lexical_chunk",
                return_value=("a1", "A.md", 0, "A lexical", -10.0),
            ),
        ):
            documents = retriever.invoke("query", k=1)
    finally:
        retriever.close()

    assert documents[0].metadata == {
        "chunk_id": "a1",
        "source": "A.md",
        "ordinal": 0,
        "score": pytest.approx(1 / 61 + 1 / 62),
        "lexical_score": 10.0,
        "retrieval_type": "hybrid-source+lexical-chunk",
    }
    assert documents[0].page_content == "A lexical"


def test_best_lexical_chunk_ignores_title_only_matches():
    retriever = Retriever.__new__(Retriever)
    retriever.connection = sqlite3.connect(":memory:")
    retriever.connection.executescript(
        """
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            note_path TEXT,
            ordinal INTEGER,
            text TEXT
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED,
            note_path UNINDEXED,
            title,
            text
        );
        """
    )
    rows = [
        ("one", "Needle.md", 0, "No matching body text"),
        ("two", "Needle.md", 1, "The needle is in this passage"),
    ]
    retriever.connection.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?)", rows)
    retriever.connection.executemany(
        "INSERT INTO chunks_fts VALUES (?, ?, ?, ?)",
        [(chunk_id, source, "TitleOnly", text) for chunk_id, source, _, text in rows],
    )

    try:
        match = retriever._best_lexical_chunk("needle", "Needle.md")
        title_only = retriever._best_lexical_chunk("TitleOnly", "Needle.md")
    finally:
        retriever.close()

    assert match[:4] == ("two", "Needle.md", 1, "The needle is in this passage")
    assert title_only is None


def test_lexical_retriever_streams_from_pipeline_worker_thread(tmp_path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    build_index(vault, KeywordEmbeddings())
    pipeline = QueryPipeline(
        LexicalRetriever(vault),
        MagicMock(),
        vault_path=vault,
        k=1,
        retrieval_k=3,
    )

    async def fake_stream(*_args, **_kwargs):
        yield "ORG-429 means quota exhaustion [1]."

    async def collect_events():
        with patch("obsidianrag.core.query_pipeline.stream_chat_model_tokens", fake_stream):
            return [event async for event in pipeline.stream("What does ORG-429 mean?")]

    try:
        events = asyncio.run(collect_events())
    finally:
        pipeline.close()

    assert events[-1]["type"] == "answer"
    assert events[-1]["answer"] == "ORG-429 means quota exhaustion [1]."
    assert events[-1]["citations"] == ["Reference/Error Codes.md"]


def test_multipart_pipeline_keeps_sources_from_each_query_part(tmp_path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    build_index(vault, KeywordEmbeddings())
    model = MagicMock()
    model.invoke.return_value.content = "Rollback [1], rotate credentials [2]."
    pipeline = QueryPipeline(
        LexicalRetriever(vault),
        model,
        vault_path=vault,
        k=5,
        retrieval_k=25,
    )

    try:
        result = pipeline.ask(
            "How do I roll back a failed deployment?; "
            "además, ¿cómo se deben rotar las credenciales de producción?"
        )
    finally:
        pipeline.close()

    sources = {document.metadata["source"] for document in result.documents}
    assert "Operations/Deployment Runbook.md" in sources
    assert "Operations/Secret Rotation.md" in sources


def test_hybrid_retriever_closes_sqlite_when_initialization_fails(tmp_path):
    connection = MagicMock()
    connection.execute.return_value = [
        ("embedding_fingerprint", "old"),
        ("embedding_dimension", "6"),
    ]
    lease = MagicMock()

    with (
        patch("obsidianrag.v4.retrieval.active_revision", return_value=tmp_path),
        patch("obsidianrag.v4.retrieval.acquire_revision_lease", return_value=lease),
        patch("obsidianrag.v4.retrieval.sqlite3.connect", return_value=connection),
        patch("obsidianrag.v4.retrieval.embedding_fingerprint", return_value=("new", 6)),
        pytest.raises(RuntimeError, match="different embedding configuration"),
    ):
        Retriever(tmp_path, KeywordEmbeddings())

    connection.close.assert_called_once_with()
    lease.close.assert_called_once_with()


def test_active_manifest_cannot_escape_revision_directory(tmp_path):
    vault = copy_sample_vault(tmp_path)
    root = vault / ".obsidianrag" / "v4"
    root.mkdir(parents=True)
    (root / "active.json").write_text('{"schema_version": 3, "revision": "../../outside"}')

    with pytest.raises(RuntimeError, match="revision path"):
        active_revision(vault)


def test_new_revision_activates_without_deleting_previous(tmp_path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()

    first = build_index(vault, embeddings)
    (vault / "Projects" / "Art.md").write_text("# Art\n\nUpdated publishing checklist.")
    second = build_index(vault, embeddings)

    assert first.revision != second.revision
    assert first.path.exists()
    assert second.path.exists()
    assert second.path.parent.parent.joinpath("active.json").read_text().find(second.revision) >= 0
