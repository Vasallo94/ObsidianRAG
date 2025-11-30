# ObsidianRAG Backend

Python backend providing RAG (Retrieval-Augmented Generation) capabilities for Obsidian vaults.

[![PyPI](https://img.shields.io/badge/PyPI-obsidianrag-blue)](https://pypi.org/project/obsidianrag/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-77%20passing-brightgreen)](https://github.com/Vasallo94/ObsidianRAG/actions)

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
```

#### Index Vault

```bash
# Full rebuild
obsidianrag index --vault /path/to/vault --rebuild

# Incremental (only changed notes)
obsidianrag index --vault /path/to/vault
```

#### Check Status

```bash
obsidianrag status --vault /path/to/vault
```

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
LLM_MODEL=gemma3
OLLAMA_BASE_URL=http://localhost:11434

# Embeddings
EMBEDDING_PROVIDER=huggingface  # or 'ollama'
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# Reranker
USE_RERANKER=true
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RERANKER_TOP_N=6

# Retrieval
CHUNK_SIZE=1500
CHUNK_OVERLAP=300
RETRIEVAL_K=12
BM25_K=5
BM25_WEIGHT=0.4
VECTOR_WEIGHT=0.6

# API
API_HOST=127.0.0.1
API_PORT=8000
CORS_ORIGINS=["http://localhost:3000", "app://obsidian.md"]
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

**Total**: 77 tests, 42% coverage

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
