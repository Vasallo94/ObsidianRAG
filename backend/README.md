# ObsidianRAG Backend

Python backend providing RAG (Retrieval-Augmented Generation) capabilities for Obsidian vaults.

[![PyPI](https://img.shields.io/badge/PyPI-obsidianrag-blue)](https://pypi.org/project/obsidianrag/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-88%20passing-brightgreen)](https://github.com/Vasallo94/ObsidianRAG/actions)

---

## 🚀 Installation

### As End User

```bash
# With pip
pip install obsidianrag

# With pipx (recommended - isolated environment)
pipx install obsidianrag

# With uv (fastest)
uv tool install obsidianrag
```

### As Developer

```bash
git clone https://github.com/Vasallo94/ObsidianRAG.git
cd ObsidianRAG/backend
uv sync
```

---

## 📖 Usage

### CLI Commands

#### Start Server

```bash
# Serve with auto-detected vault
obsidianrag serve --vault /path/to/vault

# Custom port and model
obsidianrag serve --vault ~/notes --port 9000 --model qwen2.5

# LM Studio
obsidianrag serve --vault ~/notes --provider lmstudio --model my-model

# Custom OpenAI-compatible server
OBSIDIANRAG_COMPATIBLE_API_KEY=my-key \
  obsidianrag serve --vault ~/notes --provider custom \
  --base-url http://my-server:8080/v1 \
  --api-format chat-completions
```

#### Index Vault

```bash
# Full rebuild
obsidianrag index --vault /path/to/vault --force

# Incremental (only changed notes)
obsidianrag index --vault /path/to/vault
```

#### Check Status

```bash
obsidianrag status --vault /path/to/vault
```

#### Evaluate Retrieval

Create a dataset with questions and the source notes that retrieval should find:

```json
{
  "cases": [
    {
      "question": "Where is the deployment procedure?",
      "expected_sources": ["Operations/Deployment.md"]
    }
  ]
}
```

Run retrieval without calling an LLM:

```bash
obsidianrag evaluate evaluation.json --vault /path/to/vault --k 10
obsidianrag evaluate evaluation.json --vault /path/to/vault --reranker --output results.json
```

The command reports source Precision@k, Recall@k, hit rate, MRR, MAP@k, nDCG@k, evidence recall, deterministic 95% bootstrap confidence intervals, and mean/p50/p95 retrieval latency. Add optional `relevance_grades` entries (`source` plus a positive numeric `grade`) to dataset cases for graded nDCG; expected sources without an explicit grade default to relevance 1. Cases with `supporting_evidence` also measure whether the retrieved chunk contains the cited ground-truth passage, rather than merely matching the correct note.

Compare two saved runs without loading an embedding model:

```bash
obsidianrag compare-evaluations v3-results.json v4-results.json --output comparison.json
```

The comparison pairs cases by question and reports baseline, candidate, delta, paired 95% bootstrap interval, and improved/regressed query counts for every retrieval metric.

Evaluate grounded answers through any external JSON stdin/stdout agent command. This uses SQLite FTS5 for retrieval and does not load an embedding model:

```bash
uv run obsidianrag evaluate-agent private-ground-truth.json \
  --vault /path/to/vault \
  --generator-command "python -m obsidianrag.pi_agent_adapter" \
  --judge-command "python -m obsidianrag.pi_agent_adapter" \
  --allow-private-data \
  --output agent-results.json
```

`--allow-private-data` is mandatory because questions, retrieved note chunks, candidate answers, required facts, and supporting evidence are passed to the external commands, which may call a remote provider. The bundled Pi adapter defaults to `openai-codex/gpt-5.6-luna`; override it with `OBSIDIANRAG_PI_MODEL`.

#### Experimental v4 Retrieval

Install the optional embedded LanceDB backend, build an isolated index revision, and compare it with v3:

```bash
pip install 'obsidianrag[v4]'
obsidianrag v4-index --vault /path/to/vault
obsidianrag v4-index --vault /path/to/vault --full-rebuild  # after incompatible settings
obsidianrag v4-prune --vault /path/to/vault                 # remove unleased revisions
obsidianrag v4-search "deployment rollback" --vault /path/to/vault
obsidianrag v4-search "deployment rollback" --vault /path/to/vault --lexical-only
obsidianrag ask "How do I roll back a deployment?" --vault /path/to/vault --engine v4
obsidianrag ask "How do I roll back a deployment?" --vault /path/to/vault --engine v4-fts
obsidianrag evaluate evaluation.json --vault /path/to/vault --engine v4 --k 10
obsidianrag evaluate evaluation.json --vault /path/to/vault --engine v4-fts --k 10
```

Experimental indexes live under `.obsidianrag/v4` and do not modify the v3 Chroma index. Builds scan regular vault Markdown files without following links and create a copy-on-write revision: unchanged vectors are reused in bounded batches, changed notes are re-embedded, and deleted notes are omitted. Empty vaults activate a valid empty revision.

SQLite integrity, foreign keys, deterministic IDs, catalog/FTS semantics, and LanceDB paths, dimensions, and finite vectors are validated before atomically switching the active manifest. Synthetic embedding fingerprints prevent reuse across different vector spaces; incompatible schema, embedding, or chunk settings require `--full-rebuild`. Readers lease their revision so `v4-prune` refuses in-use data and deletes only inactive revisions after readers close. Hybrid retrieval ranks unique sources with vector/lexical fusion and then selects each source's strongest lexical chunk, avoiding a correct note paired with an irrelevant chunk. Before generation, the query pipeline keeps scored sources whose lexical relevance is at least 70% of the leading source; unscored vector fallbacks and top-k results without positive lexical scores are retained conservatively. Semicolon-separated multipart questions support up to four explicit parts, retrieve each part independently, interleave their ranked sources, and apply the relevance threshold within each part so one dominant topic cannot hide the others. For `v4-fts` generation, the leading source for each retrieval part may preserve a second strong lexical passage from the same note, improving evidence coverage without expanding arbitrary adjacent chunks. The v4 query pipeline uses one provider-neutral prompt and history path for complete and streaming generation, treats note text as untrusted data, asks the model to preserve supported concrete details or abstain when evidence is insufficient, and accepts only valid numeric citations from the retrieved context. The `v4-fts` engine and `--lexical-only` search use the SQLite catalog without loading an embedding model; building or refreshing the index still requires embeddings.

#### Ask Question (CLI)

```bash
obsidianrag ask --vault /path/to/vault "What notes do I have about Python?"
```

---

## 🔌 API

### Start Server

```python
from obsidianrag.api.server import run_server

run_server(vault_path="/path/to/vault", host="0.0.0.0", port=8000)
```

### Endpoints

#### `POST /ask`

Ask a question about your notes.

**Request**:
```json
{
  "text": "What notes do I have about Python?",
  "session_id": "optional-session-id"
}
```

**Response**:
```json
{
  "question": "What notes do I have about Python?",
  "result": "According to your notes...",
  "sources": [
    {
      "source": "Programming/Python.md",
      "score": 0.92,
      "retrieval_type": "retrieved"
    }
  ],
  "text_blocks": ["..."],
  "process_time": 2.5,
  "session_id": "abc123"
}
```

#### `POST /ask/stream`

Same as `/ask` but streams response via Server-Sent Events (SSE).

**Events**:
- `start` - Request started
- `status` - Progress update
- `retrieve_complete` - Documents retrieved
- `token` - LLM token (streamed)
- `answer` - Final answer
- `done` - Stream complete
- `error` - Error occurred

#### `GET /health`

Check server status.

**Response**:
```json
{
  "status": "ok",
  "model": "gemma3",
  "embedding_provider": "huggingface",
  "embedding_model": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
  "db_ready": true
}
```

#### `GET /stats`

Get vault statistics.

**Response**:
```json
{
  "total_notes": 150,
  "total_chunks": 450,
  "total_words": 25000,
  "total_chars": 150000,
  "avg_words_per_chunk": 55,
  "folders": 12,
  "internal_links": 350,
  "vault_path": "MyVault"
}
```

#### `POST /rebuild_db`

Force full database rebuild.

---

## ⚙️ Configuration

### Environment Variables

Create `~/.config/obsidianrag/.env`:

```env
# LLM
OBSIDIANRAG_LLM_MODEL=gemma3
OBSIDIANRAG_LLM_TEMPERATURE=0
OBSIDIANRAG_OLLAMA_BASE_URL=http://localhost:11434

# Embeddings
OBSIDIANRAG_EMBEDDING_PROVIDER=huggingface  # or 'ollama'
OBSIDIANRAG_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
OBSIDIANRAG_OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# Reranker
OBSIDIANRAG_USE_RERANKER=true
OBSIDIANRAG_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
OBSIDIANRAG_RERANKER_TOP_N=6

# Retrieval
OBSIDIANRAG_CHUNK_SIZE=1500
OBSIDIANRAG_CHUNK_OVERLAP=300
OBSIDIANRAG_RETRIEVAL_K=12
OBSIDIANRAG_BM25_K=5
OBSIDIANRAG_BM25_WEIGHT=0.4
OBSIDIANRAG_VECTOR_WEIGHT=0.6

# API
OBSIDIANRAG_API_HOST=127.0.0.1
OBSIDIANRAG_API_PORT=8000
OBSIDIANRAG_CORS_ORIGINS=["http://localhost:3000", "app://obsidian.md"]
```

### Programmatic Configuration

```python
from obsidianrag.config import Settings, configure_from_vault

# Auto-configure from vault
configure_from_vault("/path/to/vault")

# Manual configuration
settings = Settings(
    obsidian_path="/path/to/vault",
    llm_model="qwen2.5",
    use_reranker=True,
    retrieval_k=15
)
```

---

## 🏗️ Architecture

### Core Components

```
obsidianrag/
├── api/
│   └── server.py         # FastAPI server
├── cli/
│   └── main.py           # CLI commands (Typer)
├── core/
│   ├── qa_agent.py       # LangGraph RAG agent
│   ├── qa_service.py     # Hybrid retriever + reranker
│   ├── db_service.py     # ChromaDB + indexing
│   └── metadata_tracker.py  # Change detection
├── config/
│   └── __init__.py       # Pydantic settings
└── utils/
    └── logger.py         # Logging
```

### RAG Pipeline

**LangGraph Agent** (`qa_agent.py`):
```python
# Two-node graph: retrieve → generate
graph = StateGraph(AgentState)
graph.add_node("retrieve", retrieve_node)
graph.add_node("generate", generate_node)
graph.add_edge("retrieve", "generate")
```

**Hybrid Retriever** (`qa_service.py`):
1. Vector search (ChromaDB)
2. BM25 search
3. Ensemble (weighted 0.6/0.4)
4. CrossEncoder reranking
5. GraphRAG link expansion

**Database Service** (`db_service.py`):
- ChromaDB persistence
- Incremental indexing (only changed notes)
- Metadata tracking
- Link extraction from `[[wikilinks]]`

---

## 🧪 Testing

```bash
# All tests
uv run pytest

# Unit tests only (no integration, no slow)
uv run pytest -m "not integration and not slow"

# With coverage
uv run pytest --cov=obsidianrag --cov-report=html
```

**Test Structure**:
- `tests/test_cli.py` - CLI commands (14 tests)
- `tests/test_server.py` - API endpoints (14 tests)
- `tests/test_qa_agent.py` - LangGraph agent (17 tests)
- `tests/test_db_service.py` - Database (16 tests)
- `tests/test_integration.py` - E2E flows (16 tests)

**Total**: 88 tests

---

## 🔧 Development

### Setup

```bash
# Clone repo
git clone https://github.com/Vasallo94/ObsidianRAG.git
cd ObsidianRAG/backend

# Install with dev dependencies
uv sync

# Run tests
uv run pytest

# Lint and format
uv run ruff check obsidianrag/ tests/
uv run ruff format obsidianrag/ tests/
```

### Project Structure

```
backend/
├── obsidianrag/          # Main package
├── tests/                # Tests
├── pyproject.toml        # Package metadata + dependencies
├── uv.lock               # Lock file
└── pytest.ini            # Pytest configuration
```

---

## 📄 License

MIT License - see [LICENSE](../LICENSE)

---

## 🤝 Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md)
