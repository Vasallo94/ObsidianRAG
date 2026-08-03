"""Safe revisioned SQLite FTS5 + LanceDB indexing for the v4 engine."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import shutil
import sqlite3
import stat
import struct
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator, Literal

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from obsidianrag.config import get_settings
from obsidianrag.core.db_service import get_text_splitter
from obsidianrag.core.metadata_tracker import EXCLUDED_DIRECTORIES

SCHEMA_VERSION = 3
EMBED_BATCH_SIZE = 64
_FINGERPRINT_DOCUMENTS = (
    "obsidianrag synthetic document probe alpha",
    "obsidianrag synthetic document probe beta",
)
_FINGERPRINT_QUERY = "obsidianrag synthetic query probe"


class V4DependencyError(RuntimeError):
    """Raised when a required v4 dependency is unavailable."""


class FullRebuildRequired(RuntimeError):
    """Raised when an active revision cannot be updated incrementally."""


class IndexBuildLocked(RuntimeError):
    """Raised when another v4 revision is currently being built."""


class IndexPathError(RuntimeError):
    """Raised when an index or vault path is unsafe."""


class IndexCorruptionError(RuntimeError):
    """Raised when persisted v4 state is malformed or inconsistent."""


class RevisionInUse(RuntimeError):
    """Raised when pruning would delete a revision held by a reader."""


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
class PruneResult:
    deleted_revisions: tuple[str, ...]
    active_revision: str


@dataclass(frozen=True)
class IndexStatus:
    """Read-only summary of the active v4 revision and vault drift."""

    state: Literal["missing", "current", "stale", "rebuild_required"]
    active_revision: str | None = None
    indexed_notes: int = 0
    indexed_chunks: int = 0
    changed_notes: int = 0
    deleted_notes: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class _NoteSnapshot:
    path: str
    content: str
    content_hash: str


@dataclass
class RevisionLease:
    """A filesystem lease that prevents an inactive revision from being pruned."""

    path: Path
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            _reject_link(self.path)
            self.path.unlink()
        except FileNotFoundError:
            pass


def require_lancedb():
    try:
        import lancedb
    except ImportError as error:
        raise V4DependencyError(
            "LanceDB is required; reinstall the standard obsidianrag package"
        ) from error
    return lancedb


def _is_link(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise IndexPathError(f"Could not inspect managed path {path}: {error}") from error
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_point)


def _reject_link(path: Path) -> None:
    if _is_link(path):
        raise IndexPathError(f"Managed v4 paths cannot be links: {path}")


def _ensure_directory(path: Path) -> Path:
    try:
        path.mkdir(exist_ok=True)
    except OSError as error:
        raise IndexPathError(f"Could not create managed directory {path}: {error}") from error
    _reject_link(path)
    try:
        mode = path.stat(follow_symlinks=False).st_mode
    except OSError as error:
        raise IndexPathError(f"Could not inspect managed directory {path}: {error}") from error
    if not stat.S_ISDIR(mode):
        raise IndexPathError(f"Managed v4 path is not a directory: {path}")
    return path


def _v4_root(vault: Path, *, create: bool = False) -> Path:
    vault = vault.resolve()
    if not vault.is_dir():
        raise IndexPathError(f"Vault is not a directory: {vault}")
    current = vault
    for component in (".obsidianrag", "v4"):
        current = current / component
        if create:
            _ensure_directory(current)
        else:
            _reject_link(current)
    return current


def _indexes_path(root: Path, *, create: bool = False) -> Path:
    path = root / "indexes"
    return _ensure_directory(path) if create else _checked_directory(path)


def _checked_directory(path: Path) -> Path:
    _reject_link(path)
    try:
        if not stat.S_ISDIR(path.stat(follow_symlinks=False).st_mode):
            raise IndexPathError(f"Managed v4 path is not a directory: {path}")
    except FileNotFoundError as error:
        raise IndexCorruptionError(f"Managed v4 directory is missing: {path}") from error
    return path


def _open_regular(path: Path, flags: int, mode: int = 0o600) -> tuple[int, os.stat_result]:
    _reject_link(path)
    try:
        if path.exists() and not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
            raise IndexPathError(f"Managed v4 path is not a regular file: {path}")
    except OSError as error:
        raise IndexPathError(f"Could not inspect managed file {path}: {error}") from error
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags | nofollow, mode)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise IndexPathError(f"Managed v4 path must be a single-link regular file: {path}")
        current = path.stat(follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise IndexPathError(f"Managed v4 path changed while opening: {path}")
        return descriptor, opened
    except Exception as error:
        descriptor_value = locals().get("descriptor")
        if isinstance(descriptor_value, int):
            os.close(descriptor_value)
        if isinstance(error, OSError):
            raise IndexPathError(f"Could not open managed file {path}: {error}") from error
        raise


def _read_regular_bytes(path: Path) -> bytes:
    try:
        descriptor, opened = _open_regular(path, os.O_RDONLY)
        with os.fdopen(descriptor, "rb") as handle:
            value = handle.read()
        current = path.stat(follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise IndexPathError(f"File changed while reading: {path}")
        return value
    except (IndexPathError, FileNotFoundError):
        raise
    except OSError as error:
        raise IndexPathError(f"Could not read regular file {path}: {error}") from error


@contextmanager
def _build_lock(root: Path) -> Iterator[None]:
    """Take an OS-released lock without following a malicious lock link."""
    root = _checked_directory(root)
    lock_path = root / "build.lock"
    descriptor, _ = _open_regular(lock_path, os.O_RDWR | os.O_CREAT)
    lock_file: BinaryIO = os.fdopen(descriptor, "r+b")
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()
    lock_file.seek(0)
    try:
        if os.name == "nt":
            msvcrt = importlib.import_module("msvcrt")
            getattr(msvcrt, "locking")(descriptor, getattr(msvcrt, "LK_NBLCK"), 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        lock_file.close()
        raise IndexBuildLocked("Another v4 index build or prune is running") from error

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
            getattr(msvcrt, "locking")(descriptor, getattr(msvcrt, "LK_UNLCK"), 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
        lock_file.close()


def _embedding_identity() -> dict[str, str]:
    settings = get_settings()
    model = (
        settings.ollama_embedding_model
        if settings.embedding_provider == "ollama"
        else settings.embedding_model
    )
    identity = {"provider": settings.embedding_provider, "model": model}
    if settings.embedding_provider == "ollama":
        identity["endpoint"] = settings.ollama_base_url.rstrip("/")
    return identity


def _canonical_vector(vector: list[float]) -> bytes:
    values = [float(value) for value in vector]
    if not values or any(not math.isfinite(value) for value in values):
        raise RuntimeError("Embedding provider returned an empty or non-finite probe vector")
    return b"".join(struct.pack("!f", value) for value in values)


def embedding_fingerprint(embeddings: Embeddings) -> tuple[str, int]:
    """Fingerprint the configured encoder and its actual synthetic output."""
    document_vectors = embeddings.embed_documents(list(_FINGERPRINT_DOCUMENTS))
    query_vector = embeddings.embed_query(_FINGERPRINT_QUERY)
    if len(document_vectors) != len(_FINGERPRINT_DOCUMENTS):
        raise RuntimeError("Embedding provider returned an unexpected probe vector count")
    vectors = [*document_vectors, query_vector]
    dimension = len(vectors[0]) if vectors else 0
    if dimension <= 0 or any(len(vector) != dimension for vector in vectors):
        raise RuntimeError("Embedding provider returned inconsistent probe dimensions")
    payload = {
        "class": f"{type(embeddings).__module__}.{type(embeddings).__qualname__}",
        "config": _embedding_identity(),
        "probe_version": 1,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    for vector in vectors:
        digest.update(_canonical_vector(vector))
    return digest.hexdigest(), dimension


def build_index(
    vault_path: Path,
    embeddings: Embeddings,
    *,
    full_rebuild: bool = False,
) -> IndexBuildResult:
    """Build, validate, and atomically activate a copy-on-write v4 revision."""
    lancedb = require_lancedb()
    vault = vault_path.resolve()
    root = _v4_root(vault, create=True)
    root_identity = root.stat(follow_symlinks=False)
    revisions = _indexes_path(root, create=True)

    with _build_lock(root):
        snapshots = _scan_vault(vault)
        fingerprint, probe_dimension = embedding_fingerprint(embeddings)
        active_manifest = None if full_rebuild else _read_manifest(root / "active.json")

        old_revision: Path | None = None
        old_metadata: dict[str, str] = {}
        old_chunks: list[dict[str, str | int]] = []
        old_manifest: dict[str, str] = {}
        if active_manifest is not None:
            if active_manifest.get("schema_version") != SCHEMA_VERSION:
                raise FullRebuildRequired(
                    "Active v4 index schema is incompatible; run --full-rebuild"
                )
            old_revision = active_revision(vault)
            old_metadata, old_chunks, old_manifest = _read_revision(old_revision)
            _assert_incremental_compatible(
                old_metadata, fingerprint=fingerprint, dimension=probe_dimension
            )
            _validate_revision(old_revision, expected_chunks=len(old_chunks))
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
        try:
            revision_path.mkdir(exist_ok=False)
        except OSError as error:
            raise IndexPathError(
                f"Could not create v4 revision {revision_path}: {error}"
            ) from error
        revision_identity = _checked_directory(revision_path).stat(follow_symlinks=False)
        try:
            if old_revision is None:
                records = _records_for_snapshots(vault, snapshots)
                unchanged_records: list[dict[str, str | int]] = []
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
                reused_chunks = len(unchanged_records)

            catalog_path = revision_path / "catalog.sqlite3"
            try:
                connection = sqlite3.connect(catalog_path)
                try:
                    _create_catalog(connection)
                    _write_catalog(connection, records)
                    try:
                        _write_vectors(
                            lancedb,
                            revision_path / "vectors",
                            records,
                            embeddings,
                            dimension=probe_dimension,
                            old_revision=old_revision,
                            reused_ids={str(record["chunk_id"]) for record in unchanged_records},
                        )
                    except RuntimeError:
                        raise
                    except Exception as error:
                        raise IndexCorruptionError(
                            "Could not write the v4 LanceDB table"
                        ) from error
                    _write_metadata(
                        connection,
                        probe_dimension,
                        fingerprint,
                        snapshots,
                        len(records),
                    )
                    connection.commit()
                finally:
                    connection.close()
            except sqlite3.Error as error:
                raise IndexCorruptionError("Could not write the v4 SQLite catalog") from error

            _validate_revision(revision_path, expected_chunks=len(records))
            _fsync_file(catalog_path)
            _fsync_tree(revision_path / "vectors")
            _fsync_directory(revision_path)
            _fsync_directory(revisions)
            if _scan_vault(vault) != snapshots:
                raise RuntimeError("Vault changed during v4 indexing; retry the build")
            active = {
                "schema_version": SCHEMA_VERSION,
                "revision": revision,
                "activated_at": datetime.now(timezone.utc).isoformat(),
            }
            _activate(root, active, root_identity)
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
            if not _manifest_points_to(root / "active.json", revision):
                _safe_rmtree(revisions, revision_path, revision_identity)


def index_status(vault_path: Path, embeddings: Embeddings | None = None) -> IndexStatus:
    """Inspect the active index without creating files or loading indexed content."""
    vault = vault_path.resolve()
    root = _v4_root(vault)
    snapshots = _scan_vault(vault)
    try:
        active_manifest = _read_manifest(root / "active.json")
    except IndexPathError:
        raise
    except IndexCorruptionError as error:
        return IndexStatus(
            state="rebuild_required",
            changed_notes=len(snapshots),
            reason=str(error),
        )
    if active_manifest is None:
        return IndexStatus(
            state="missing",
            changed_notes=len(snapshots),
            reason="No active v4 index exists",
        )

    revision_name: str | None = None
    indexed_notes = 0
    indexed_chunks = 0
    changed = len(snapshots)
    deleted = 0
    try:
        revision_name = _manifest_revision(active_manifest)
        if active_manifest.get("schema_version") != SCHEMA_VERSION:
            raise FullRebuildRequired("Active v4 index schema is incompatible")
        indexes = _indexes_path(root)
        revision_path = indexes / revision_name
        if revision_path.parent != indexes:
            raise IndexPathError("Invalid v4 revision path")
        metadata, manifest, indexed_notes, indexed_chunks = _read_revision_summary(revision_path)
        changed = sum(
            path not in manifest or manifest[path] != snapshot.content_hash
            for path, snapshot in snapshots.items()
        )
        deleted = len(set(manifest) - set(snapshots))
        if metadata.get("schema_version") != str(SCHEMA_VERSION):
            raise FullRebuildRequired("Active v4 index schema is incompatible")
        settings = get_settings()
        for key, value in {
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
        }.items():
            if metadata.get(key) != str(value):
                raise FullRebuildRequired(f"Active v4 index {key} is incompatible")
        if embeddings is not None:
            fingerprint, dimension = embedding_fingerprint(embeddings)
            _assert_incremental_compatible(metadata, fingerprint=fingerprint, dimension=dimension)
    except IndexPathError:
        raise
    except (FullRebuildRequired, IndexCorruptionError) as error:
        return IndexStatus(
            state="rebuild_required",
            active_revision=revision_name,
            indexed_notes=indexed_notes,
            indexed_chunks=indexed_chunks,
            changed_notes=changed,
            deleted_notes=deleted,
            reason=str(error),
        )

    if changed or deleted:
        return IndexStatus(
            state="stale",
            active_revision=revision_name,
            indexed_notes=indexed_notes,
            indexed_chunks=indexed_chunks,
            changed_notes=changed,
            deleted_notes=deleted,
            reason="Vault contents differ from the active v4 index",
        )
    return IndexStatus(
        state="current",
        active_revision=revision_name,
        indexed_notes=indexed_notes,
        indexed_chunks=indexed_chunks,
    )


def _read_revision_summary(
    revision_path: Path,
) -> tuple[dict[str, str], dict[str, str], int, int]:
    """Read bounded metadata/count summaries without materializing indexed rows."""
    checked = _checked_directory(revision_path)
    _assert_tree_no_links(checked)
    catalog_path = checked / "catalog.sqlite3"
    _reject_link(catalog_path)
    _checked_directory(checked / "vectors")
    try:
        connection = sqlite3.connect(f"{catalog_path.as_uri()}?mode=ro", uri=True)
        try:
            metadata = {
                str(key): str(value)
                for key, value in connection.execute("SELECT key, value FROM metadata")
            }
            indexed_notes = int(connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0])
            indexed_chunks = int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
            connection.execute("SELECT 1 FROM chunks_fts LIMIT 1").fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, TypeError, ValueError) as error:
        raise IndexCorruptionError("The active v4 revision summary is unreadable") from error

    try:
        manifest_value = json.loads(metadata["note_manifest"])
        if not isinstance(manifest_value, dict):
            raise ValueError("note manifest is not an object")
        manifest = {str(path): str(content_hash) for path, content_hash in manifest_value.items()}
        for path, content_hash in manifest.items():
            normalized = Path(path)
            if (
                normalized.is_absolute()
                or ".." in normalized.parts
                or normalized.as_posix() != path
                or normalized.suffix != ".md"
                or len(content_hash) != 64
            ):
                raise ValueError("note manifest contains an invalid entry")
        if int(metadata["notes"]) != indexed_notes or int(metadata["chunks"]) != indexed_chunks:
            raise ValueError("metadata counts disagree with the catalog")
        if metadata["schema_version"] != str(SCHEMA_VERSION):
            raise ValueError("schema version is incompatible")
        dimension = int(metadata["embedding_dimension"])
        if dimension <= 0 or len(metadata["embedding_fingerprint"]) != 64:
            raise ValueError("embedding metadata is invalid")
        table = require_lancedb().connect(checked / "vectors").open_table("chunks")
        if table.count_rows() != indexed_chunks:
            raise ValueError("vector count disagrees with the catalog")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise IndexCorruptionError("The active v4 revision metadata is invalid") from error
    except Exception as error:
        raise IndexCorruptionError("The active v4 vector table is unreadable") from error
    return metadata, manifest, indexed_notes, indexed_chunks


def active_revision(vault_path: Path) -> Path:
    """Return the active validated revision path without following links."""
    root = _v4_root(vault_path)
    active = _read_manifest(root / "active.json")
    if active is None:
        raise IndexCorruptionError("No v4 index found. Run: obsidianrag index --vault ...")
    revision = _manifest_revision(active)
    if active.get("schema_version") != SCHEMA_VERSION:
        raise IndexCorruptionError("Unsupported v4 index manifest; run --full-rebuild")
    indexes = _indexes_path(root)
    revision_path = indexes / revision
    if revision_path.parent != indexes or Path(revision).name != revision:
        raise IndexPathError("Invalid v4 revision path")
    checked = _checked_directory(revision_path)
    _assert_tree_no_links(checked)
    return checked


def _new_revision_name() -> str:
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"


def _read_manifest(path: Path) -> dict[str, object] | None:
    _reject_link(path)
    if not path.exists():
        return None
    try:
        value = json.loads(_read_regular_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as error:
        raise IndexCorruptionError(
            "The active v4 manifest is malformed; run obsidianrag index --full-rebuild"
        ) from error
    if not isinstance(value, dict):
        raise IndexCorruptionError(
            "The active v4 manifest is invalid; run obsidianrag index --full-rebuild"
        )
    return value


def _manifest_revision(manifest: dict[str, object]) -> str:
    revision = manifest.get("revision")
    if (
        not isinstance(revision, str)
        or not revision
        or Path(revision).name != revision
        or revision in {".", ".."}
    ):
        raise IndexCorruptionError("The active v4 manifest has an invalid revision path")
    return revision


def _manifest_points_to(path: Path, revision: str) -> bool:
    try:
        manifest = _read_manifest(path)
        return manifest is not None and _manifest_revision(manifest) == revision
    except RuntimeError:
        return False


def _read_revision(
    revision_path: Path,
) -> tuple[dict[str, str], list[dict[str, str | int]], dict[str, str]]:
    catalog_path = revision_path / "catalog.sqlite3"
    _reject_link(catalog_path)
    try:
        connection = sqlite3.connect(f"{catalog_path.as_uri()}?mode=ro", uri=True)
        try:
            metadata = {
                str(key): str(value)
                for key, value in connection.execute("SELECT key, value FROM metadata")
            }
            note_rows = connection.execute("SELECT note_path, content_hash FROM notes").fetchall()
            rows = connection.execute(
                "SELECT chunk_id, note_path, ordinal, text FROM chunks"
            ).fetchall()
        finally:
            connection.close()
        manifest_value = json.loads(metadata["note_manifest"])
        if not isinstance(manifest_value, dict):
            raise ValueError("note manifest is not an object")
        manifest = {str(path): str(value) for path, value in manifest_value.items()}
        catalog_manifest = {str(path): str(value) for path, value in note_rows}
        if manifest != catalog_manifest:
            raise ValueError("catalog note hashes do not match the manifest")
        chunks: list[dict[str, str | int]] = []
        for row in rows:
            chunks.append(
                {
                    "chunk_id": str(row[0]),
                    "note_path": str(row[1]),
                    "ordinal": int(row[2]),
                    "text": str(row[3]),
                    "content_hash": manifest[str(row[1])],
                }
            )
        return metadata, chunks, manifest
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, sqlite3.Error) as error:
        raise FullRebuildRequired(
            "The active v4 revision is corrupt or lacks incremental metadata; run --full-rebuild"
        ) from error


def _configuration_hash(dimension: int, fingerprint: str) -> str:
    settings = get_settings()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "embedding_fingerprint": fingerprint,
        "embedding_dimension": dimension,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _assert_incremental_compatible(
    metadata: dict[str, str], *, fingerprint: str, dimension: int
) -> None:
    settings = get_settings()
    expected = {
        "schema_version": str(SCHEMA_VERSION),
        "embedding_dimension": str(dimension),
        "embedding_fingerprint": fingerprint,
        "chunk_size": str(settings.chunk_size),
        "chunk_overlap": str(settings.chunk_overlap),
        "config_hash": _configuration_hash(dimension, fingerprint),
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            label = "configuration hash" if key == "config_hash" else key
            raise FullRebuildRequired(
                f"Active v4 index {label} is incompatible; run --full-rebuild"
            )


def _decode_note(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("latin-1")


def _assert_vault_file_path(vault: Path, path: Path) -> None:
    try:
        relative = path.relative_to(vault)
    except ValueError as error:
        raise IndexPathError(f"Markdown note is outside the vault: {path}") from error
    current = vault
    for component in relative.parts:
        current /= component
        if _is_link(current):
            raise IndexPathError(f"Markdown note paths cannot contain links: {path}")
    try:
        if not path.resolve(strict=True).is_relative_to(vault):
            raise IndexPathError(f"Markdown note resolves outside the vault: {path}")
    except OSError as error:
        raise IndexPathError(f"Could not resolve Markdown note {path}: {error}") from error


def _read_vault_note(vault: Path, relative: Path) -> str:
    path = vault / relative
    _assert_vault_file_path(vault, path)
    if os.name == "nt":
        value = _read_regular_bytes(path)
        _assert_vault_file_path(vault, path)
        return _decode_note(value)

    try:
        directory_fd = os.open(
            vault,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise IndexPathError(f"Could not open vault directory {vault}: {error}") from error
    root_fd = directory_fd
    try:
        for component in relative.parts[:-1]:
            child_fd = os.open(
                component,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            opened_directory = os.fstat(child_fd)
            if not stat.S_ISDIR(opened_directory.st_mode):
                os.close(child_fd)
                raise IndexPathError(f"Markdown note parent is not a directory: {path}")
            if directory_fd != root_fd:
                os.close(directory_fd)
            directory_fd = child_fd
        descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise IndexPathError(f"Markdown note must be a single-link regular file: {path}")
            value = handle.read()
            after = os.fstat(handle.fileno())
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise IndexPathError(f"Markdown note changed while reading: {path}")
        return _decode_note(value)
    except OSError as error:
        raise IndexPathError(f"Could not safely read Markdown note {path}: {error}") from error
    finally:
        if directory_fd != root_fd:
            os.close(directory_fd)
        os.close(root_fd)


def _scan_vault(vault: Path) -> dict[str, _NoteSnapshot]:
    """Scan regular Markdown files directly without following any links."""
    excluded_patterns = (".excalidraw.md", ".canvas", "untitled")
    snapshots: dict[str, _NoteSnapshot] = {}
    for root_value, directories, files in os.walk(vault, followlinks=False):
        root = Path(root_value)
        safe_directories: list[str] = []
        for directory in directories:
            candidate = root / directory
            if directory in EXCLUDED_DIRECTORIES:
                continue
            if _is_link(candidate):
                raise IndexPathError(f"Markdown note paths cannot contain links: {candidate}")
            safe_directories.append(directory)
        directories[:] = safe_directories
        for filename in sorted(files):
            if not filename.endswith(".md") or any(
                pattern in filename.lower() for pattern in excluded_patterns
            ):
                continue
            candidate = root / filename
            try:
                relative = candidate.relative_to(vault)
                relative_path = relative.as_posix()
                content = _read_vault_note(vault, relative)
            except (OSError, ValueError) as error:
                raise IndexPathError(
                    f"Could not read Markdown note {candidate}: {error}"
                ) from error
            if not content.strip():
                continue
            snapshots[relative_path] = _NoteSnapshot(
                relative_path,
                content,
                hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
    return dict(sorted(snapshots.items()))


def _records_for_snapshots(
    vault: Path, snapshots: dict[str, _NoteSnapshot]
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


def _chunk_id(note_path: str, content_hash: str, ordinal: int, text: str) -> str:
    return hashlib.sha256(
        f"{note_path}\0{content_hash}\0{ordinal}\0{text}".encode("utf-8")
    ).hexdigest()


def _chunk_records(vault: Path, chunks: list[Document]) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    ordinals: dict[str, int] = {}
    for chunk in chunks:
        source = Path(str(chunk.metadata.get("source", "")))
        try:
            relative_path = source.relative_to(vault).as_posix()
        except ValueError as error:
            raise IndexPathError(f"Indexed source is outside the vault: {source}") from error
        ordinal = ordinals.get(relative_path, 0)
        ordinals[relative_path] = ordinal + 1
        content_hash = str(chunk.metadata.get("content_hash", ""))
        if not content_hash:
            raise RuntimeError(f"Indexed chunk has no note content hash: {relative_path}")
        records.append(
            {
                "chunk_id": _chunk_id(relative_path, content_hash, ordinal, chunk.page_content),
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
        PRAGMA journal_mode = DELETE;
        PRAGMA synchronous = FULL;
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
            text TEXT NOT NULL,
            UNIQUE(note_path, ordinal)
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
    content_hashes = {str(record["note_path"]): str(record["content_hash"]) for record in records}
    connection.executemany(
        "INSERT INTO notes(note_path, title, content_hash) VALUES (?, ?, ?)",
        ((note, Path(note).stem, content_hashes[note]) for note in notes),
    )
    connection.executemany(
        "INSERT INTO chunks(chunk_id, note_path, ordinal, text) VALUES (?, ?, ?, ?)",
        (
            (record["chunk_id"], record["note_path"], record["ordinal"], record["text"])
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


def _vector_schema(dimension: int):
    try:
        import pyarrow as pa
    except ImportError as error:
        raise V4DependencyError("LanceDB requires pyarrow for v4 indexing") from error
    return pa.schema(
        [
            pa.field("chunk_id", pa.string(), nullable=False),
            pa.field("note_path", pa.string(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), dimension), nullable=False),
        ]
    )


def _validated_vector(vector: list[float], dimension: int) -> list[float]:
    values = [float(value) for value in vector]
    if len(values) != dimension or any(not math.isfinite(value) for value in values):
        raise RuntimeError("Embedding provider returned an invalid vector")
    return values


def _write_vectors(
    lancedb,
    path: Path,
    records: list[dict[str, str | int]],
    embeddings: Embeddings,
    *,
    dimension: int,
    old_revision: Path | None,
    reused_ids: set[str],
) -> None:
    database = lancedb.connect(path)
    table = database.create_table("chunks", schema=_vector_schema(dimension), mode="create")
    records_by_id = {str(record["chunk_id"]): record for record in records}
    new_records = [record for record in records if str(record["chunk_id"]) not in reused_ids]
    for offset in range(0, len(new_records), EMBED_BATCH_SIZE):
        batch = new_records[offset : offset + EMBED_BATCH_SIZE]
        vectors = embeddings.embed_documents([str(record["text"]) for record in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("Embedding provider returned an unexpected vector count")
        table.add(
            [
                {
                    "chunk_id": str(record["chunk_id"]),
                    "note_path": str(record["note_path"]),
                    "vector": _validated_vector(vector, dimension),
                }
                for record, vector in zip(batch, vectors)
            ]
        )

    if old_revision is None or not reused_ids:
        return
    old_vectors = _checked_directory(old_revision / "vectors")
    old_table = lancedb.connect(old_vectors).open_table("chunks")
    copied: set[str] = set()
    reader = (
        old_table.search()
        .select(["chunk_id", "note_path", "vector"])
        .to_batches(batch_size=EMBED_BATCH_SIZE)
    )
    for batch in reader:
        rows = []
        for row in batch.to_pylist():
            chunk_id = str(row["chunk_id"])
            if chunk_id not in reused_ids:
                continue
            record = records_by_id[chunk_id]
            if str(row["note_path"]) != str(record["note_path"]):
                raise FullRebuildRequired("Reusable vector metadata is corrupt; run --full-rebuild")
            if chunk_id in copied:
                raise FullRebuildRequired("Reusable vectors are duplicated; run --full-rebuild")
            copied.add(chunk_id)
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "note_path": str(row["note_path"]),
                    "vector": _validated_vector(row["vector"], dimension),
                }
            )
        if rows:
            table.add(rows)
    if copied != reused_ids:
        raise FullRebuildRequired("The active v4 revision is missing vectors; run --full-rebuild")


def _write_metadata(
    connection: sqlite3.Connection,
    dimension: int,
    fingerprint: str,
    snapshots: dict[str, _NoteSnapshot],
    chunks: int,
) -> None:
    settings = get_settings()
    values = {
        "schema_version": str(SCHEMA_VERSION),
        "embedding_fingerprint": fingerprint,
        "embedding_dimension": str(dimension),
        "config_hash": _configuration_hash(dimension, fingerprint),
        "chunk_size": str(settings.chunk_size),
        "chunk_overlap": str(settings.chunk_overlap),
        "notes": str(len(snapshots)),
        "chunks": str(chunks),
        "note_manifest": json.dumps(
            {path: snapshot.content_hash for path, snapshot in sorted(snapshots.items())},
            sort_keys=True,
        ),
    }
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", values.items())


def _validate_revision(revision_path: Path, expected_chunks: int | set[str]) -> None:
    _assert_tree_no_links(revision_path)
    catalog_path = revision_path / "catalog.sqlite3"
    _reject_link(catalog_path)
    try:
        connection = sqlite3.connect(f"{catalog_path.as_uri()}?mode=ro", uri=True)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            note_rows = connection.execute(
                "SELECT note_path, title, content_hash FROM notes"
            ).fetchall()
            catalog_rows = connection.execute(
                "SELECT chunk_id, note_path, ordinal, text FROM chunks ORDER BY note_path, ordinal"
            ).fetchall()
            fts_rows = connection.execute(
                "SELECT chunk_id, note_path, title, text FROM chunks_fts"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise IndexCorruptionError("v4 SQLite catalog is unreadable") from error

    try:
        dimension = int(metadata["embedding_dimension"])
        fingerprint = str(metadata["embedding_fingerprint"])
        if (
            metadata["schema_version"] != str(SCHEMA_VERSION)
            or len(fingerprint) != 64
            or metadata["config_hash"] != _configuration_hash(dimension, fingerprint)
        ):
            raise ValueError
        manifest_value = json.loads(metadata["note_manifest"])
        if not isinstance(manifest_value, dict):
            raise ValueError
        manifest = {str(path): str(value) for path, value in manifest_value.items()}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise IndexCorruptionError("v4 metadata is invalid") from error
    notes = {str(row[0]): (str(row[1]), str(row[2])) for row in note_rows}
    for note_path, (title, _) in notes.items():
        normalized = Path(note_path)
        if (
            normalized.is_absolute()
            or ".." in normalized.parts
            or normalized.as_posix() != note_path
            or normalized.suffix != ".md"
            or title != normalized.stem
        ):
            raise IndexCorruptionError("v4 note paths or titles are invalid")
    if manifest != {path: value[1] for path, value in notes.items()}:
        raise IndexCorruptionError("v4 note manifest disagrees with the catalog")
    if int(metadata.get("notes", "-1")) != len(notes):
        raise IndexCorruptionError("v4 note count is invalid")

    catalog: dict[str, tuple[str, int, str]] = {}
    next_ordinal: dict[str, int] = {}
    for raw_id, raw_path, raw_ordinal, raw_text in catalog_rows:
        chunk_id, note_path, text = str(raw_id), str(raw_path), str(raw_text)
        ordinal = int(raw_ordinal)
        if chunk_id in catalog or note_path not in notes:
            raise IndexCorruptionError("v4 catalog contains duplicate or orphan chunks")
        if ordinal != next_ordinal.get(note_path, 0):
            raise IndexCorruptionError("v4 chunk ordinals are not contiguous")
        next_ordinal[note_path] = ordinal + 1
        if chunk_id != _chunk_id(note_path, notes[note_path][1], ordinal, text):
            raise IndexCorruptionError("v4 deterministic chunk ID validation failed")
        catalog[chunk_id] = (note_path, ordinal, text)

    fts: dict[str, tuple[str, str, str]] = {}
    for raw_id, raw_path, raw_title, raw_text in fts_rows:
        chunk_id = str(raw_id)
        if chunk_id in fts:
            raise IndexCorruptionError("v4 FTS contains duplicate chunk IDs")
        fts[chunk_id] = (str(raw_path), str(raw_title), str(raw_text))
    expected_fts = {
        chunk_id: (note_path, notes[note_path][0], text)
        for chunk_id, (note_path, _, text) in catalog.items()
    }
    if fts != expected_fts:
        raise IndexCorruptionError("v4 FTS content disagrees with the catalog")

    vector_ids: set[str] = set()
    try:
        table = (
            require_lancedb()
            .connect(_checked_directory(revision_path / "vectors"))
            .open_table("chunks")
        )
        reader = (
            table.search()
            .select(["chunk_id", "note_path", "vector"])
            .to_batches(batch_size=EMBED_BATCH_SIZE)
        )
        for batch in reader:
            for row in batch.to_pylist():
                chunk_id = str(row["chunk_id"])
                if chunk_id in vector_ids or chunk_id not in catalog:
                    raise IndexCorruptionError("v4 vectors contain duplicate or unknown IDs")
                if str(row["note_path"]) != catalog[chunk_id][0]:
                    raise IndexCorruptionError("v4 vector paths disagree with the catalog")
                _validated_vector(row["vector"], dimension)
                vector_ids.add(chunk_id)
    except IndexCorruptionError:
        raise
    except Exception as error:
        raise IndexCorruptionError("v4 LanceDB table is unreadable") from error

    expected_ids = expected_chunks if isinstance(expected_chunks, set) else set(catalog)
    counts_match = not isinstance(expected_chunks, int) or len(catalog) == expected_chunks
    if (
        integrity != "ok"
        or foreign_keys
        or set(catalog) != set(fts)
        or set(catalog) != vector_ids
        or set(catalog) != expected_ids
        or int(metadata.get("chunks", "-1")) != len(catalog)
        or not counts_match
    ):
        raise IndexCorruptionError("v4 index validation failed")


def _fsync_file(path: Path) -> None:
    flags = os.O_RDWR if os.name == "nt" else os.O_RDONLY
    descriptor, _ = _open_regular(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise IndexPathError(f"Could not sync managed directory {path}: {error}") from error


def _fsync_tree(path: Path) -> None:
    _assert_tree_no_links(path)
    directories: list[Path] = []
    for root_value, child_directories, files in os.walk(path, followlinks=False):
        root = Path(root_value)
        directories.append(root)
        for filename in files:
            _fsync_file(root / filename)
        for child_directory in child_directories:
            _reject_link(root / child_directory)
    if os.name != "nt":
        for synced_directory in reversed(directories):
            _fsync_directory(synced_directory)


def _activate(root: Path, active: dict[str, object], expected_root: os.stat_result) -> None:
    active_name = "active.json"
    temporary_name = f"active-{uuid.uuid4().hex}.json"
    active_path = root / active_name
    temporary_path = root / temporary_name
    _reject_link(active_path)

    if os.name != "nt":
        root_fd = os.open(
            root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened_root = os.fstat(root_fd)
            if (opened_root.st_dev, opened_root.st_ino) != (
                expected_root.st_dev,
                expected_root.st_ino,
            ):
                raise IndexPathError("Managed v4 root changed before activation")
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=root_fd,
            )
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                os.close(descriptor)
                raise IndexPathError("Temporary v4 manifest is not a regular file")
            with os.fdopen(descriptor, "w", encoding="utf-8") as manifest:
                json.dump(active, manifest, indent=2)
                manifest.flush()
                os.fsync(manifest.fileno())
            os.replace(
                temporary_name,
                active_name,
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
            )
            os.fsync(root_fd)
        except OSError as error:
            raise IndexPathError(f"Could not activate v4 revision: {error}") from error
        finally:
            try:
                os.unlink(temporary_name, dir_fd=root_fd)
            except FileNotFoundError:
                pass
            os.close(root_fd)
        return

    descriptor, _ = _open_regular(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        current_root = root.stat(follow_symlinks=False)
        if (current_root.st_dev, current_root.st_ino) != (
            expected_root.st_dev,
            expected_root.st_ino,
        ):
            raise IndexPathError("Managed v4 root changed before activation")
        with os.fdopen(descriptor, "w", encoding="utf-8") as manifest:
            json.dump(active, manifest, indent=2)
            manifest.flush()
            os.fsync(manifest.fileno())
        os.replace(temporary_path, active_path)
    except OSError as error:
        raise IndexPathError(f"Could not activate v4 revision: {error}") from error
    finally:
        try:
            _reject_link(temporary_path)
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def acquire_revision_lease(vault_path: Path, revision_path: Path) -> RevisionLease:
    """Lease a revision while a retriever owns its SQLite/LanceDB handles."""
    vault = vault_path.resolve()
    root = _v4_root(vault)
    with _build_lock(root):
        indexes = _indexes_path(root)
        revision = revision_path.name
        checked = _checked_directory(indexes / revision)
        if checked != revision_path:
            raise IndexPathError("Cannot lease a revision outside the v4 index directory")
        leases_root = _ensure_directory(root / "leases")
        revision_leases = _ensure_directory(leases_root / revision)
        lease_path = revision_leases / f"{uuid.uuid4().hex}.lease"
        descriptor, _ = _open_regular(lease_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "w", encoding="utf-8") as lease:
            lease.write(f"pid={os.getpid()}\n")
            lease.flush()
            os.fsync(lease.fileno())
        return RevisionLease(lease_path)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _windows_pid_is_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetLastError.restype = wintypes.DWORD

    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return bool(kernel32.GetLastError() != 87)
    try:
        exit_code = wintypes.DWORD()
        return (
            bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)))
            and exit_code.value == 259
        )
    finally:
        kernel32.CloseHandle(handle)


def _live_leases(root: Path, revision: str) -> list[Path]:
    revision_leases = root / "leases" / revision
    if not revision_leases.exists():
        return []
    _checked_directory(revision_leases)
    live: list[Path] = []
    for lease in revision_leases.iterdir():
        if lease.suffix != ".lease":
            continue
        _reject_link(lease)
        try:
            text = _read_regular_bytes(lease).decode()
            pid = int(text.strip().removeprefix("pid="))
        except (OSError, UnicodeDecodeError, ValueError):
            live.append(lease)
            continue
        if _pid_is_alive(pid):
            live.append(lease)
        else:
            lease.unlink()
    if not live:
        try:
            revision_leases.rmdir()
        except OSError:
            pass
    return live


def prune_revisions(vault_path: Path) -> PruneResult:
    """Delete inactive revisions, refusing to delete any revision with a live lease."""
    vault = vault_path.resolve()
    root = _v4_root(vault)
    with _build_lock(root):
        active = active_revision(vault).name
        indexes = _indexes_path(root)
        inactive = [path for path in indexes.iterdir() if path.name != active]
        in_use = [path.name for path in inactive if _live_leases(root, path.name)]
        if in_use:
            raise RevisionInUse(
                "Cannot prune revisions held by active readers: " + ", ".join(sorted(in_use))
            )
        deleted: list[str] = []
        for revision_path in inactive:
            identity = revision_path.stat(follow_symlinks=False)
            _safe_rmtree(indexes, revision_path, identity)
            deleted.append(revision_path.name)
        return PruneResult(tuple(sorted(deleted)), active)


def _assert_tree_no_links(path: Path) -> None:
    _checked_directory(path)
    for root_value, directories, files in os.walk(path, followlinks=False):
        root = Path(root_value)
        for name in [*directories, *files]:
            _reject_link(root / name)


def _safe_rmtree(
    indexes: Path, revision_path: Path, expected: os.stat_result | None = None
) -> None:
    _checked_directory(indexes)
    if revision_path.parent != indexes or Path(revision_path.name).name != revision_path.name:
        raise IndexPathError("Refusing to remove a path outside the v4 revisions directory")
    if not revision_path.exists():
        return
    _assert_tree_no_links(revision_path)
    try:
        if os.name != "nt" and shutil.rmtree.avoids_symlink_attacks:
            indexes_fd = os.open(
                indexes,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                current = os.stat(revision_path.name, dir_fd=indexes_fd, follow_symlinks=False)
                if expected is not None and (current.st_dev, current.st_ino) != (
                    expected.st_dev,
                    expected.st_ino,
                ):
                    raise IndexPathError(
                        f"Refusing to remove a replaced v4 revision: {revision_path}"
                    )
                shutil.rmtree(revision_path.name, dir_fd=indexes_fd)
                os.fsync(indexes_fd)
            finally:
                os.close(indexes_fd)
        else:
            if expected is not None:
                current = revision_path.stat(follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
                    raise IndexPathError(
                        f"Refusing to remove a replaced v4 revision: {revision_path}"
                    )
            shutil.rmtree(revision_path)
    except IndexPathError:
        raise
    except OSError as error:
        raise IndexPathError(f"Could not remove v4 revision {revision_path}: {error}") from error
    _fsync_directory(indexes)
