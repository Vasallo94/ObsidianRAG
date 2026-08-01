"""Experimental revisioned SQLite + LanceDB index."""

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from obsidianrag.config import get_settings
from obsidianrag.core.db_service import get_text_splitter, load_all_obsidian_documents

SCHEMA_VERSION = 1
EMBED_BATCH_SIZE = 64


class V4DependencyError(RuntimeError):
    """Raised when the experimental optional dependencies are unavailable."""


@dataclass(frozen=True)
class IndexBuildResult:
    revision: str
    notes: int
    chunks: int
    path: Path


def require_lancedb():
    try:
        import lancedb
    except ImportError as error:
        raise V4DependencyError(
            "Experimental v4 support requires: pip install 'obsidianrag[v4]'"
        ) from error
    return lancedb


def build_index(vault_path: Path, embeddings: Embeddings) -> IndexBuildResult:
    """Build an isolated index revision and atomically activate it."""
    lancedb = require_lancedb()
    vault = vault_path.resolve()
    root = vault / ".obsidianrag" / "v4"
    revisions = root / "indexes"
    revision = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    revision_path = revisions / revision
    revision_path.mkdir(parents=True, exist_ok=False)

    try:
        documents = load_all_obsidian_documents(str(vault))
        chunks = get_text_splitter().split_documents(documents)
        if not chunks:
            raise RuntimeError("No Markdown content was available to index")

        records = _chunk_records(vault, chunks)
        note_count = len({str(record["note_path"]) for record in records})
        catalog_path = revision_path / "catalog.sqlite3"
        connection = sqlite3.connect(catalog_path)
        try:
            _create_catalog(connection)
            _write_catalog(connection, records)
            dimension = _write_vectors(lancedb, revision_path / "vectors", records, embeddings)
            _write_metadata(connection, dimension, note_count, len(records))
            connection.commit()
        finally:
            connection.close()

        _validate_revision(catalog_path, revision_path / "vectors", len(records))
        active = {
            "schema_version": SCHEMA_VERSION,
            "revision": revision,
            "activated_at": datetime.now(timezone.utc).isoformat(),
        }
        root.mkdir(parents=True, exist_ok=True)
        active_tmp = root / f"active-{uuid.uuid4().hex}.json"
        with active_tmp.open("w", encoding="utf-8") as manifest:
            json.dump(active, manifest, indent=2)
            manifest.flush()
            os.fsync(manifest.fileno())
        os.replace(active_tmp, root / "active.json")
        return IndexBuildResult(revision, note_count, len(records), revision_path)
    except Exception:
        shutil.rmtree(revision_path, ignore_errors=True)
        raise


def active_revision(vault_path: Path) -> Path:
    """Return the currently active experimental index revision."""
    root = vault_path.resolve() / ".obsidianrag" / "v4"
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
    settings = get_settings()
    if settings.embedding_provider == "ollama":
        model = settings.ollama_embedding_model
    else:
        model = settings.embedding_model
    return f"{settings.embedding_provider}:{model}"


def _chunk_records(vault: Path, chunks: list[Document]) -> list[dict[str, str | int]]:
    records = []
    ordinals: dict[str, int] = {}
    for chunk in chunks:
        source = Path(str(chunk.metadata.get("source", ""))).resolve()
        try:
            relative_path = source.relative_to(vault).as_posix()
        except ValueError as error:
            raise RuntimeError(f"Indexed source is outside the vault: {source}") from error
        ordinal = ordinals.get(relative_path, 0)
        ordinals[relative_path] = ordinal + 1
        chunk_id = hashlib.sha256(
            f"{relative_path}\0{ordinal}\0{chunk.page_content}".encode("utf-8")
        ).hexdigest()
        record: dict[str, str | int] = {
            "chunk_id": chunk_id,
            "note_path": relative_path,
            "ordinal": ordinal,
            "text": chunk.page_content,
        }
        records.append(record)
    return records


def _create_catalog(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;
        CREATE TABLE notes (
            note_path TEXT PRIMARY KEY,
            title TEXT NOT NULL
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
    connection.executemany(
        "INSERT INTO notes(note_path, title) VALUES (?, ?)",
        ((note, Path(note).stem) for note in notes),
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


def _write_vectors(lancedb, path: Path, records: list[dict], embeddings: Embeddings) -> int:
    database = lancedb.connect(path)
    table = None
    dimension = 0
    for offset in range(0, len(records), EMBED_BATCH_SIZE):
        batch = records[offset : offset + EMBED_BATCH_SIZE]
        vectors = embeddings.embed_documents([str(record["text"]) for record in batch])
        if len(vectors) != len(batch) or not vectors:
            raise RuntimeError("Embedding provider returned an unexpected vector count")
        batch_dimensions = {len(vector) for vector in vectors}
        if len(batch_dimensions) != 1 or (dimension and dimension not in batch_dimensions):
            raise RuntimeError("Embedding provider returned inconsistent vector dimensions")
        dimension = batch_dimensions.pop()
        rows = [
            {
                "chunk_id": record["chunk_id"],
                "note_path": record["note_path"],
                "vector": vector,
            }
            for record, vector in zip(batch, vectors)
        ]
        if table is None:
            table = database.create_table("chunks", data=rows, mode="create")
        else:
            table.add(rows)
    return dimension


def _write_metadata(
    connection: sqlite3.Connection, dimension: int, notes: int, chunks: int
) -> None:
    settings = get_settings()
    values = {
        "schema_version": str(SCHEMA_VERSION),
        "embedding_signature": embedding_signature(),
        "embedding_dimension": str(dimension),
        "chunk_size": str(settings.chunk_size),
        "chunk_overlap": str(settings.chunk_overlap),
        "notes": str(notes),
        "chunks": str(chunks),
    }
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", values.items())


def _validate_revision(catalog_path: Path, vectors_path: Path, expected_chunks: int) -> None:
    connection = sqlite3.connect(catalog_path)
    try:
        catalog_chunks = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
        fts_chunks = connection.execute("SELECT count(*) FROM chunks_fts").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    lancedb = require_lancedb()
    vector_chunks = lancedb.connect(vectors_path).open_table("chunks").count_rows()
    if integrity != "ok" or any(
        count != expected_chunks for count in (catalog_chunks, fts_chunks, vector_chunks)
    ):
        raise RuntimeError("Experimental index validation failed")
