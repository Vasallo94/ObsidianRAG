"""Integration tests for the experimental v4 index vertical."""

import asyncio
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.embeddings import Embeddings

pytest.importorskip("lancedb")

from obsidianrag.config import configure_from_vault
from obsidianrag.core.query_pipeline import QueryPipeline
from obsidianrag.v4 import ExperimentalLexicalRetriever, ExperimentalRetriever, build_index
from obsidianrag.v4.index import active_revision


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
    retriever = ExperimentalRetriever(vault, embeddings)
    try:
        documents = retriever.invoke("What does ORG-429 mean?", k=3)
    finally:
        retriever.close()

    assert result.notes == 6
    assert result.chunks >= result.notes
    lexical = ExperimentalLexicalRetriever(vault)
    try:
        lexical_documents = lexical.invoke("What does ORG-429 mean?", k=3)
    finally:
        lexical.close()

    assert documents[0].metadata["source"] == "Reference/Error Codes.md"
    assert documents[0].metadata["retrieval_type"] == "hybrid-source+lexical-chunk"
    assert len({document.metadata["source"] for document in documents}) == len(documents)
    assert lexical_documents[0].metadata["source"] == "Reference/Error Codes.md"
    assert lexical_documents[0].metadata["retrieval_type"] == "lexical"


def test_lexical_retriever_streams_from_pipeline_worker_thread(tmp_path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    build_index(vault, KeywordEmbeddings())
    pipeline = QueryPipeline(
        ExperimentalLexicalRetriever(vault),
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


def test_hybrid_retriever_closes_sqlite_when_initialization_fails(tmp_path):
    connection = MagicMock()
    connection.execute.return_value = [("embedding_signature", "old")]

    with (
        patch("obsidianrag.v4.retrieval.active_revision", return_value=tmp_path),
        patch("obsidianrag.v4.retrieval.sqlite3.connect", return_value=connection),
        patch("obsidianrag.v4.retrieval.embedding_signature", return_value="new"),
        pytest.raises(RuntimeError, match="different embedding configuration"),
    ):
        ExperimentalRetriever(tmp_path, KeywordEmbeddings())

    connection.close.assert_called_once_with()


def test_active_manifest_cannot_escape_revision_directory(tmp_path):
    vault = copy_sample_vault(tmp_path)
    root = vault / ".obsidianrag" / "v4"
    root.mkdir(parents=True)
    (root / "active.json").write_text('{"schema_version": 1, "revision": "../../outside"}')

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
