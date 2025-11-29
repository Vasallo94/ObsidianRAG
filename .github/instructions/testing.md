# Testing Guidelines

> Instructions for writing and running tests for ObsidianRAG

## Test Structure

```
backend/tests/
├── __init__.py
├── conftest.py          # Shared fixtures
├── test_cli.py          # CLI command tests
├── test_server.py       # API endpoint tests
├── test_qa_agent.py     # LangGraph agent tests
├── test_db_service.py   # ChromaDB tests
└── test_integration.py  # End-to-end tests
```

## Running Tests

```bash
cd backend

# Run all tests
uv run pytest tests/ -v

# Run specific file
uv run pytest tests/test_cli.py -v

# Run specific test
uv run pytest tests/test_cli.py::TestVersionCommand::test_version_displays_correct_format -v

# Skip slow/integration tests for quick feedback
uv run pytest tests/ -m "not slow and not integration" -v

# Run with coverage
uv run pytest tests/ --cov=obsidianrag --cov-report=term-missing

# Run only integration tests
uv run pytest tests/ -m "integration" -v
```

## Test Markers

```python
import pytest

@pytest.mark.integration  # Requires external services or full setup
@pytest.mark.slow         # Takes >5 seconds
@pytest.mark.asyncio      # Async test
```

## Fixtures (conftest.py)

### Core Fixtures

```python
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_vault(tmp_path: Path) -> Path:
    """Create a temporary vault with test notes."""
    vault = tmp_path / "test_vault"
    vault.mkdir()
    
    # Create test notes
    (vault / "note1.md").write_text("# Machine Learning\n\nML is a subset of AI.")
    (vault / "note2.md").write_text("# Deep Learning\n\nSee [[Machine Learning]].")
    (vault / "folder").mkdir()
    (vault / "folder" / "note3.md").write_text("# Neural Networks\n\nContent here.")
    
    return vault

@pytest.fixture
def mock_settings(mock_vault: Path):
    """Patch settings to use mock vault."""
    with patch("obsidianrag.config.settings") as mock:
        mock.obsidian_path = str(mock_vault)
        mock.db_path = str(mock_vault / ".obsidianrag" / "db")
        mock.llm_model = "test-model"
        mock.use_reranker = False  # Disable for faster tests
        yield mock

@pytest.fixture
def mock_ollama():
    """Mock Ollama LLM responses."""
    with patch("obsidianrag.core.qa_agent.ChatOllama") as mock:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="This is a test answer."
        )
        mock.return_value = mock_llm
        yield mock_llm

@pytest.fixture
def mock_chroma_db():
    """Mock ChromaDB for fast tests."""
    with patch("obsidianrag.core.db_service.chromadb") as mock:
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 10
        mock_collection.query.return_value = {
            "ids": [["doc1", "doc2"]],
            "documents": [["Content 1", "Content 2"]],
            "metadatas": [[{"source": "note1.md"}, {"source": "note2.md"}]],
            "distances": [[0.1, 0.2]],
        }
        mock_client.get_or_create_collection.return_value = mock_collection
        mock.PersistentClient.return_value = mock_client
        yield mock_collection

@pytest.fixture
def test_client(mock_vault: Path, mock_settings):
    """FastAPI test client with mocked dependencies."""
    from fastapi.testclient import TestClient
    from obsidianrag.config import configure_from_vault
    from obsidianrag.api.server import create_app
    
    configure_from_vault(str(mock_vault))
    app = create_app()
    
    with TestClient(app) as client:
        yield client

@pytest.fixture
def cli_runner():
    """Typer CLI test runner."""
    from typer.testing import CliRunner
    return CliRunner()
```

## Writing Tests

### CLI Tests
```python
class TestServeCommand:
    """Tests for the serve command."""

    @patch("obsidianrag.cli.main.run_server")
    @patch("obsidianrag.cli.main.configure_from_vault")
    def test_serve_starts_server(self, mock_configure, mock_run, cli_runner, mock_vault):
        """Test that serve command configures and starts server."""
        from obsidianrag.cli.main import app

        result = cli_runner.invoke(app, ["serve", "--vault-path", str(mock_vault)])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
        mock_run.assert_called_once()

    def test_serve_requires_vault_path(self, cli_runner):
        """Test that serve fails without vault path."""
        from obsidianrag.cli.main import app

        result = cli_runner.invoke(app, ["serve"])
        
        assert result.exit_code != 0
        assert "vault-path" in result.stdout.lower() or "required" in result.stdout.lower()
```

### API Tests
```python
class TestAskEndpoint:
    """Tests for the /ask endpoint."""

    def test_ask_valid_question(self, test_client, mock_ollama):
        """Test asking a valid question."""
        response = test_client.post("/ask", json={"question": "What is ML?"})

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    def test_ask_empty_question(self, test_client):
        """Test asking with empty question returns error."""
        response = test_client.post("/ask", json={"question": ""})

        assert response.status_code in [400, 422]

    def test_ask_missing_field(self, test_client):
        """Test missing question field returns validation error."""
        response = test_client.post("/ask", json={})

        assert response.status_code == 422
```

### Unit Tests with Mocks
```python
class TestDBService:
    """Tests for DBService."""

    @patch("obsidianrag.core.db_service.chromadb")
    def test_indexes_markdown_files(self, mock_chromadb, mock_vault):
        """Test that service finds and indexes .md files."""
        from obsidianrag.core.db_service import DBService

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client

        db = DBService(vault_path=str(mock_vault))
        db.index_vault()

        # Verify add was called with documents
        assert mock_collection.add.called
```

### Integration Tests
```python
@pytest.mark.integration
class TestFullRAGPipeline:
    """Integration tests requiring full setup."""

    @patch("obsidianrag.core.qa_agent.ChatOllama")
    def test_end_to_end_query(self, mock_ollama, mock_vault):
        """Test complete flow: index → query → answer."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Test answer")
        mock_ollama.return_value = mock_llm

        # This test uses real ChromaDB and embeddings
        # Only mock the LLM to avoid Ollama dependency
        
        from obsidianrag.config import configure_from_vault
        from obsidianrag.core.db_service import DBService
        from obsidianrag.core.qa_agent import create_qa_agent

        configure_from_vault(str(mock_vault))
        db = DBService()
        db.index_vault()
        
        agent = create_qa_agent(db)
        result = agent.invoke({"question": "What is machine learning?"})

        assert "answer" in result
        assert len(result["answer"]) > 0
```

## Test Best Practices

### DO ✅
- Mock external services (Ollama, network calls)
- Use `tmp_path` fixture for file operations
- Test error cases and edge cases
- Keep unit tests fast (<1s each)
- Use descriptive test names
- Group related tests in classes

### DON'T ❌
- Don't test implementation details
- Don't rely on real Ollama in unit tests
- Don't hardcode file paths
- Don't skip cleanup (use fixtures)
- Don't write tests that depend on order

## Mocking Guidelines

### When to Mock
| Component | Unit Tests | Integration Tests |
|-----------|-----------|-------------------|
| Ollama/LLM | Always mock | Always mock |
| ChromaDB | Mock | Real (temp dir) |
| Embeddings | Can mock | Real |
| File system | Use tmp_path | Use tmp_path |
| Settings | Patch | Configure properly |

### Mock Patterns
```python
# Patch at the point of use, not definition
@patch("obsidianrag.core.qa_agent.ChatOllama")  # ✅ Where it's used
@patch("langchain_ollama.ChatOllama")            # ❌ Where it's defined

# Use context managers for temporary mocks
def test_something(self):
    with patch("obsidianrag.config.settings") as mock_settings:
        mock_settings.llm_model = "test"
        # test code

# Use fixtures for reusable mocks
@pytest.fixture
def mock_ollama():
    with patch("obsidianrag.core.qa_agent.ChatOllama") as mock:
        yield mock
```

## Coverage Goals

- **Minimum**: 60% overall coverage
- **Target**: 80% for core modules
- **Critical paths**: 100% coverage for:
  - API endpoints
  - CLI commands
  - Error handling

```bash
# Check coverage
uv run pytest tests/ --cov=obsidianrag --cov-fail-under=60

# Generate HTML report
uv run pytest tests/ --cov=obsidianrag --cov-report=html
open htmlcov/index.html
```

## Debugging Failing Tests

```bash
# Run with full output
uv run pytest tests/test_file.py -v -s

# Run with debugging on failure
uv run pytest tests/test_file.py --pdb

# Run single test with max verbosity
uv run pytest tests/test_file.py::TestClass::test_method -vvv --tb=long

# Show local variables on failure
uv run pytest tests/test_file.py --tb=short --showlocals
```
