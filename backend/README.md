# ObsidianRAG Backend

[![PyPI version](https://badge.fury.io/py/obsidianrag.svg)](https://badge.fury.io/py/obsidianrag)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The Python backend for ObsidianRAG - a RAG system for querying Obsidian notes using LangGraph and local LLMs.

## Installation

### For Users (via Obsidian Plugin)

The plugin handles installation automatically. If you need to install manually:

```bash
pip install obsidianrag
```

### For Developers

We use [uv](https://docs.astral.sh/uv/) for fast, reliable dependency management:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone https://github.com/Vasallo94/ObsidianRAG.git
cd ObsidianRAG/backend

# Install dependencies (creates virtual environment automatically)
uv sync

# Install with dev dependencies
uv sync --dev

# Run commands via uv
uv run obsidianrag serve --vault /path/to/vault
uv run pytest tests/ -v
```

## Quick Start

### As a CLI

```bash
# Start the server
obsidianrag serve --vault /path/to/your/vault

# Index/reindex the vault
obsidianrag index --vault /path/to/your/vault

# Check status
obsidianrag status

# Ask a question directly
obsidianrag ask "What are my notes about Python?"
```

### As a Library

```python
from obsidianrag import ObsidianRAG

# Initialize with your vault path
rag = ObsidianRAG(vault_path="/path/to/your/vault")

# Ask questions
answer, sources = rag.ask("What are my notes about Python?")
print(answer)

# Get vault stats
stats = rag.get_stats()
print(f"Total notes: {stats['total_notes']}")
```

## Requirements

- Python 3.11+
- [Ollama](https://ollama.ai/) running locally with at least one LLM model

## Configuration

Environment variables (prefix with `OBSIDIANRAG_` for settings):

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSIDIAN_PATH` | - | Path to your Obsidian vault |
| `LLM_MODEL` | `gemma3` | Ollama model to use |
| `EMBEDDING_PROVIDER` | `huggingface` | `huggingface` or `ollama` |
| `USE_RERANKER` | `true` | Enable CrossEncoder reranking |
| `CHUNK_SIZE` | `1500` | Text chunk size for indexing |

## API Endpoints

When running the server:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ask` | POST | Ask a question, returns answer + sources |
| `/health` | GET | System status, model info |
| `/stats` | GET | Vault statistics |
| `/rebuild_db` | POST | Force reindex all notes |

## Development

```bash
cd backend

# Run tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=obsidianrag --cov-report=html

# Lint and format
uv run ruff check obsidianrag/ tests/
uv run ruff format obsidianrag/ tests/

# Build package
uv build
```

## License

MIT
