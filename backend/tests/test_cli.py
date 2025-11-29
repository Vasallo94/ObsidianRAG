"""Tests for ObsidianRAG CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from obsidianrag.cli.main import app


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


class TestVersionCommand:
    """Tests for the version command."""

    def test_version_displays_correct_format(self, runner):
        """Test that version command shows version number."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "ObsidianRAG" in result.stdout
        assert "3.0.0" in result.stdout

    def test_version_shows_description(self, runner):
        """Test version command shows project description."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "RAG" in result.stdout or "Obsidian" in result.stdout


class TestServeCommand:
    """Tests for the serve command."""

    @patch("uvicorn.run")
    @patch("obsidianrag.api.server.create_app")
    @patch("obsidianrag.config.configure_from_vault")
    def test_serve_default_options(self, mock_configure, mock_create_app, mock_uvicorn, runner, mock_vault):
        """Test serve command with default options."""
        mock_create_app.return_value = MagicMock()
        
        result = runner.invoke(app, ["serve", "--vault", str(mock_vault)])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
        mock_uvicorn.assert_called_once()

    @patch("uvicorn.run")
    @patch("obsidianrag.api.server.create_app")
    @patch("obsidianrag.config.configure_from_vault")
    def test_serve_custom_port(self, mock_configure, mock_create_app, mock_uvicorn, runner, mock_vault):
        """Test serve command with custom port."""
        mock_create_app.return_value = MagicMock()
        
        result = runner.invoke(app, ["serve", "--vault", str(mock_vault), "--port", "9000"])

        assert result.exit_code == 0
        mock_uvicorn.assert_called_once()
        # Verify port was passed correctly
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs is not None
        assert call_kwargs.kwargs.get("port") == 9000

    @patch("uvicorn.run")
    @patch("obsidianrag.api.server.create_app")
    @patch("obsidianrag.config.configure_from_vault")
    def test_serve_custom_host(self, mock_configure, mock_create_app, mock_uvicorn, runner, mock_vault):
        """Test serve command with custom host."""
        mock_create_app.return_value = MagicMock()
        
        result = runner.invoke(app, ["serve", "--vault", str(mock_vault), "--host", "0.0.0.0"])

        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs.get("host") == "0.0.0.0"


class TestIndexCommand:
    """Tests for the index command."""

    @patch("obsidianrag.core.db_service.load_or_create_db")
    @patch("obsidianrag.config.configure_from_vault")
    def test_index_full_rebuild(self, mock_configure, mock_load_db, runner, mock_vault):
        """Test index command with full rebuild."""
        mock_db = MagicMock()
        mock_db.get.return_value = {
            "documents": ["doc1", "doc2"],
            "metadatas": [{"source": "note1.md"}, {"source": "note2.md"}]
        }
        mock_load_db.return_value = mock_db

        result = runner.invoke(app, ["index", "--vault", str(mock_vault), "--force"])

        assert result.exit_code == 0
        mock_load_db.assert_called_once()
        # Verify force=True was passed
        call_kwargs = mock_load_db.call_args
        assert call_kwargs.kwargs.get("force_rebuild") is True

    @patch("obsidianrag.core.db_service.load_or_create_db")
    @patch("obsidianrag.config.configure_from_vault")
    def test_index_incremental(self, mock_configure, mock_load_db, runner, mock_vault):
        """Test index command for incremental update."""
        mock_db = MagicMock()
        mock_db.get.return_value = {
            "documents": ["doc1"],
            "metadatas": [{"source": "note1.md"}]
        }
        mock_load_db.return_value = mock_db

        result = runner.invoke(app, ["index", "--vault", str(mock_vault)])

        assert result.exit_code == 0
        mock_load_db.assert_called_once()


class TestStatusCommand:
    """Tests for the status command."""

    @patch("httpx.get")
    def test_status_shows_vault_info(self, mock_httpx, runner, mock_vault):
        """Test status command displays vault info."""
        # Mock Ollama check to fail (not running)
        mock_httpx.side_effect = Exception("Connection refused")
        
        result = runner.invoke(app, ["status", "--vault", str(mock_vault)])

        assert result.exit_code == 0
        assert "Vault" in result.stdout or "Status" in result.stdout

    @patch("httpx.get")
    def test_status_shows_ollama_status(self, mock_httpx, runner, mock_vault):
        """Test status command checks Ollama."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": [{"name": "gemma3"}]}
        mock_httpx.return_value = mock_response
        
        result = runner.invoke(app, ["status", "--vault", str(mock_vault)])

        assert result.exit_code == 0
        # Should show Ollama status
        assert "Ollama" in result.stdout or "models" in result.stdout.lower()


class TestAskCommand:
    """Tests for the ask command."""

    @patch("obsidianrag.ObsidianRAG")
    def test_ask_simple_question(self, mock_rag_class, runner, mock_vault):
        """Test ask command with a simple question."""
        mock_rag = MagicMock()
        mock_rag.ask.return_value = ("Test answer about ML", [])
        mock_rag_class.return_value = mock_rag

        result = runner.invoke(
            app, ["ask", "What is machine learning?", "--vault", str(mock_vault)]
        )

        assert result.exit_code == 0
        assert "Test answer" in result.stdout or "Answer" in result.stdout

    def test_ask_without_question(self, runner, mock_vault):
        """Test ask command without providing a question."""
        result = runner.invoke(app, ["ask", "--vault", str(mock_vault)])

        # Should fail - question is required argument
        assert result.exit_code != 0


class TestCLIHelp:
    """Tests for CLI help messages."""

    def test_main_help(self, runner):
        """Test main help message."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "ObsidianRAG" in result.stdout or "Usage" in result.stdout

    def test_serve_help(self, runner):
        """Test serve command help."""
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.stdout or "port" in result.stdout.lower()

    def test_index_help(self, runner):
        """Test index command help."""
        result = runner.invoke(app, ["index", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.stdout or "force" in result.stdout.lower()
