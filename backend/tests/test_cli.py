"""Tests for ObsidianRAG CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from click import unstyle
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
        from obsidianrag import __version__

        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "ObsidianRAG" in result.stdout
        assert __version__ in result.stdout

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
    def test_serve_default_options(
        self, mock_configure, mock_create_app, mock_uvicorn, runner, mock_vault
    ):
        """Test serve command with default options."""
        mock_create_app.return_value = MagicMock()

        result = runner.invoke(app, ["serve", "--vault", str(mock_vault)])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
        mock_uvicorn.assert_called_once()

    @patch("uvicorn.run")
    @patch("obsidianrag.api.server.create_app")
    @patch("obsidianrag.config.configure_from_vault")
    def test_serve_custom_port(
        self, mock_configure, mock_create_app, mock_uvicorn, runner, mock_vault
    ):
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
    def test_serve_custom_host(
        self, mock_configure, mock_create_app, mock_uvicorn, runner, mock_vault
    ):
        """Test serve command with custom host."""
        mock_create_app.return_value = MagicMock()

        result = runner.invoke(app, ["serve", "--vault", str(mock_vault), "--host", "0.0.0.0"])

        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs.get("host") == "0.0.0.0"


class TestIndexCommand:
    """Tests for the index command."""

    @pytest.mark.parametrize("full_rebuild", [False, True])
    def test_index_builds_v4_revision(self, runner, mock_vault, full_rebuild):
        build_result = MagicMock(
            revision="revision-2",
            notes=3,
            chunks=7,
            reused_chunks=5,
            reindexed_notes=1,
            deleted_notes=1,
        )
        args = ["index", "--vault", str(mock_vault)]
        if full_rebuild:
            args.append("--full-rebuild")
        with (
            patch("obsidianrag.v4.build_index", return_value=build_result) as build,
            patch("obsidianrag.core.db_service.get_embeddings", return_value=MagicMock()),
        ):
            result = runner.invoke(app, args)

        assert result.exit_code == 0
        assert build.call_args.kwargs["full_rebuild"] is full_rebuild
        assert "Reused chunks: 5" in unstyle(result.stdout)


class TestStatusCommand:
    """Tests for the status command."""

    def test_status_shows_index_state_without_loading_embeddings(self, runner, mock_vault):
        status = MagicMock(
            state="missing",
            indexed_notes=0,
            indexed_chunks=0,
            changed_notes=4,
            deleted_notes=0,
        )
        with (
            patch("obsidianrag.v4.index_status", return_value=status),
            patch("obsidianrag.core.db_service.get_embeddings") as get_embeddings,
        ):
            result = runner.invoke(app, ["status", "--vault", str(mock_vault)])

        assert result.exit_code == 0
        assert "missing" in result.stdout
        get_embeddings.assert_not_called()


class TestAskCommand:
    """Tests for the ask command."""

    @patch("obsidianrag.core.query_pipeline.create_v4_query_pipeline")
    def test_ask_routes_v4_and_closes_pipeline(self, create_pipeline, runner, mock_vault):
        from langchain_core.documents import Document

        pipeline = MagicMock()
        pipeline.ask.return_value = MagicMock(
            answer="Grounded [1].",
            documents=(
                Document(
                    page_content="Grounded",
                    metadata={"source": "Notes/Grounding.md"},
                ),
            ),
        )
        create_pipeline.return_value = pipeline

        result = runner.invoke(
            app,
            [
                "ask",
                "What is grounded?",
                "--vault",
                str(mock_vault),
                "--k",
                "3",
            ],
        )

        assert result.exit_code == 0
        assert "Grounded" in result.stdout
        assert "Notes/Grounding.md" in result.stdout
        create_pipeline.assert_called_once()
        assert create_pipeline.call_args.kwargs["k"] == 3
        pipeline.ask.assert_called_once_with("What is grounded?")
        pipeline.close.assert_called_once_with()

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
        assert "--full-rebuild" in result.stdout

    def test_v4_commands_are_discoverable(self, runner):
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "index" in result.stdout
        assert "prune" in result.stdout
        assert "search" in result.stdout
        assert "compare-evaluations" in result.stdout

    def test_v4_index_reports_incremental_counts(self, runner, tmp_path):
        build_result = MagicMock(
            revision="revision-2",
            notes=3,
            chunks=7,
            reused_chunks=5,
            reindexed_notes=1,
            deleted_notes=1,
        )
        with (
            patch("obsidianrag.v4.build_index", return_value=build_result),
            patch("obsidianrag.core.db_service.get_embeddings", return_value=MagicMock()),
        ):
            result = runner.invoke(app, ["index", "--vault", str(tmp_path)])

        assert result.exit_code == 0
        assert "Reused chunks: 5" in unstyle(result.stdout)
        assert "Reindexed notes: 1" in unstyle(result.stdout)
        assert "Deleted notes: 1" in unstyle(result.stdout)

    def test_v4_search_help_exposes_embedding_free_mode(self, runner):
        result = runner.invoke(app, ["search", "--help"])

        assert result.exit_code == 0
        assert "--lexical-only" in unstyle(result.stdout)

    def test_external_agent_evaluation_requires_private_data_confirmation(self, runner, tmp_path):
        dataset = tmp_path / "private.json"
        dataset.write_text('{"cases":[{}]}')

        result = runner.invoke(
            app,
            [
                "evaluate-agent",
                str(dataset),
                "--generator-command",
                "generator",
                "--judge-command",
                "judge",
            ],
        )

        assert result.exit_code == 2
        assert "--allow-private-data" in result.stdout

    def test_evaluate_rejects_unknown_engine(self, runner, mock_vault, tmp_path):
        dataset = tmp_path / "questions.json"
        dataset.write_text('{"cases":[{"question":"q","expected_sources":["note.md"]}]}')

        result = runner.invoke(
            app,
            ["evaluate", str(dataset), "--vault", str(mock_vault), "--engine", "unknown"],
        )

        assert result.exit_code == 2
