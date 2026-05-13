# LangChain Classic Migration Plan

ObsidianRAG currently uses `langchain_classic` for legacy retriever composition:

- `EnsembleRetriever`
- `ContextualCompressionRetriever`
- `CrossEncoderReranker`

This works, but LangChain v1 moved these pieces into `langchain-classic` as a
compatibility package for legacy chains, retrievers, indexing APIs, and hub
functionality. New development should avoid adding more dependency on
`langchain_classic`.

## Decision

Keep the current implementation patched and supported short term, but migrate
retrieval and reranking to first-party ObsidianRAG code or modern, narrow
libraries.

Do not move this logic into `obsidian-mcp-server`. The MCP should remain a
client/orchestrator for ObsidianRAG, not a second embedded RAG stack.

## Current Dependency Surface

The active imports are in `backend/obsidianrag/core/qa_service.py`:

```python
from langchain_classic.retrievers import ContextualCompressionRetriever, EnsembleRetriever
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
```

The surrounding non-classic pieces are still useful:

- `langchain_core.documents.Document`
- `langchain_community.retrievers.BM25Retriever`
- `langchain_community.cross_encoders.HuggingFaceCrossEncoder`
- Chroma vector store integration
- LangGraph orchestration

## Target Architecture

Replace classic retriever orchestration with explicit components:

1. BM25 retrieval
   - Prefer `rank-bm25` or a small local wrapper.
   - Input: indexed chunks and metadata from Chroma or the metadata tracker.
   - Output: scored `Document` candidates.

2. Vector retrieval
   - Query Chroma directly or through the minimal vector store API already used
     by the backend.
   - Output: scored `Document` candidates.

3. Fusion
   - Implement reciprocal rank fusion or weighted score merge.
   - Preserve source metadata and deterministic ordering.
   - Make weights configurable using the existing `bm25_weight` and
     `vector_weight` settings.

4. Reranking
   - Use a cross-encoder directly.
   - Input: query plus fused candidates.
   - Output: top `reranker_top_n` documents.
   - Keep reranking optional and fail open to fused retrieval when the model is
     unavailable.

5. Retrieval interface
   - Expose a small internal function or class with `.retrieve(query)`.
   - Keep `retrieve_with_links()` compatible with returned `Document` objects.

## Migration Steps

1. Add tests around current retrieval behavior:
   - empty database handling;
   - BM25-only candidate ordering;
   - vector-only fallback;
   - fused retrieval deduplication;
   - reranker fail-open behavior;
   - metadata preservation.

2. Implement a local fusion module:
   - `backend/obsidianrag/core/retrieval/fusion.py`
   - pure functions, no model dependencies;
   - deterministic unit tests.

3. Implement a local reranker adapter:
   - `backend/obsidianrag/core/retrieval/reranker.py`
   - direct cross-encoder call;
   - no `ContextualCompressionRetriever`.

4. Replace `create_hybrid_retriever()` internals:
   - keep the public function stable at first;
   - return a lightweight object with `.invoke(query)` if that minimizes caller
     churn.

5. Remove `langchain_classic` imports from `qa_service.py`.

6. Remove `langchain-classic` from backend dependencies once tests pass.

7. Run:

```bash
uv run pytest
uv run ruff check obsidianrag tests
uv run pip-audit
```

## Non-goals

- Do not rewrite ObsidianRAG as a LangChain v1 agent only to replace retrievers.
- Do not add LangChain agent middleware unless ObsidianRAG grows a separate
  agentic research workflow.
- Do not reintroduce an embedded RAG stack inside `obsidian-mcp-server`.

## Future Agentic Layer

LangChain v1 middleware may be useful later for a higher-level research agent:

- dynamic tool selection;
- summarization;
- human-in-the-loop checkpoints;
- PII handling;
- model-call retries.

That should be a separate ObsidianRAG feature above retrieval, not a dependency
of the core retrieval path.
