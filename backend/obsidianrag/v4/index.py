"""Revisioned SQLite FTS5 + LanceDB indexing for the experimental v4 engine."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from obsidianrag.config import get_settings
from obsidianrag.core.db_service import get_text_splitter
from obsidianrag.core.metadata_tracker import EXCLUDED_DIRECTORIES

SCHEMA_VERSION = 2
EMBED_BATCH_SIZE = 64


class V4DependencyError(RuntimeError):
    """Raised when the experimental optional dependencies are unavailable."""


class FullRebuildRequired(RuntimeError):
    """Raised when an active revision cannot be updated incrementally."""


class IndexBuildLocked(RuntimeError):
    """Raised when another v4 revision is currently being built."""


# A descriptive alias is useful to callers that distinguish update failures.
IncrementalIndexError = FullRebuildRequired


@dataclass(frozen=True)
class IndexBuildResult:
    revision: str
    notes: int
    chunks: int
    path: Path
    reused_chunks: int = 0
    reindexed_notes: int = 0
    deleted_notes: int = 0


@dataclass(frozen=True)
class _NoteSnapshot:
    path: str
    content: str
    content_hash: str


def require_lancedb():
    try:
        import lancedb
    except ImportError as error:
        raise V4DependencyError(
            "Experimental v4 support requires: pip install 'obsidianrag[v4]'"
        ) from error
    return lancedb


def _v4_root(vault: Path) -> Path:
    return vault.resolve() / ".obsidianrag" / "v4"


@contextmanager
def _build_lock(root: Path) -> Iterator[None]:
    """Take an OS-released cross-platform lock for the complete build."""
    root.mkdir(parents=True, exist_ok=True)
    lock_file = (root / "build.lock").open("a+b")
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()
    lock_file.seek(0)

    try:
        if os.name == "nt":
            msvcrt = importlib.import_module("msvcrt")
            getattr(msvcrt, "locking")(lock_file.fileno(), getattr(msvcrt, "LK_NBLCK"), 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        lock_file.close()
        raise IndexBuildLocked("Another experimental v4 index build is already running") from error

    try:
        lock_file.seek(1)
        lock_file.truncate()
        lock_file.write(f"pid={os.getpid()}\n".encode())
        lock_file.flush()
        yield
    finally:
        lock_file.seek(0)
        if os.name == "nt":
            msvcrt = importlib.import_module("msvcrt")
            getattr(msvcrt, "locking")(lock_file.fileno(), getattr(msvcrt, "LK_UNLCK"), 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def build_index(
    vault_path: Path,
    embeddings: Embeddings,
    *,
    full_rebuild: bool = False,
    force_rebuild: bool = False,
) -> IndexBuildResult:
    """Build a v4 revision and atomically activate it.

    The default path compares the authoritative vault scan with the active
    revision and only splits/embeds new or changed notes.  ``full_rebuild`` is
    an explicit escape hatch for incompatible index configuration.
    """
    lancedb = require_lancedb()
    vault = vault_path.resolve()
    root = _v4_root(vault)
    revisions = root / "indexes"
    rebuild = full_rebuild or force_rebuild

    with _build_lock(root):
        snapshots = _scan_vault(vault)
        active_path = root / "active.json"
        active_manifest = _read_manifest(active_path)

        old_revision: Path | None = None
        old_metadata: dict[str, str] = {}
        old_chunks: list[dict[str, str | int]] = []
        old_vectors: dict[str, list[float]] = {}
        old_manifest: dict[str, str] = {}
        if active_manifest is not None and not rebuild:
            if active_manifest.get("schema_version") != SCHEMA_VERSION:
                raise FullRebuildRequired(
                    "Active v4 index schema is incompatible; run --full-rebuild"
                )
            old_revision = active_revision(vault)
            old_metadata, old_chunks, old_vectors, old_manifest = _read_revision(
                lancedb, old_revision
            )
            _assert_incremental_compatible(old_metadata, embeddings)
            _validate_revision(
                old_revision / "catalog.sqlite3",
                old_revision / "vectors",
                len(old_chunks),
            )
            _assert_manifest_matches_catalog(old_manifest, old_metadata)

            changed_paths = {
                path
                for path, snapshot in snapshots.items()
                if old_manifest.get(path) != snapshot.content_hash
            }
            deleted_paths = set(old_manifest) - set(snapshots)
            if not changed_paths and not deleted_paths:
                return IndexBuildResult(
                    revision=_manifest_revision(active_manifest),
                    notes=len(snapshots),
                    chunks=len(old_chunks),
                    path=old_revision,
                    reused_chunks=len(old_chunks),
                )
        else:
            changed_paths = set(snapshots)
            deleted_paths = set()

        revision = _new_revision_name()
        revision_path = revisions / revision
        revision_path.mkdir(parents=True, exist_ok=False)
        activated = False
        try:
            if old_revision is None:
                records = _records_for_snapshots(vault, snapshots)
                reused_vectors: dict[str, list[float]] = {}
                expected_dimension = None
                reused_chunks = 0
            else:
                changed_snapshots = {
                    path: snapshots[path] for path in sorted(changed_paths) if path in snapshots
                }
                changed_records = _records_for_snapshots(vault, changed_snapshots)
                unchanged_records = [
                    record
                    for record in old_chunks
                    if str(record["note_path"]) in snapshots
                    and str(record["note_path"]) not in changed_paths
                ]
                records = sorted(
                    [*unchanged_records, *changed_records],
                    key=lambda record: (str(record["note_path"]), int(record["ordinal"])),
                )
                reused_vectors = {}
                for record in unchanged_records:
                    chunk_id = str(record["chunk_id"])
                    vector = old_vectors.get(chunk_id)
                    if vector is None:
                        raise FullRebuildRequired(
                            "The active v4 revision is missing a reusable vector; "
                            "run a full rebuild"
                        )
                    reused_vectors[chunk_id] = vector
                expected_dimension = int(old_metadata["embedding_dimension"])
                reused_chunks = len(reused_vectors)

            if not records:
                raise RuntimeError("No Markdown content was available to index")

            catalog_path = revision_path / "catalog.sqlite3"
            connection = sqlite3.connect(catalog_path)
            try:
                _create_catalog(connection)
                _write_catalog(connection, records)
                dimension = _write_vectors(
                    lancedb,
                    revision_path / "vectors",
                    records,
                    embeddings,
                    reused_vectors=reused_vectors,
                    expected_dimension=expected_dimension,
                )
                _write_metadata(
                    connection,
                    dimension,
                    len(snapshots),
                    len(records),
                    snapshots,
                )
                connection.commit()
            finally:
                connection.close()

            _validate_revision(catalog_path, revision_path / "vectors", len(records))
            active = {
                "schema_version": SCHEMA_VERSION,
                "revision": revision,
                "activated_at": datetime.now(timezone.utc).isoformat(),
            }
            _activate(root, active)
            activated = True
            return IndexBuildResult(
                revision=revision,
                notes=len(snapshots),
                chunks=len(records),
                path=revision_path,
                reused_chunks=reused_chunks,
                reindexed_notes=len(changed_paths),
                deleted_notes=len(deleted_paths),
            )
        finally:
            if not activated:
                shutil.rmtree(revision_path, ignore_errors=True)


def build_incremental_index(vault_path: Path, embeddings: Embeddings) -> IndexBuildResult:
    """Build an incremental v4 revision."""
    return build_index(vault_path, embeddings)


def build_full_index(vault_path: Path, embeddings: Embeddings) -> IndexBuildResult:
    """Build a v4 revision without using the active revision as a base."""
    return build_index(vault_path, embeddings, full_rebuild=True)


def active_revision(vault_path: Path) -> Path:
    """Return the currently active experimental index revision."""
    root = _v4_root(vault_path)
    active_path = root / "active.json"
    if not active_path.exists():
        raise RuntimeError("No experimental v4 index found. Run: obsidianrag v4-index --vault ...")
    active = json.loads(active_path.read_text(encoding="utf-8"))
    revision = active.get("revision") if isinstance(active, dict) else None
    schema_version = active.get("schema_version") if isinstance(active, dict) else None
    if schema_version != SCHEMA_VERSION or not isinstance(revision, str):
        raise RuntimeError("Unsupported or invalid experimental v4 index manifest")
    indexes_path = (root / "indexes").resolve()
    revision_path = (indexes_path / revision).resolve()
    if not revision_path.is_relative_to(indexes_path):
        raise RuntimeError("Invalid experimental v4 index revision path")
    if not revision_path.is_dir():
        raise RuntimeError("The active experimental v4 index revision is missing")
    return revision_path


def embedding_signature() -> str:
    """Return the configured embedding identity persisted in each revision."""
    settings = get_settings()
    if settings.embedding_provider == "ollama":
        model = settings.ollama_embedding_model
    else:
        model = settings.embedding_model
    return f"{settings.embedding_provider}:{model}"


def _new_revision_name() -> str:
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"


def _read_manifest(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Unsupported or invalid experimental v4 index manifest")
    return value


def _manifest_revision(manifest: dict[str, object]) -> str:
    revision = manifest.get("revision")
    if not isinstance(revision, str):
        raise RuntimeError("Unsupported or invalid experimental v4 index manifest")
    return revision


def _read_revision(
    lancedb,
    revision_path: Path,
) -> tuple[
    dict[str, str],
    list[dict[str, str | int]],
    dict[str, list[float]],
    dict[str, str],
]:
    catalog_path = revision_path / "catalog.sqlite3"
    connection = sqlite3.connect(f"{catalog_path.as_uri()}?mode=ro", uri=True)
    try:
        metadata = {
            str(key): str(value)
            for key, value in connection.execute("SELECT key, value FROM metadata")
        }
        try:
            note_rows = connection.execute("SELECT note_path, content_hash FROM notes").fetchall()
        except sqlite3.OperationalError as error:
            raise FullRebuildRequired(
                "The active v4 revision predates incremental metadata; run a full rebuild"
            ) from error
        rows = connection.execute(
            "SELECT chunk_id, note_path, ordinal, text FROM chunks"
        ).fetchall()
    finally:
        connection.close()

    try:
        old_manifest_value = json.loads(metadata["note_manifest"])
        if not isinstance(old_manifest_value, dict):
            raise ValueError
        old_manifest = {
            str(path): str(content_hash) for path, content_hash in old_manifest_value.items()
        }
        catalog_manifest = {str(path): str(content_hash) for path, content_hash in note_rows}
        if catalog_manifest != old_manifest:
            raise ValueError("catalog note hashes do not match the manifest")
        old_chunks: list[dict[str, str | int]] = [
            {
                "chunk_id": str(row[0]),
                "note_path": str(row[1]),
                "ordinal": int(row[2]),
                "text": str(row[3]),
                "content_hash": old_manifest[str(row[1])],
            }
            for row in rows
        ]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise FullRebuildRequired(
            "The active v4 revision lacks incremental metadata; run a full rebuild"
        ) from error

    try:
        table = lancedb.connect(revision_path / "vectors").open_table("chunks")
        vector_rows = table.to_arrow().to_pylist()
        old_vectors = {
            str(row["chunk_id"]): [float(value) for value in row["vector"]] for row in vector_rows
        }
    except Exception as error:
        raise FullRebuildRequired(
            "The active v4 revision vectors cannot be read; run a full rebuild"
        ) from error
    return metadata, old_chunks, old_vectors, old_manifest


def _assert_manifest_matches_catalog(manifest: dict[str, str], metadata: dict[str, str]) -> None:
    try:
        note_count = int(metadata["notes"])
    except (KeyError, ValueError) as error:
        raise FullRebuildRequired(
            "The active v4 revision has incomplete metadata; run a full rebuild"
        ) from error
    if len(manifest) != note_count:
        raise FullRebuildRequired(
            "The active v4 revision note manifest is inconsistent; run a full rebuild"
        )


def _configuration_hash(dimension: int) -> str:
    settings = get_settings()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "embedding_signature": embedding_signature(),
        "embedding_dimension": dimension,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _embedding_dimension_hint(embeddings: Embeddings) -> int | None:
    for name in ("dimension", "embedding_dimension", "dim"):
        value = getattr(embeddings, name, None)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _assert_incremental_compatible(metadata: dict[str, str], embeddings: Embeddings) -> None:
    settings = get_settings()
    expected = {
        "schema_version": str(SCHEMA_VERSION),
        "embedding_signature": embedding_signature(),
        "chunk_size": str(settings.chunk_size),
        "chunk_overlap": str(settings.chunk_overlap),
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise FullRebuildRequired(f"Active v4 index {key} is incompatible; run --full-rebuild")
    try:
        dimension = int(metadata["embedding_dimension"])
        if dimension <= 0:
            raise ValueError
    except (KeyError, ValueError) as error:
        raise FullRebuildRequired(
            "Active v4 index has no valid embedding dimension; run --full-rebuild"
        ) from error
    if metadata.get("config_hash") != _configuration_hash(dimension):
        raise FullRebuildRequired(
            "Active v4 index configuration hash is incompatible; run --full-rebuild"
        )
    hint = _embedding_dimension_hint(embeddings)
    if hint is None:
        probe = embeddings.embed_query("obsidianrag embedding dimension probe")
        if not probe:
            raise RuntimeError("Embedding provider returned an empty dimension probe")
        hint = len(probe)
    if hint != dimension:
        raise FullRebuildRequired(
            "Active v4 index embedding dimension is incompatible; run --full-rebuild"
        )


def _read_note(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _scan_vault(vault: Path) -> dict[str, _NoteSnapshot]:
    """Scan Markdown directly; this is the source of truth for v4 updates."""
    excluded_patterns = (".excalidraw.md", ".canvas", "untitled")
    snapshots: dict[str, _NoteSnapshot] = {}
    for root, directories, files in os.walk(vault, followlinks=False):
        directories[:] = [
            directory for directory in directories if directory not in EXCLUDED_DIRECTORIES
        ]
        for filename in sorted(files):
            if not filename.endswith(".md") or any(
                pattern in filename.lower() for pattern in excluded_patterns
            ):
                continue
            candidate = Path(root) / filename
            try:
                resolved = candidate.resolve()
                if not resolved.is_relative_to(vault):
                    continue
                relative_path = candidate.relative_to(vault).as_posix()
                content = _read_note(candidate)
            except (OSError, ValueError) as error:
                raise RuntimeError(f"Could not read Markdown note {candidate}: {error}") from error
            if not content.strip():
                continue
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            snapshots[relative_path] = _NoteSnapshot(relative_path, content, content_hash)
    return dict(sorted(snapshots.items()))


def _records_for_snapshots(
    vault: Path,
    snapshots: dict[str, _NoteSnapshot],
) -> list[dict[str, str | int]]:
    splitter = get_text_splitter()
    records: list[dict[str, str | int]] = []
    for relative_path, snapshot in snapshots.items():
        document = Document(
            page_content=snapshot.content,
            metadata={
                "source": str(vault / relative_path),
                "content_hash": snapshot.content_hash,
            },
        )
        records.extend(_chunk_records(vault, splitter.split_documents([document])))
    return records


def _chunk_records(vault: Path, chunks: list[Document]) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    ordinals: dict[str, int] = {}
    for chunk in chunks:
        source = Path(str(chunk.metadata.get("source", ""))).resolve()
        try:
            relative_path = source.relative_to(vault).as_posix()
        except ValueError as error:
            raise RuntimeError(f"Indexed source is outside the vault: {source}") from error
        ordinal = ordinals.get(relative_path, 0)
        ordinals[relative_path] = ordinal + 1
        content_hash = str(chunk.metadata.get("content_hash", ""))
        if not content_hash:
            content_hash = hashlib.sha256(chunk.page_content.encode("utf-8")).hexdigest()
        chunk_id = hashlib.sha256(
            f"{relative_path}\0{content_hash}\0{ordinal}\0{chunk.page_content}".encode("utf-8")
        ).hexdigest()
        records.append(
            {
                "chunk_id": chunk_id,
                "note_path": relative_path,
                "ordinal": ordinal,
                "text": chunk.page_content,
                "content_hash": content_hash,
            }
        )
    return records


def _create_catalog(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;
        CREATE TABLE notes (
            note_path TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content_hash TEXT NOT NULL
        );
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            note_path TEXT NOT NULL REFERENCES notes(note_path),
            ordinal INTEGER NOT NULL,
            text TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED,
            note_path UNINDEXED,
            title,
            text,
            tokenize='unicode61 remove_diacritics 2'
        );
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )


def _write_catalog(connection: sqlite3.Connection, records: list[dict[str, str | int]]) -> None:
    notes = sorted({str(record["note_path"]) for record in records})
    content_hashes = {
        str(record["note_path"]): str(record.get("content_hash", "")) for record in records
    }
    connection.executemany(
        "INSERT INTO notes(note_path, title, content_hash) VALUES (?, ?, ?)",
        ((note, Path(note).stem, content_hashes[note]) for note in notes),
    )
    connection.executemany(
        "INSERT INTO chunks(chunk_id, note_path, ordinal, text) VALUES (?, ?, ?, ?)",
        (
            (
                record["chunk_id"],
                record["note_path"],
                record["ordinal"],
                record["text"],
            )
            for record in records
        ),
    )
    connection.executemany(
        "INSERT INTO chunks_fts(chunk_id, note_path, title, text) VALUES (?, ?, ?, ?)",
        (
            (
                record["chunk_id"],
                record["note_path"],
                Path(str(record["note_path"])).stem,
                record["text"],
            )
            for record in records
        ),
    )


def _write_vectors(
    lancedb,
    path: Path,
    records: list[dict[str, str | int]],
    embeddings: Embeddings,
    *,
    reused_vectors: dict[str, list[float]] | None = None,
    expected_dimension: int | None = None,
) -> int:
    database = lancedb.connect(path)
    reused_vectors = reused_vectors or {}
    vectors_by_id: dict[str, list[float]] = {}
    dimension = expected_dimension or 0
    for offset in range(0, len(records), EMBED_BATCH_SIZE):
        batch = records[offset : offset + EMBED_BATCH_SIZE]
        missing = [record for record in batch if str(record["chunk_id"]) not in reused_vectors]
        if missing:
            vectors = embeddings.embed_documents([str(record["text"]) for record in missing])
            if len(vectors) != len(missing) or not vectors:
                raise RuntimeError("Embedding provider returned an unexpected vector count")
            for record, embedded_vector in zip(missing, vectors):
                vectors_by_id[str(record["chunk_id"])] = [float(value) for value in embedded_vector]

        rows = []
        for record in batch:
            chunk_id = str(record["chunk_id"])
            vector: list[float] | None = reused_vectors.get(chunk_id)
            if vector is None:
                vector = vectors_by_id.get(chunk_id)
            if vector is None:
                raise RuntimeError(f"No vector was produced for chunk {chunk_id}")
            if not vector or (dimension and len(vector) != dimension):
                if expected_dimension is not None:
                    raise FullRebuildRequired("Embedding dimension changed; run --full-rebuild")
                raise RuntimeError("Embedding provider returned inconsistent vector dimensions")
            dimension = len(vector)
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "note_path": record["note_path"],
                    "vector": vector,
                }
            )
        if offset == 0:
            database.create_table("chunks", data=rows, mode="create")
        else:
            database.open_table("chunks").add(rows)
    return dimension


def _write_metadata(
    connection: sqlite3.Connection,
    dimension: int,
    notes: int,
    chunks: int,
    snapshots: dict[str, _NoteSnapshot] | None = None,
) -> None:
    settings = get_settings()
    values = {
        "schema_version": str(SCHEMA_VERSION),
        "embedding_signature": embedding_signature(),
        "embedding_dimension": str(dimension),
        "config_hash": _configuration_hash(dimension),
        "chunk_size": str(settings.chunk_size),
        "chunk_overlap": str(settings.chunk_overlap),
        "notes": str(notes),
        "chunks": str(chunks),
    }
    if snapshots is not None:
        values["note_manifest"] = json.dumps(
            {path: snapshot.content_hash for path, snapshot in sorted(snapshots.items())},
            sort_keys=True,
        )
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", values.items())


def _validate_revision(
    catalog_path: Path,
    vectors_path: Path,
    expected_chunks: int | set[str],
) -> None:
    connection = sqlite3.connect(catalog_path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        catalog_rows = connection.execute("SELECT chunk_id FROM chunks").fetchall()
        fts_rows = connection.execute("SELECT chunk_id FROM chunks_fts").fetchall()
    finally:
        connection.close()

    catalog_ids = {str(row[0]) for row in catalog_rows}
    fts_ids = {str(row[0]) for row in fts_rows}
    if len(catalog_ids) != len(catalog_rows) or len(fts_ids) != len(fts_rows):
        raise RuntimeError("Experimental index validation failed: duplicate chunk IDs")

    try:
        lancedb = require_lancedb()
        vector_rows = lancedb.connect(vectors_path).open_table("chunks").to_arrow().to_pylist()
        vector_ids = {str(row["chunk_id"]) for row in vector_rows}
    except Exception as error:
        raise RuntimeError("Experimental index validation failed: LanceDB is unreadable") from error
    if len(vector_ids) != len(vector_rows):
        raise RuntimeError("Experimental index validation failed: duplicate vector IDs")

    expected_ids = expected_chunks if isinstance(expected_chunks, set) else None
    counts_match = (
        all(len(ids) == expected_chunks for ids in (catalog_ids, fts_ids, vector_ids))
        if isinstance(expected_chunks, int)
        else True
    )
    if (
        integrity != "ok"
        or catalog_ids != fts_ids
        or catalog_ids != vector_ids
        or (expected_ids is not None and catalog_ids != expected_ids)
        or not counts_match
    ):
        raise RuntimeError("Experimental index validation failed: chunk IDs disagree")


def _activate(root: Path, active: dict[str, object]) -> None:
    active_tmp = root / f"active-{uuid.uuid4().hex}.json"
    try:
        with active_tmp.open("w", encoding="utf-8") as manifest:
            json.dump(active, manifest, indent=2)
            manifest.flush()
            os.fsync(manifest.fileno())
        os.replace(active_tmp, root / "active.json")
    finally:
        try:
            active_tmp.unlink()
        except FileNotFoundError:
            pass
