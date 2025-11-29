# ObsidianRAG v3 - Copilot Instructions

## Project Overview

ObsidianRAG is a RAG (Retrieval-Augmented Generation) system for querying Obsidian notes. Version 3 restructures it as:
- **Backend**: Python package (`obsidianrag`) distributed via PyPI with CLI
- **Frontend**: TypeScript Obsidian plugin (planned)

## Repository Structure

```
ObsidianRAG/
├── backend/                    # Python backend (PyPI package)
│   ├── obsidianrag/           # Main package
│   │   ├── __init__.py        # Package exports, version
│   │   ├── __main__.py        # python -m obsidianrag entry
│   │   ├── config.py          # Pydantic Settings
│   │   ├── api/server.py      # FastAPI server
│   │   ├── cli/main.py        # Typer CLI
│   │   └── core/              # Business logic
│   │       ├── db_service.py      # ChromaDB management
│   │       ├── qa_agent.py        # LangGraph RAG agent
│   │       ├── qa_service.py      # Hybrid retriever
│   │       └── metadata_tracker.py # Incremental indexing
│   ├── tests/                 # pytest tests
│   ├── pyproject.toml         # Package config
│   └── uv.lock
├── plugin/                    # Obsidian plugin (TypeScript) - PLANNED
├── docs/                      # Documentation - PLANNED
├── .github/
│   ├── workflows/             # CI/CD
│   └── instructions/          # Development guidelines
└── V3_MIGRATION_PLAN.md       # Full migration plan
```

## Quick Reference

### Run Commands (from `backend/`)
```bash
uv run obsidianrag serve --vault-path /path/to/vault  # Start server
uv run obsidianrag index --vault-path /path/to/vault  # Index vault
uv run obsidianrag status --vault-path /path/to/vault # Check status
uv run obsidianrag ask --vault-path /path "question"  # CLI query
uv run pytest tests/ -v                                # Run tests
uv run ruff check obsidianrag/ tests/                 # Lint
uv run ruff format obsidianrag/ tests/                # Format
```

### Key Technologies
- **Python**: 3.11+ with uv for dependency management
- **LLM**: Ollama (local) with langchain-ollama
- **Embeddings**: HuggingFace sentence-transformers
- **Vector DB**: ChromaDB (persistent)
- **Reranker**: BAAI/bge-reranker-v2-m3
- **API**: FastAPI with uvicorn
- **CLI**: Typer with Rich
- **Tests**: pytest with pytest-asyncio, pytest-cov

### API Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/ask` | POST | Ask question (JSON: `{"question": "..."}`) |
| `/stats` | GET | Vault statistics |
| `/rebuild_db` | POST | Force reindex |

## Development Guidelines

📚 **See detailed instructions in `.github/instructions/`:**

| File | Topics |
|------|--------|
| [python-backend.md](instructions/python-backend.md) | Python code style, patterns, imports, error handling |
| [testing.md](instructions/testing.md) | pytest fixtures, mocking, coverage, test patterns |
| [obsidian-plugin.md](instructions/obsidian-plugin.md) | TypeScript plugin structure, Obsidian API, UI components |
| [rag-patterns.md](instructions/rag-patterns.md) | LangGraph, hybrid search, reranking, GraphRAG |
| [ci-cd.md](instructions/ci-cd.md) | GitHub Actions, releases, PyPI publishing |

## Data Flow

```
Question → Retrieve (hybrid search) → Rerank → GraphRAG expansion → Generate (LLM) → Answer
```

## Configuration

All settings via Pydantic `BaseSettings` in `config.py`:
- Environment variables with `OBSIDIANRAG_` prefix
- `.env` file support
- CLI arguments override environment

### Key Settings
| Setting | Default | Purpose |
|---------|---------|---------|
| `llm_model` | gemma3 | Ollama model name |
| `use_reranker` | true | Enable CrossEncoder reranking |
| `reranker_top_n` | 6 | Docs after reranking |
| `retrieval_k` | 12 | Docs before reranking |
| `chunk_size` | 1500 | Text chunk size |
| `bm25_weight` | 0.4 | BM25 weight in hybrid search |
| `vector_weight` | 0.6 | Vector weight in hybrid search |

## Phase Status (v3 Migration)

- ✅ Phase 0: Planning & Issues
- ✅ Phase 1: Backend restructure
- 🔄 Phase 2: Testing (in progress)
- ⏳ Phase 3: Obsidian Plugin
- ⏳ Phase 4: Integration
- ⏳ Phase 5: Polish
- ⏳ Phase 6: Documentation
- ⏳ Phase 7: Release

See `V3_MIGRATION_PLAN.md` and GitHub Issues #20-#28 for details.
