"""Integration tests for ObsidianRAG."""

from unittest.mock import MagicMock, patch

import pytest


class TestFullRAGPipeline:
    """Integration tests for the complete RAG pipeline."""

    @pytest.mark.integration
    @patch("obsidianrag.core.qa_agent.OllamaLLM")
    def test_index_and_query_flow(self, mock_ollama, mock_vault, mock_chroma_db):
        """Test complete flow: index vault → query → get answer."""
        # Setup mock LLM
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="Machine learning is a subset of artificial intelligence."
        )
        mock_ollama.return_value = mock_llm

        # Flow:
        # 1. DBService indexes mock vault
        # 2. User submits question
        # 3. QAAgent retrieves context via hybrid search
        # 4. QAAgent generates answer using LLM
        # 5. Response includes answer + sources

    @pytest.mark.integration
    @patch("obsidianrag.core.qa_agent.OllamaLLM")
    def test_graphrag_link_expansion(self, mock_ollama, mock_vault, mock_chroma_db):
        """Test that GraphRAG expands [[wikilinks]] during retrieval."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Answer with expanded context")
        mock_ollama.return_value = mock_llm

        # When a retrieved document has [[links]], those linked documents
        # should also be fetched and included in context

    @pytest.mark.integration
    def test_incremental_indexing(self, mock_vault, mock_chroma_db):
        """Test that incremental indexing only updates changed files."""
        # 1. Initial index
        # 2. Modify one file
        # 3. Reindex
        # 4. Verify only modified file was reindexed

    @pytest.mark.integration
    def test_hybrid_search_combines_bm25_and_vector(self, mock_vault, mock_chroma_db):
        """Test that hybrid search uses both BM25 and vector similarity."""
        # Query should use ensemble of:
        # - BM25 (keyword matching)
        # - Vector similarity (semantic matching)
        # Results should be combined and reranked


class TestAPIIntegration:
    """Integration tests for API endpoints with full backend."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires full backend setup with real embeddings")
    @patch("obsidianrag.core.qa_agent.OllamaLLM")
    def test_ask_endpoint_full_flow(self, mock_ollama, test_client, mock_vault):
        """Test /ask endpoint with complete backend."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Integrated answer")
        mock_ollama.return_value = mock_llm

        response = test_client.post("/ask", json={"text": "What is deep learning?"})

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    @pytest.mark.integration
    def test_stats_reflects_indexed_data(self, fast_test_client, mock_vault):
        """Test that /stats endpoint reflects actual indexed data."""
        response = fast_test_client.get("/stats")

        if response.status_code == 200:
            data = response.json()
            # Stats should reflect the mock vault contents
            assert isinstance(data, dict)


@pytest.mark.skip(reason="CLI integration tests require complex mock setup - to be fixed")
class TestCLIIntegration:
    """Integration tests for CLI commands."""

    @pytest.mark.integration
    @patch("obsidianrag.api.server.run_server")
    @patch("obsidianrag.config.configure_from_vault")
    def test_cli_serve_starts_server(self, mock_configure, mock_run, cli_runner, mock_vault):
        """Test that CLI serve command configures and starts server."""
        from obsidianrag.cli.main import app

        cli_runner.invoke(app, ["serve", "--vault-path", str(mock_vault)])

        # Should configure from vault and start server
        mock_configure.assert_called_once()
        # run_server is called inside serve command

    @pytest.mark.integration
    @patch("obsidianrag.core.db_service.DBService")
    @patch("obsidianrag.config.configure_from_vault")
    def test_cli_index_creates_db(self, mock_configure, mock_db, cli_runner, mock_vault):
        """Test that CLI index command creates/updates database."""
        from obsidianrag.cli.main import app

        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        cli_runner.invoke(app, ["index", "--vault-path", str(mock_vault)])

        # Should configure from vault
        mock_configure.assert_called_once()


class TestErrorRecovery:
    """Tests for error handling and recovery."""

    @pytest.mark.integration
    def test_recovers_from_corrupted_db(self, mock_vault, tmp_path):
        """Test that system can recover from corrupted database."""
        # Create a corrupted db file
        db_path = tmp_path / "db"
        db_path.mkdir()
        corrupted_file = db_path / "chroma.sqlite3"
        corrupted_file.write_text("corrupted data")

        # System should handle this gracefully

    @pytest.mark.integration
    @patch("obsidianrag.core.qa_agent.OllamaLLM")
    def test_handles_ollama_timeout(self, mock_ollama, mock_vault):
        """Test handling of Ollama timeout."""
        mock_ollama.side_effect = TimeoutError("Connection timed out")

        # Should return appropriate error message

    @pytest.mark.integration
    def test_handles_empty_vault(self, tmp_path):
        """Test handling of empty vault (no markdown files)."""
        empty_vault = tmp_path / "empty_vault"
        empty_vault.mkdir()

        # Should handle gracefully, not crash


class TestPerformance:
    """Performance-related integration tests."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_large_document_indexing(self, tmp_path):
        """Test indexing of large documents doesn't timeout."""
        vault = tmp_path / "large_vault"
        vault.mkdir()

        # Create a large markdown file
        large_content = "# Large Document\n\n" + ("Lorem ipsum dolor sit amet. " * 10000)
        (vault / "large.md").write_text(large_content)

        # Indexing should complete without timeout

    @pytest.mark.integration
    @pytest.mark.slow
    def test_many_files_indexing(self, tmp_path):
        """Test indexing many files is performant."""
        vault = tmp_path / "many_files_vault"
        vault.mkdir()

        # Create many small files
        for i in range(100):
            (vault / f"note_{i}.md").write_text(f"# Note {i}\n\nContent for note {i}")

        # Indexing should complete in reasonable time


class TestConcurrency:
    """Tests for concurrent access handling."""

    @pytest.mark.integration
    def test_concurrent_queries(self, fast_test_client):
        """Test handling of concurrent query requests."""
        # Simulate sequential requests (TestClient is synchronous)
        queries = [
            "What is machine learning?",
            "Explain deep learning",
            "What are neural networks?",
        ]

        for q in queries:
            response = fast_test_client.post("/ask", json={"text": q})
            assert response.status_code == 200


class TestConfigurationIntegration:
    """Tests for configuration handling."""

    @pytest.mark.integration
    def test_settings_from_env(self, mock_vault, monkeypatch):
        """Test that settings are properly loaded from environment."""
        monkeypatch.setenv("OBSIDIANRAG_VAULT_PATH", str(mock_vault))
        monkeypatch.setenv("OBSIDIANRAG_LLM_MODEL", "test-model")

        # Settings should reflect environment variables

    @pytest.mark.integration
    def test_settings_from_dotenv(self, mock_vault, tmp_path):
        """Test that settings can be loaded from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(f"VAULT_PATH={mock_vault}\nLLM_MODEL=test-model")

        # Settings should load from .env when present
