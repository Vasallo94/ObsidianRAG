"""Integration tests for the experimental v4 index vertical."""

import shutil
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings

pytest.importorskip("lancedb")

from obsidianrag.config import configure_from_vault
from obsidianrag.v4 import ExperimentalRetriever, build_index
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
    assert documents[0].metadata["source"] == "Reference/Error Codes.md"
    assert documents[0].metadata["retrieval_type"] in {
        "lexical",
        "lexical+vector",
        "vector",
    }


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
