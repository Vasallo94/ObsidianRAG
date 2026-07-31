"""Experimental hybrid retrieval over SQLite FTS5 and LanceDB."""

import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from obsidianrag.v4.index import active_revision, embedding_signature, require_lancedb

RRF_CONSTANT = 60


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

        ranked = sorted(scores, key=scores.__getitem__, reverse=True)[:k]
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
        return [
            Document(
                page_content=rows[chunk_id][3],
                metadata={
                    "chunk_id": chunk_id,
                    "source": rows[chunk_id][1],
                    "ordinal": rows[chunk_id][2],
                    "score": scores[chunk_id],
                    "retrieval_type": "+".join(sorted(channels[chunk_id])),
                },
            )
            for chunk_id in ranked
            if chunk_id in rows
        ]

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

    def _vector_search(self, query: str, limit: int) -> list[str]:
        vector = self.embeddings.embed_query(query)
        query_builder = self.table.search(vector).distance_type("cosine").limit(limit)
        return [row["chunk_id"] for row in query_builder.to_list()]
