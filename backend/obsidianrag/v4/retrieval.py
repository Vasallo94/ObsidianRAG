"""Experimental hybrid retrieval over SQLite FTS5 and LanceDB."""

import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from obsidianrag.v4.index import active_revision, embedding_signature, require_lancedb

RRF_CONSTANT = 60


class ExperimentalLexicalRetriever:
    """Retrieve chunks from the authoritative SQLite FTS5 catalog without embeddings."""

    def __init__(self, vault_path: Path):
        self.revision_path = active_revision(vault_path.resolve())
        self.connection = sqlite3.connect(
            f"file:{self.revision_path / 'catalog.sqlite3'}?mode=ro", uri=True
        )

    def close(self) -> None:
        self.connection.close()

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
        self.connection = sqlite3.connect(
            f"file:{self.revision_path / 'catalog.sqlite3'}?mode=ro", uri=True
        )
        metadata = dict(self.connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("embedding_signature") != embedding_signature():
            raise RuntimeError(
                "The active v4 index uses a different embedding configuration. Rebuild it."
            )
        self.table = require_lancedb().connect(self.revision_path / "vectors").open_table("chunks")

    def close(self) -> None:
        self.connection.close()

    def invoke(self, query: str, k: int = 10) -> list[Document]:
        """Return hybrid results using reciprocal-rank fusion."""
        if not query.strip():
            return []
        candidates = max(k * 5, 25)
        lexical = self._lexical_search(query, candidates)
        vector = self._vector_search(query, candidates)
        scores: defaultdict[str, float] = defaultdict(float)
        channels: defaultdict[str, set[str]] = defaultdict(set)

        for channel, ranked_ids in (("lexical", lexical), ("vector", vector)):
            for rank, chunk_id in enumerate(ranked_ids, 1):
                scores[chunk_id] += 1.0 / (RRF_CONSTANT + rank)
                channels[chunk_id].add(channel)

        ranked = sorted(scores, key=scores.__getitem__, reverse=True)
        if not ranked:
            return []
        placeholders = ",".join("?" for _ in ranked)
        rows = {
            row[0]: row
            for row in self.connection.execute(
                f"SELECT chunk_id, note_path, ordinal, text FROM chunks "
                f"WHERE chunk_id IN ({placeholders})",
                ranked,
            )
        }
        source_candidates = []
        fallback_rows = {}
        source_scores = {}
        for chunk_id in ranked:
            row = rows.get(chunk_id)
            if row is None or row[1] in fallback_rows:
                continue
            source_candidates.append(row[1])
            fallback_rows[row[1]] = row
            source_scores[row[1]] = scores[chunk_id]
            if len(source_candidates) == k:
                break

        documents = []
        for source in source_candidates:
            row = self._best_lexical_chunk(query, source) or fallback_rows[source]
            documents.append(
                Document(
                    page_content=row[3],
                    metadata={
                        "chunk_id": row[0],
                        "source": row[1],
                        "ordinal": row[2],
                        "score": source_scores[source],
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
            "ORDER BY bm25(chunks_fts) LIMIT ?",
            (expression, limit),
        )
        return [row[0] for row in rows]

    def _best_lexical_chunk(self, query: str, source: str):
        terms = re.findall(r"\w+", query, flags=re.UNICODE)
        if not terms:
            return None
        expression = " OR ".join(f'"{term}"' for term in terms)
        return self.connection.execute(
            "SELECT c.chunk_id, c.note_path, c.ordinal, c.text "
            "FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id "
            "WHERE chunks_fts MATCH ? AND c.note_path = ? "
            "ORDER BY bm25(chunks_fts) LIMIT 1",
            (expression, source),
        ).fetchone()

    def _vector_search(self, query: str, limit: int) -> list[str]:
        vector = self.embeddings.embed_query(query)
        query_builder = self.table.search(vector).distance_type("cosine").limit(limit)
        return [row["chunk_id"] for row in query_builder.to_list()]
