"""Experimental hybrid retrieval over SQLite FTS5 and LanceDB."""

import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from obsidianrag.v4.index import (
    acquire_revision_lease,
    active_revision,
    embedding_fingerprint,
    require_lancedb,
)

RRF_CONSTANT = 60


class ExperimentalLexicalRetriever:
    """Retrieve chunks from the authoritative SQLite FTS5 catalog without embeddings."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path.resolve()
        self.revision_path = active_revision(self.vault_path)
        self.lease = acquire_revision_lease(self.vault_path, self.revision_path)
        try:
            self.connection = sqlite3.connect(
                f"{(self.revision_path / 'catalog.sqlite3').as_uri()}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
        except Exception:
            self.lease.close()
            raise

    def close(self) -> None:
        try:
            self.connection.close()
        finally:
            lease = getattr(self, "lease", None)
            if lease is not None:
                lease.close()

    def invoke(self, query: str, k: int = 10) -> list[Document]:
        if not query.strip():
            return []
        terms = re.findall(r"\w+", query, flags=re.UNICODE)
        if not terms:
            return []
        expression = " OR ".join(f'"{term}"' for term in terms)
        rows = self.connection.execute(
            "SELECT c.chunk_id, c.note_path, c.ordinal, c.text, bm25(chunks_fts) "
            "FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id "
            "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?",
            (expression, k),
        )
        return [
            Document(
                page_content=row[3],
                metadata={
                    "chunk_id": row[0],
                    "source": row[1],
                    "ordinal": row[2],
                    "score": -row[4],
                    "retrieval_type": "lexical",
                },
            )
            for row in rows
        ]


class ExperimentalRetriever:
    """Retrieve chunks from the active experimental index revision."""

    def __init__(self, vault_path: Path, embeddings: Embeddings):
        self.vault_path = vault_path.resolve()
        self.embeddings = embeddings
        self.revision_path = active_revision(self.vault_path)
        self.lease = acquire_revision_lease(self.vault_path, self.revision_path)
        try:
            self.connection = sqlite3.connect(
                f"{(self.revision_path / 'catalog.sqlite3').as_uri()}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
            metadata = dict(self.connection.execute("SELECT key, value FROM metadata"))
            fingerprint, dimension = embedding_fingerprint(embeddings)
            if metadata.get("embedding_fingerprint") != fingerprint or metadata.get(
                "embedding_dimension"
            ) != str(dimension):
                raise RuntimeError(
                    "The active v4 index uses a different embedding configuration. Rebuild it."
                )
            self.table = (
                require_lancedb().connect(self.revision_path / "vectors").open_table("chunks")
            )
        except Exception:
            connection = getattr(self, "connection", None)
            if connection is not None:
                connection.close()
            self.lease.close()
            raise

    def close(self) -> None:
        try:
            self.connection.close()
        finally:
            lease = getattr(self, "lease", None)
            if lease is not None:
                lease.close()

    def invoke(self, query: str, k: int = 10) -> list[Document]:
        """Return hybrid results using reciprocal-rank fusion."""
        if not query.strip():
            return []
        candidates = max(k * 5, 25)
        lexical = self._lexical_search(query, candidates)
        vector = self._vector_search(query, candidates)
        chunk_ids = list(dict.fromkeys([*lexical, *vector]))
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = {
            row[0]: row
            for row in self.connection.execute(
                f"SELECT chunk_id, note_path, ordinal, text FROM chunks "
                f"WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )
        }

        source_scores: defaultdict[str, float] = defaultdict(float)
        for ranked_ids in (lexical, vector):
            seen_sources = set()
            source_rank = 0
            for chunk_id in ranked_ids:
                row = rows.get(chunk_id)
                if row is None or row[1] in seen_sources:
                    continue
                seen_sources.add(row[1])
                source_rank += 1
                source_scores[row[1]] += 1.0 / (RRF_CONSTANT + source_rank)

        source_candidates = sorted(
            source_scores, key=lambda source: (-source_scores[source], source)
        )[:k]
        fallback_rows = {}
        for chunk_id in chunk_ids:
            row = rows.get(chunk_id)
            if row is not None and row[1] not in fallback_rows:
                fallback_rows[row[1]] = row

        documents = []
        for source in source_candidates:
            lexical_row = self._best_lexical_chunk(query, source)
            row = lexical_row or fallback_rows[source]
            lexical_score = max(0.0, -float(lexical_row[4])) if lexical_row else 0.0
            documents.append(
                Document(
                    page_content=row[3],
                    metadata={
                        "chunk_id": row[0],
                        "source": row[1],
                        "ordinal": row[2],
                        "score": source_scores[source],
                        "lexical_score": lexical_score,
                        "retrieval_type": "hybrid-source+lexical-chunk",
                    },
                )
            )
        return documents

    def _lexical_search(self, query: str, limit: int) -> list[str]:
        terms = re.findall(r"\w+", query, flags=re.UNICODE)
        if not terms:
            return []
        expression = " OR ".join(f'"{term}"' for term in terms)
        rows = self.connection.execute(
            "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? "
            "ORDER BY bm25(chunks_fts), chunk_id LIMIT ?",
            (expression, limit),
        )
        return [row[0] for row in rows]

    def _best_lexical_chunk(self, query: str, source: str):
        terms = re.findall(r"\w+", query, flags=re.UNICODE)
        if not terms:
            return None
        expression = "text : (" + " OR ".join(f'"{term}"' for term in terms) + ")"
        return self.connection.execute(
            "SELECT c.chunk_id, c.note_path, c.ordinal, c.text, bm25(chunks_fts) "
            "FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id "
            "WHERE chunks_fts MATCH ? AND c.note_path = ? "
            "ORDER BY bm25(chunks_fts), c.ordinal, c.chunk_id LIMIT 1",
            (expression, source),
        ).fetchone()

    def _vector_search(self, query: str, limit: int) -> list[str]:
        if self.table.count_rows() == 0:
            return []
        vector = self.embeddings.embed_query(query)
        query_builder = self.table.search(vector).distance_type("cosine").limit(limit)
        return [row["chunk_id"] for row in query_builder.to_list()]
