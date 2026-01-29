"""Pytest configuration and fixtures for ObsidianRAG tests."""

import os
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ============================================================
# Test Vault Fixtures
# ============================================================


@pytest.fixture(name="mock_vault")
def mock_vault_fixt(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary mock Obsidian vault with test notes."""
    vault_path = tmp_path / "test_vault"
    vault_path.mkdir()

    # Create .obsidian folder to make it look like a vault
    (vault_path / ".obsidian").mkdir()

    # Create test notes
    notes = {
        "Python Basics.md": """# Python Basics

Python is a high-level programming language.

## Variables
Variables store data. Example:
```python
x = 10
name = "Alice"
```

## Functions
Functions are reusable code blocks.
```python
def greet(name):
    return f"Hello, {name}!"
```

Related: [[Advanced Python]], [[Data Types]]
""",
        "Advanced Python.md": """# Advanced Python

## Decorators
Decorators modify function behavior.

```python
def my_decorator(func):
    def wrapper():
        print("Before")
        func()
        print("After")
    return wrapper
```

## Generators
Generators yield values lazily.

Related: [[Python Basics]]
""",
        "Data Types.md": """# Data Types

Python has several built-in data types:
- int: integers
- float: decimals
- str: strings
- list: ordered collections
- dict: key-value pairs

See also: [[Python Basics]]
""",
        "subfolder/Nested Note.md": """# Nested Note

This is a note in a subfolder.

Links to [[Python Basics]].
""",
    }

    for filename, content in notes.items():
        filepath = vault_path / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)

    yield vault_path

    # Cleanup is handled by tmp_path fixture


@pytest.fixture
def mock_vault_with_db(mock_vault: Path) -> Generator[Path, None, None]:
    """Mock vault with a pre-created .obsidianrag directory."""
    obsidianrag_dir = mock_vault / ".obsidianrag"
    obsidianrag_dir.mkdir()
    (obsidianrag_dir / "db").mkdir()
    (obsidianrag_dir / "logs").mkdir()
    (obsidianrag_dir / "cache").mkdir()

    yield mock_vault


# ============================================================
# Settings Fixtures
# ============================================================


@pytest.fixture(name="mock_settings")
def mock_settings_fixt(mock_vault: Path):
    """Create mock settings configured for test vault."""
    from obsidianrag.config import Settings

    settings = Settings()
    settings.configure_paths(str(mock_vault))
    settings.llm_model = "gemma3"
    settings.use_reranker = False  # Disable for faster tests

    return settings


@pytest.fixture
def patched_settings(mock_settings):
    """Patch get_settings to return mock settings."""
    with patch("obsidianrag.config.get_settings", return_value=mock_settings):
        with patch("obsidianrag.config.settings", mock_settings):
            yield mock_settings


# ============================================================
# Ollama Mock Fixtures
# ============================================================


@pytest.fixture
def mock_ollama_available():
    """Mock Ollama as available with test models."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [
            {"name": "gemma3:latest"},
            {"name": "llama3.2:latest"},
            {"name": "nomic-embed-text:latest"},
        ]
    }

    with patch("httpx.get", return_value=mock_response):
        with patch("requests.get", return_value=mock_response):
            yield


@pytest.fixture
def mock_ollama_unavailable():
    """Mock Ollama as unavailable."""
    with patch("httpx.get", side_effect=Exception("Connection refused")):
        with patch("requests.get", side_effect=Exception("Connection refused")):
            yield


# ============================================================
# LLM Mock Fixtures
# ============================================================


@pytest.fixture(name="mock_llm")
def mock_llm_fixt():
    """Mock LLM that returns predefined responses."""
    mock = MagicMock()
    mock.invoke.return_value = "This is a mock response about Python basics."

    with patch("langchain_ollama.OllamaLLM", return_value=mock):
        yield mock


@pytest.fixture(name="mock_embeddings")
def mock_embeddings_fixt():
    """Mock embeddings model."""
    mock = MagicMock()
    # Return 384-dimensional vectors (typical for sentence-transformers)
    mock.embed_documents.side_effect = lambda texts: [[0.1] * 384] * len(texts)
    mock.embed_query.return_value = [0.1] * 384

    with patch("langchain_huggingface.HuggingFaceEmbeddings", return_value=mock):
        with patch("obsidianrag.core.db_service.HuggingFaceEmbeddings", return_value=mock):
            yield mock


@pytest.fixture(name="mock_qa_agent")
def mock_qa_agent_fixt():
    """Mock the QA Agent to avoid loading LLM/embeddings."""
    mock_agent = MagicMock()
    mock_agent.invoke.return_value = {
        "answer": "This is a mock answer about your notes.",
        "context": [],
        "sources": ["Python Basics.md", "Advanced Python.md"],
    }
    yield mock_agent


# ============================================================
# API Client Fixtures
# ============================================================


@pytest.fixture
def test_client(mock_vault: Path, mock_embeddings):
    """Create a test client for the FastAPI app.

    Note: This uses real server but with mocked embeddings.
    For faster tests, use mock_qa_agent fixture to skip LLM loading.
    """
    from obsidianrag.api.server import create_app
    from obsidianrag.config import configure_from_vault

    # Configure settings for test vault
    configure_from_vault(str(mock_vault))

    # Create app with mocked embeddings and LLM
    from langchain_core.runnables import RunnableLambda

    mock_llm_internal = RunnableLambda(lambda x: "Integrated answer")

    with patch("obsidianrag.core.db_service.HuggingFaceEmbeddings", return_value=mock_embeddings):
        with patch("obsidianrag.core.qa_agent.OllamaLLM", return_value=mock_llm_internal):
            with patch("obsidianrag.core.qa_service.verify_ollama_available"):
                with patch("obsidianrag.core.qa_agent.verify_ollama_available"):
                    with patch("obsidianrag.core.qa_agent.verify_llm_model", return_value="gemma3"):
                        app = create_app(str(mock_vault))

                        with TestClient(app) as client:
                            yield client


@pytest.fixture
def fast_test_client(mock_qa_agent):
    """Create a fast test client with fully mocked backend.

    Use this for tests that don't need real DB/embeddings.
    """
    from typing import Optional

    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field

    class Question(BaseModel):
        text: str = Field(..., alias="question")
        session_id: Optional[str] = None

        class Config:
            populate_by_name = True

    class Source(BaseModel):
        source: str
        score: float = 0.0
        retrieval_type: str = "retrieved"

    class Answer(BaseModel):
        question: str
        result: str
        sources: list[Source]
        text_blocks: list[str] = []
        process_time: float = 0.1
        session_id: str = "test-session"

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "healthy", "version": "3.0.0"}

    @app.post("/ask", response_model=Answer)
    def ask(question: Question):
        if not question.text.strip():
            raise HTTPException(400, "Question cannot be empty")
        result = mock_qa_agent.invoke({"question": question.text})
        sources = [Source(source=s, score=0.9) for s in result.get("sources", ["Python Basics.md"])]
        return Answer(
            question=question.text,
            result=result["answer"],
            sources=sources,
        )

    @app.get("/stats")
    def stats():
        return {"total_chunks": 10, "total_documents": 4}

    @app.post("/rebuild_db")
    def rebuild():
        return {"status": "ok"}

    with TestClient(app) as client:
        yield client


# ============================================================
# Database Fixtures
# ============================================================


@pytest.fixture
def mock_chroma_db():
    """Mock ChromaDB instance."""
    mock_db = MagicMock()
    mock_db.get.return_value = {
        "documents": ["Python is great", "Functions are useful"],
        "metadatas": [
            {"source": "/test/Python Basics.md", "links": "Advanced Python"},
            {"source": "/test/Advanced Python.md", "links": "Python Basics"},
        ],
        "ids": ["id1", "id2"],
    }
    mock_db.as_retriever.return_value = MagicMock()

    return mock_db


# ============================================================
# CLI Fixtures
# ============================================================


@pytest.fixture
def cli_runner():
    """Create a Typer CLI test runner."""
    from typer.testing import CliRunner

    return CliRunner()


# ============================================================
# Environment Fixtures
# ============================================================


@pytest.fixture
def clean_env():
    """Temporarily clear OBSIDIAN_PATH from environment."""
    old_value = os.environ.pop("OBSIDIAN_PATH", None)
    yield
    if old_value:
        os.environ["OBSIDIAN_PATH"] = old_value


@pytest.fixture
def env_with_vault(mock_vault: Path):
    """Set OBSIDIAN_PATH environment variable to mock vault."""
    old_value = os.environ.get("OBSIDIAN_PATH")
    os.environ["OBSIDIAN_PATH"] = str(mock_vault)
    yield
    if old_value:
        os.environ["OBSIDIAN_PATH"] = old_value
    else:
        os.environ.pop("OBSIDIAN_PATH", None)
