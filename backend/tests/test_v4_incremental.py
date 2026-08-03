"""Focused tests for v4 copy-on-write incremental revisions."""

import json
import multiprocessing
import os
import sqlite3
import stat
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.embeddings import Embeddings

pytest.importorskip("lancedb")

import obsidianrag.v4.index as index_module
from obsidianrag.config import configure_from_vault
from obsidianrag.v4 import (
    FullRebuildRequired,
    IndexBuildLocked,
    IndexCorruptionError,
    IndexPathError,
    LexicalRetriever,
    Retriever,
    RevisionInUse,
    active_revision,
    build_index,
    index_status,
    prune_revisions,
)
from obsidianrag.v4.index import SCHEMA_VERSION, _build_lock
from tests.test_v4_retrieval import KeywordEmbeddings, copy_sample_vault


class TrackingEmbeddings(KeywordEmbeddings):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.extend(texts)
        return super().embed_documents(texts)


class DifferentDimensionEmbeddings(KeywordEmbeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[*vector, 0.0] for vector in super().embed_documents(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [*super().embed_query(text), 0.0]


class ConfigurableSpaceEmbeddings(KeywordEmbeddings):
    def __init__(self, *, alternate: bool) -> None:
        self.alternate = alternate

    def _embed(self, text: str) -> list[float]:
        vector = super()._embed(text)
        if not self.alternate:
            return vector
        return [value + (index + 1) / 100 for index, value in enumerate(vector)]


def _hold_build_lock(root: str, ready, release) -> None:
    with _build_lock(Path(root)):
        ready.set()
        release.wait(10)


def test_reparse_file_attribute_is_treated_as_a_link(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    metadata = MagicMock(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
    monkeypatch.setattr(index_module.os, "lstat", MagicMock(return_value=metadata))

    assert index_module._is_link(tmp_path / "junction")


def test_pid_liveness_check_does_not_signal_the_current_process():
    assert index_module._pid_is_alive(os.getpid())
    assert not index_module._pid_is_alive(2_147_483_647)


def test_index_status_missing_does_not_create_managed_directories(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    status = index_status(vault, KeywordEmbeddings())

    assert status.state == "missing"
    assert status.active_revision is None
    assert status.indexed_notes == 0
    assert status.indexed_chunks == 0
    assert status.changed_notes == 6
    assert status.deleted_notes == 0
    assert not (vault / ".obsidianrag").exists()


def test_index_status_reports_current_and_add_modify_delete_stale(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    result = build_index(vault, embeddings)

    current = index_status(vault, embeddings)
    assert current.state == "current"
    assert current.active_revision == result.revision
    assert current.indexed_notes == result.notes
    assert current.indexed_chunks == result.chunks
    assert current.changed_notes == 0
    assert current.deleted_notes == 0

    (vault / "Projects" / "Art.md").write_text("# Art\n\nrollback checklist")
    (vault / "Added.md").write_text("# Added\n\ncredenciales")
    (vault / "Reference" / "Error Codes.md").unlink()

    stale = index_status(vault, embeddings)
    assert stale.state == "stale"
    assert stale.active_revision == result.revision
    assert stale.changed_notes == 2
    assert stale.deleted_notes == 1


def test_index_status_requires_rebuild_for_config_or_embedding_mismatch(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    settings = configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    build_index(vault, embeddings)
    original_size = settings.chunk_size
    settings.chunk_size += 1
    try:
        status = index_status(vault, embeddings)
        assert status.state == "rebuild_required"
        assert "chunk_size" in (status.reason or "")
    finally:
        settings.chunk_size = original_size

    status = index_status(vault, ConfigurableSpaceEmbeddings(alternate=True))
    assert status.state == "rebuild_required"
    assert "fingerprint" in (status.reason or "")


def test_index_status_classifies_malformed_or_missing_revision_as_rebuild_required(
    tmp_path: Path,
):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    build_index(vault, KeywordEmbeddings())
    active_path = vault / ".obsidianrag" / "v4" / "active.json"
    active_path.write_text("{truncated")

    malformed = index_status(vault, KeywordEmbeddings())
    assert malformed.state == "rebuild_required"
    assert "malformed" in (malformed.reason or "")

    active_path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "revision": "missing-revision"})
    )
    missing = index_status(vault, KeywordEmbeddings())
    assert missing.state == "rebuild_required"
    assert missing.active_revision == "missing-revision"
    assert "missing" in (missing.reason or "")


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
    assert embeddings.calls == list(index_module._FINGERPRINT_DOCUMENTS)


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


def test_same_class_and_dimension_different_vector_space_requires_rebuild(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    build_index(vault, ConfigurableSpaceEmbeddings(alternate=False))

    with pytest.raises(FullRebuildRequired, match="fingerprint"):
        build_index(vault, ConfigurableSpaceEmbeddings(alternate=True))


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
    reader = Retriever(vault, embeddings)
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

    def fail_candidate(revision_path: Path, expected_chunks: int | set[str]):
        if revision_path != first.path:
            raise RuntimeError("validation failed")
        validate_revision(revision_path, expected_chunks)

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
    reader = Retriever(vault, embeddings)
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


def test_managed_paths_and_markdown_notes_reject_links(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    root = vault / ".obsidianrag" / "v4"
    root.mkdir(parents=True)
    external = tmp_path / "external.txt"
    external.write_text("do not truncate")
    try:
        (root / "build.lock").symlink_to(external)
    except OSError:
        pytest.skip("symlinks are unavailable")

    with pytest.raises(IndexPathError, match="links"):
        build_index(vault, KeywordEmbeddings())
    assert external.read_text() == "do not truncate"

    (root / "build.lock").unlink()
    secret = tmp_path / "secret.md"
    secret.write_text("external secret")
    (vault / "linked.md").symlink_to(secret)
    with pytest.raises(IndexPathError, match="cannot contain links"):
        build_index(vault, KeywordEmbeddings())


def _windows_junction(link: Path, target: Path) -> None:
    if os.name != "nt":
        pytest.skip("Windows junction coverage runs only on Windows")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if os.environ.get("CI"):
            pytest.fail(f"Windows CI could not create a junction: {detail}")
        pytest.skip(f"Windows junction creation is unavailable: {detail}")


def test_windows_reparse_points_cannot_enter_index_or_cleanup(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    managed_target = tmp_path / "managed-target"
    managed_target.mkdir()
    managed_root = vault / ".obsidianrag"
    _windows_junction(managed_root, managed_target)
    with pytest.raises(IndexPathError, match="links"):
        build_index(vault, KeywordEmbeddings())
    managed_root.rmdir()

    note_target = tmp_path / "external-notes"
    note_target.mkdir()
    (note_target / "Secret.md").write_text("external secret")
    note_link = vault / "linked-notes"
    _windows_junction(note_link, note_target)
    with pytest.raises(IndexPathError, match="links"):
        build_index(vault, KeywordEmbeddings())
    note_link.rmdir()

    build_index(vault, KeywordEmbeddings())
    external_revision = tmp_path / "external-revision"
    external_revision.mkdir()
    marker = external_revision / "keep.txt"
    marker.write_text("keep")
    linked_revision = vault / ".obsidianrag" / "v4" / "indexes" / "linked-revision"
    _windows_junction(linked_revision, external_revision)
    with pytest.raises(IndexPathError, match="links"):
        prune_revisions(vault)
    assert marker.read_text() == "keep"


def test_managed_v4_directory_rejects_link(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    external = tmp_path / "external-index"
    external.mkdir()
    try:
        (vault / ".obsidianrag" / "v4").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory links are unavailable")
    with pytest.raises(IndexPathError, match="links"):
        build_index(vault, KeywordEmbeddings())


def test_prune_rejects_linked_cleanup_target(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    build_index(vault, KeywordEmbeddings())
    external = tmp_path / "external-revision"
    external.mkdir()
    marker = external / "keep.txt"
    marker.write_text("keep")
    linked = vault / ".obsidianrag" / "v4" / "indexes" / "linked-revision"
    try:
        linked.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory links are unavailable")

    with pytest.raises(IndexPathError, match="links"):
        prune_revisions(vault)
    assert marker.read_text() == "keep"


def test_deleting_last_note_activates_empty_revision(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    first = build_index(vault, embeddings)
    for note in vault.rglob("*.md"):
        note.unlink()

    empty = build_index(vault, embeddings)
    assert empty.revision != first.revision
    assert empty.notes == 0
    assert empty.chunks == 0
    assert empty.deleted_notes == first.notes

    lexical = LexicalRetriever(vault)
    hybrid = Retriever(vault, embeddings)
    try:
        assert lexical.invoke("rollback") == []
        assert hybrid.invoke("rollback") == []
    finally:
        lexical.close()
        hybrid.close()


def test_full_rebuild_recovers_malformed_active_manifest(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    build_index(vault, KeywordEmbeddings())
    active_path = vault / ".obsidianrag" / "v4" / "active.json"
    active_path.write_text("{truncated")

    with pytest.raises(IndexCorruptionError, match="malformed"):
        build_index(vault, KeywordEmbeddings())
    rebuilt = build_index(vault, KeywordEmbeddings(), full_rebuild=True)
    assert active_revision(vault) == rebuilt.path


def test_validation_rejects_fts_semantic_corruption(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    revision = build_index(vault, KeywordEmbeddings()).path
    with sqlite3.connect(revision / "catalog.sqlite3") as connection:
        connection.execute("UPDATE chunks_fts SET text = 'tampered' WHERE rowid = 1")
        connection.commit()

    with pytest.raises(IndexCorruptionError, match="FTS content"):
        build_index(vault, KeywordEmbeddings())


def test_validation_rejects_lance_semantic_corruption(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    revision = build_index(vault, embeddings).path
    table = index_module.require_lancedb().connect(revision / "vectors").open_table("chunks")
    table.update(values={"note_path": "tampered.md"})

    with pytest.raises(IndexCorruptionError, match="vector paths"):
        build_index(vault, embeddings)


def test_vault_change_before_activation_aborts_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    first = build_index(vault, embeddings)
    changed = vault / "Added.md"
    changed.write_text("# Added\n\nfirst content")
    validate_revision = index_module._validate_revision

    def mutate_after_validation(revision_path: Path, expected_chunks: int | set[str]) -> None:
        validate_revision(revision_path, expected_chunks)
        if revision_path != first.path:
            changed.write_text("# Added\n\nchanged during build")

    monkeypatch.setattr(index_module, "_validate_revision", mutate_after_validation)
    with pytest.raises(RuntimeError, match="changed during v4 indexing"):
        build_index(vault, embeddings)
    assert active_revision(vault) == first.path


def test_incremental_copy_and_validation_never_materialize_full_lance_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    first = build_index(vault, embeddings)
    table = index_module.require_lancedb().connect(first.path / "vectors").open_table("chunks")

    def reject_to_arrow(*args, **kwargs):
        raise AssertionError("full table materialization is forbidden")

    monkeypatch.setattr(type(table), "to_arrow", reject_to_arrow)
    (vault / "Added.md").write_text("# Added\n\nrollback")
    second = build_index(vault, embeddings)
    assert second.reused_chunks == first.chunks


def test_activation_exception_after_replace_keeps_activated_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    first = build_index(vault, embeddings)
    (vault / "Added.md").write_text("# Added\n\nrollback")
    activate = index_module._activate

    def replace_then_fail(
        root: Path, active: dict[str, object], expected_root: os.stat_result
    ) -> None:
        activate(root, active, expected_root)
        raise RuntimeError("interrupted after replace")

    monkeypatch.setattr(index_module, "_activate", replace_then_fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        build_index(vault, embeddings)
    current = active_revision(vault)
    assert current != first.path
    assert current.exists()


def test_prune_refuses_leased_revision_then_deletes_it_after_close(tmp_path: Path):
    vault = copy_sample_vault(tmp_path)
    configure_from_vault(str(vault))
    embeddings = KeywordEmbeddings()
    first = build_index(vault, embeddings)
    reader = Retriever(vault, embeddings)
    (vault / "Added.md").write_text("# Added\n\nrollback")
    second = build_index(vault, embeddings)

    try:
        with pytest.raises(RevisionInUse, match="active readers"):
            prune_revisions(vault)
        assert first.path.exists()
    finally:
        reader.close()

    pruned = prune_revisions(vault)
    assert pruned.active_revision == second.revision
    assert pruned.deleted_revisions == (first.revision,)
    assert not first.path.exists()
