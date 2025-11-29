# Python Backend Development Guidelines

> Instructions for developing the ObsidianRAG Python backend (`backend/obsidianrag/`)

## Code Style & Standards

### General Rules
- **Python version**: 3.11+ required
- **Formatter**: `ruff format` (line length 88)
- **Linter**: `ruff check` with auto-fix
- **Type hints**: Required for all public functions
- **Docstrings**: Google style for all public classes/functions

### Example Function
```python
def retrieve_documents(
    query: str,
    k: int = 10,
    filters: dict[str, Any] | None = None,
) -> list[Document]:
    """Retrieve relevant documents for a query.
    
    Args:
        query: The search query text.
        k: Maximum number of documents to return.
        filters: Optional metadata filters.
    
    Returns:
        List of Document objects sorted by relevance.
    
    Raises:
        ValueError: If query is empty.
        ConnectionError: If vector DB is unavailable.
    """
    if not query.strip():
        raise ValueError("Query cannot be empty")
    ...
```

## Project Structure

### Package Layout
```
backend/
├── obsidianrag/
│   ├── __init__.py         # Exports: __version__, configure_from_vault
│   ├── __main__.py         # Entry: python -m obsidianrag
│   ├── config.py           # Settings class (Pydantic BaseSettings)
│   ├── api/
│   │   ├── __init__.py
│   │   └── server.py       # FastAPI app, endpoints, lifespan
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py         # Typer CLI commands
│   ├── core/
│   │   ├── __init__.py     # Export core classes
│   │   ├── db_service.py   # ChromaDB operations
│   │   ├── qa_agent.py     # LangGraph agent
│   │   ├── qa_service.py   # Hybrid retriever
│   │   ├── metadata_tracker.py  # File change detection
│   │   └── rag.py          # High-level RAG interface
│   └── utils/
│       ├── __init__.py
│       └── logger.py       # Logging configuration
├── tests/                  # See testing.md
├── scripts/                # Debug utilities
├── pyproject.toml
└── uv.lock
```

### Import Conventions
```python
# Standard library first
import json
import logging
from pathlib import Path
from typing import Any

# Third-party packages
import chromadb
from fastapi import FastAPI, HTTPException
from langchain_core.documents import Document
from pydantic import BaseModel

# Local imports (absolute from package root)
from obsidianrag.config import settings, configure_from_vault
from obsidianrag.core.db_service import DBService
from obsidianrag.utils.logger import get_logger
```

## Key Patterns

### Configuration with Pydantic Settings
```python
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OBSIDIANRAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Required
    obsidian_path: str = ""
    
    # With defaults
    llm_model: str = "gemma3"
    chunk_size: int = 1500
    use_reranker: bool = True
    
    @property
    def db_path(self) -> str:
        return str(Path(self.obsidian_path) / ".obsidianrag" / "db")

# Global singleton
settings = Settings()

def configure_from_vault(vault_path: str) -> Settings:
    """Reconfigure settings for a specific vault."""
    global settings
    settings = Settings(obsidian_path=vault_path)
    return settings
```

### FastAPI with Lifespan
```python
# api/server.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # Startup
    logger.info("Starting ObsidianRAG...")
    app.state.db = DBService()
    app.state.agent = create_qa_agent(app.state.db)
    yield
    # Shutdown
    logger.info("Shutting down...")

app = FastAPI(
    title="ObsidianRAG API",
    version="3.0.0",
    lifespan=lifespan,
)
```

### Typer CLI Commands
```python
# cli/main.py
import typer
from rich.console import Console

app = typer.Typer(
    name="obsidianrag",
    help="RAG system for Obsidian notes",
    no_args_is_help=True,
)
console = Console()

@app.command()
def serve(
    vault_path: str = typer.Option(..., "--vault-path", "-v", help="Path to Obsidian vault"),
    port: int = typer.Option(8000, "--port", "-p"),
    host: str = typer.Option("127.0.0.1", "--host"),
):
    """Start the ObsidianRAG API server."""
    configure_from_vault(vault_path)
    console.print(f"[green]Starting server on {host}:{port}[/green]")
    run_server(host=host, port=port)
```

### LangGraph Agent Pattern
```python
# core/qa_agent.py
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """State that flows through the agent graph."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: list[Document]
    question: str
    answer: str

def create_qa_agent(db: DBService) -> StateGraph:
    """Create the LangGraph QA agent."""
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("retrieve", lambda s: retrieve_node(s, db))
    graph.add_node("generate", lambda s: generate_node(s))
    
    # Add edges
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    
    return graph.compile()
```

### Error Handling
```python
# Use specific exceptions
class ObsidianRAGError(Exception):
    """Base exception for ObsidianRAG."""
    pass

class VaultNotFoundError(ObsidianRAGError):
    """Vault path does not exist."""
    pass

class OllamaConnectionError(ObsidianRAGError):
    """Cannot connect to Ollama."""
    pass

# In API endpoints
@app.post("/ask")
async def ask(request: AskRequest):
    try:
        result = app.state.agent.invoke({"question": request.question})
        return {"answer": result["answer"], "sources": result["sources"]}
    except OllamaConnectionError:
        raise HTTPException(503, "Ollama is not available")
    except Exception as e:
        logger.exception("Error processing question")
        raise HTTPException(500, str(e))
```

### Logging
```python
# utils/logger.py
import logging
import sys

def get_logger(name: str) -> logging.Logger:
    """Get a configured logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(levelname)s - %(name)s - %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

# Usage in modules
logger = get_logger(__name__)
```

## Dependencies

### Adding New Dependencies
```bash
# Add to pyproject.toml and lock
cd backend
uv add package-name

# Dev dependency
uv add --dev pytest-something
```

### Key Dependencies
| Package | Purpose |
|---------|---------|
| `langchain-core` | Base LangChain interfaces |
| `langchain-ollama` | Ollama LLM integration |
| `langchain-huggingface` | HuggingFace embeddings |
| `langgraph` | Agent graph framework |
| `chromadb` | Vector database |
| `fastapi` | API framework |
| `typer` | CLI framework |
| `pydantic-settings` | Configuration |
| `sentence-transformers` | Embedding models |

## Common Tasks

### Add New API Endpoint
1. Define request/response models in `api/server.py`
2. Add route function with proper error handling
3. Add test in `tests/test_server.py`

### Add New CLI Command
1. Add function with `@app.command()` in `cli/main.py`
2. Use `typer.Option()` for optional args
3. Use `console.print()` with Rich formatting
4. Add test in `tests/test_cli.py`

### Modify RAG Pipeline
1. Update `AgentState` if new state is needed
2. Add/modify nodes in `qa_agent.py`
3. Update graph edges
4. Add tests for new behavior

## Before Committing

```bash
cd backend

# Format code
uv run ruff format obsidianrag/ tests/

# Check linting
uv run ruff check obsidianrag/ tests/ --fix

# Run tests (skip slow ones for quick check)
uv run pytest tests/ -m "not slow" -v

# Verify package builds
uv build
```
