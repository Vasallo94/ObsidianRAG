# ObsidianRAG Backend

The Python backend for ObsidianRAG - a RAG system for querying Obsidian notes using LangGraph and local LLMs.

## Installation

```bash
pip install obsidianrag
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

Environment variables:
- `OBSIDIAN_PATH`: Path to your Obsidian vault
- `LLM_MODEL`: Ollama model to use (default: `gemma3`)
- `EMBEDDING_PROVIDER`: `huggingface` or `ollama` (default: `huggingface`)

## API Endpoints

When running the server:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ask` | POST | Ask a question, returns answer + sources |
| `/health` | GET | System status, model info |
| `/stats` | GET | Vault statistics |
| `/rebuild_db` | POST | Force reindex all notes |

## License

MIT
