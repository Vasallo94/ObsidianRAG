# ObsidianRAG

Monorepo with two independent components:

- **`backend/`** -- Python package (PyPI: `obsidianrag`). FastAPI server, LangGraph RAG agent, ChromaDB vector store.
- **`plugin/`** -- Obsidian plugin (TypeScript). Chat UI that talks to the backend over HTTP.

## Commands

### Backend (Python, managed with `uv`)

```bash
cd backend
uv sync                    # install deps
uv run pytest              # run tests (89 tests)
uv run pytest --cov        # with coverage
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy obsidianrag    # type check
uv run obsidianrag serve --vault /path/to/vault  # run server
```

### Plugin (TypeScript, managed with `pnpm`)

```bash
cd plugin
pnpm install               # install deps
pnpm run build             # compile (tsc + esbuild)
pnpm run dev               # watch mode
pnpm test                  # jest tests
pnpm run lint              # eslint
```

### Docker

```bash
OBSIDIAN_VAULT_PATH=/path/to/vault docker compose up
```

## Architecture

```
Plugin (TypeScript) --HTTP:8000--> Backend (FastAPI)
                                     |
                              LangGraph Agent
                           Retrieve -> Rerank -> Generate
                                     |
                              ChromaDB + BM25
                                     |
                           Ollama / LM Studio / Custom
```

## Conventions

- No emojis in code, logs, CLI output, or comments
- Backend: ruff for lint/format, mypy for types, pytest for tests
- Plugin: eslint with `@obsidianmd/eslint-plugin`, jest for tests
- Plugin UI text must use sentence case (Obsidian requirement, the rule `obsidianmd/ui/sentence-case` cannot be disabled)
- Commit messages: short imperative summary, body explains why
- PRs: one logical change per PR

## Key files

- `backend/obsidianrag/api/server.py` -- FastAPI app and endpoints
- `backend/obsidianrag/core/qa_agent.py` -- LangGraph RAG agent
- `backend/obsidianrag/core/qa_service.py` -- Retrieval, reranking, GraphRAG
- `backend/obsidianrag/core/llm_provider.py` -- Multi-provider LLM abstraction
- `backend/obsidianrag/config.py` -- Pydantic settings (env vars with `OBSIDIANRAG_` prefix)
- `plugin/src/main.ts` -- Entire plugin in one file (classes: Plugin, ChatView, SetupModal, SettingsTab)

## Release

- Backend: tag `backend-v*` triggers PyPI publish + Docker image push to GHCR
- Plugin: tag `plugin-v*` triggers GitHub Release with `main.js`, `manifest.json`, `styles.css`
