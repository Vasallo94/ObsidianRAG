"""Focused tests for v4 copy-on-write incremental revisions."""

import json
import multiprocessing
import sqlite3
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings

pytest.importorskip("lancedb")

import obsidianrag.v4.index as index_module
from obsidianrag.config import configure_from_vault
from obsidianrag.v4 import (
    ExperimentalRetriever,
    FullRebuildRequired,
    IndexBuildLocked,
    active_revision,
    build_index,
)
from obsidianrag.v4.index import SCHEMA_VERSION, _build_lock
from tests.test_v4_experimental import KeywordEmbeddings, copy_sample_vault


class TrackingEmbeddings(KeywordEmbeddings):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.extend(texts)
        return super().embed_documents(texts)


class DifferentDimensionEmbeddings(KeywordEmbeddings):
    def embed_query(self, text: str) -> list[float]:
        return [*super().embed_query(text), 0.0]


def _hold_build_lock(root: str, ready, release) -> None:
    with _build_lock(Path(root)):
        ready.set()
        release.wait(10)


def test_incremental_add_modify_delete_and_noop_only_embeds_changed_notes(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = TrackingEmbeddings()

    first = build_index(vault, embeddings)
    embeddings.calls.clear()
    (vault / "Projects" / "Art.md").write_text("# Art\n\nrollback checklist")
    (vault / "Added.md").write_text("# Added\n\ncredenciales")
    (vault / "Reference" / "Error Codes.md").unlink()

    second = build_index(vault, embeddings)
    assert second.revision != first.revision
    assert second.reused_chunks > 0
    assert second.reindexed_notes == 2
    assert second.deleted_notes == 1
    assert any("Added" in text for text in embeddings.calls)
    assert all("Error code" not in text for text in embeddings.calls)

    embeddings.calls.clear()
    no_op = build_index(vault, embeddings)
    assert no_op.revision == second.revision
    assert no_op.reused_chunks == second.chunks
    assert embeddings.calls == []


def test_incremental_config_mismatch_requires_explicit_full_rebuild(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    settings = configure_from_vault(str(vault))
    build_index(vault, KeywordEmbeddings())
    original_size = settings.chunk_size
    settings.chunk_size += 1
    try:
        with pytest.raises(FullRebuildRequired, match="full-rebuild"):
            build_index(vault, KeywordEmbeddings())
        rebuilt = build_index(vault, KeywordEmbeddings(), full_rebuild=True)
        assert rebuilt.revision == active_revision(vault).name
    finally:
        settings.chunk_size = original_size


def test_embedding_signature_and_dimension_mismatch_require_full_rebuild(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    settings = configure_from_vault(str(vault))
    build_index(vault, KeywordEmbeddings())
    original_model = settings.ollama_embedding_model

    try:
        settings.ollama_embedding_model = f"{original_model}-changed"
        with pytest.raises(FullRebuildRequired, match="full-rebuild"):
            build_index(vault, KeywordEmbeddings())
    finally:
        settings.ollama_embedding_model = original_model

    with pytest.raises(FullRebuildRequired, match="dimension"):
        build_index(vault, DifferentDimensionEmbeddings())


def test_schema_and_config_hash_mismatch_require_full_rebuild(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    first = build_index(vault, KeywordEmbeddings())
    active_path = vault / ".obsidianrag" / "v4" / "active.json"
    active = json.loads(active_path.read_text())
    active["schema_version"] = SCHEMA_VERSION - 1
    active_path.write_text(json.dumps(active))

    with pytest.raises(FullRebuildRequired, match="schema"):
        build_index(vault, KeywordEmbeddings())

    rebuilt = build_index(vault, KeywordEmbeddings(), full_rebuild=True)
    with sqlite3.connect(rebuilt.path / "catalog.sqlite3") as connection:
        connection.execute("DELETE FROM metadata WHERE key = 'config_hash'")
        connection.commit()
    with pytest.raises(FullRebuildRequired, match="configuration hash"):
        build_index(vault, KeywordEmbeddings())
    assert first.path.exists()


def test_failed_incremental_build_keeps_active_revision_and_old_reader(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    first = build_index(vault, embeddings)
    reader = ExperimentalRetriever(vault, embeddings)
    active_before = active_revision(vault)
    (vault / "Projects" / "Art.md").write_text("# Art\n\nchanged rollback")

    class FailingEmbeddings(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embedding failed")

        def embed_query(self, text: str) -> list[float]:
            return [0.0] * len(KeywordEmbeddings.terms)

    try:
        with pytest.raises(RuntimeError, match="embedding failed"):
            build_index(vault, FailingEmbeddings())
        assert active_revision(vault) == active_before
        assert reader.invoke("ORG-429", k=1)[0].metadata["source"] == "Reference/Error Codes.md"
        assert first.path.exists()
    finally:
        reader.close()


def test_failed_validation_keeps_active_revision_and_removes_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    first = build_index(vault, embeddings)
    root = vault / ".obsidianrag" / "v4"
    active_before = (root / "active.json").read_bytes()
    revisions_before = set((root / "indexes").iterdir())
    (vault / "Projects" / "Art.md").write_text("# Art\n\nchanged")
    validate_revision = index_module._validate_revision

    def fail_candidate(catalog_path: Path, vectors_path: Path, expected_chunks: int | set[str]):
        if catalog_path.parent != first.path:
            raise RuntimeError("validation failed")
        validate_revision(catalog_path, vectors_path, expected_chunks)

    monkeypatch.setattr(index_module, "_validate_revision", fail_candidate)
    with pytest.raises(RuntimeError, match="validation failed"):
        build_index(vault, embeddings)

    assert (root / "active.json").read_bytes() == active_before
    assert set((root / "indexes").iterdir()) == revisions_before


def test_old_reader_survives_successful_activation(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    first = build_index(vault, embeddings)
    reader = ExperimentalRetriever(vault, embeddings)
    (vault / "Reference" / "Error Codes.md").unlink()

    try:
        second = build_index(vault, embeddings)
        assert second.revision != first.revision
        assert reader.invoke("ORG-429", k=1)[0].metadata["source"] == "Reference/Error Codes.md"
    finally:
        reader.close()


def test_build_lock_rejects_second_builder_without_changing_active_manifest(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    build_index(vault, KeywordEmbeddings())
    root = vault / ".obsidianrag" / "v4"
    active_before = (root / "active.json").read_bytes()

    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(target=_hold_build_lock, args=(str(root), ready, release))
    process.start()
    try:
        assert ready.wait(10)
        with pytest.raises(IndexBuildLocked):
            build_index(vault, KeywordEmbeddings())
    finally:
        release.set()
        process.join(10)

    assert process.exitcode == 0
    assert (root / "active.json").read_bytes() == active_before
