# ObsidianRAG 4 Copilot Instructions

ObsidianRAG is a monorepo with a Python FastAPI backend and a TypeScript Obsidian plugin.

## Architecture

- `backend/obsidianrag/api/server.py`: API 4 and refcounted query runtime
- `backend/obsidianrag/v4/index.py`: copy-on-write SQLite FTS5 + LanceDB revisions
- `backend/obsidianrag/v4/retrieval.py`: hybrid and lexical retrieval
- `backend/obsidianrag/core/query_pipeline.py`: grounded retrieval/generation pipeline
- `backend/obsidianrag/core/llm_provider.py`: Ollama, LM Studio, and compatible providers
- `plugin/src/main.ts`: plugin UI, backend process management, API client, and index lifecycle

The plugin accepts only API 4. The backend does not index at startup. Users explicitly Build, Refresh, Full rebuild, or Prune.

## Commands

Backend:

```bash
cd backend
uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

Plugin:

```bash
cd plugin
pnpm install --frozen-lockfile
pnpm test
pnpm run lint
pnpm run build
```

## Rules

- Do not reintroduce API 3, Chroma, LangGraph, reranker, or engine selectors.
- Do not follow links while scanning vault content.
- Preserve copy-on-write activation and reader leases.
- Blocking retrieval/index work must stay off the event loop.
- Cancellation must not release a revision while its worker thread still runs.
- Plugin process startup must use `spawn(executable, args, {shell: false})`.
- Plugin UI text uses sentence case.
- Tests use temporary/sample vaults and mocked providers.
- Backend and plugin release metadata use the same version, but tags remain separate.
