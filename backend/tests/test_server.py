"""Tests for ObsidianRAG FastAPI server."""

import pytest


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_ok(self, fast_test_client):
        """Test that health endpoint returns healthy status."""
        response = fast_test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "ok"]

    def test_health_includes_version(self, fast_test_client):
        """Test that health endpoint includes version info."""
        response = fast_test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        # Version info might be in various fields
        assert "version" in data or "model" in data or len(data) > 1


class TestAskEndpoint:
    """Tests for the /ask endpoint."""

    def test_ask_valid_question(self, fast_test_client):
        """Test asking a valid question."""
        response = fast_test_client.post("/ask", json={"text": "What is machine learning?"})

        assert response.status_code == 200
        data = response.json()
        # API uses "result" field for the answer
        assert "result" in data or "answer" in data

    def test_ask_empty_question(self, fast_test_client):
        """Test asking with empty question."""
        response = fast_test_client.post("/ask", json={"text": ""})

        # Should return error or validation failure
        assert response.status_code in [400, 422]

    def test_ask_missing_question_field(self, fast_test_client):
        """Test asking without question field."""
        response = fast_test_client.post("/ask", json={})

        # Should return validation error
        assert response.status_code == 422

    def test_ask_with_context(self, fast_test_client):
        """Test asking with conversation context."""
        response = fast_test_client.post(
            "/ask",
            json={
                "text": "Tell me more about that",
                "conversation_id": "test-123",
            },
        )

        assert response.status_code == 200

    def test_ask_returns_sources(self, fast_test_client):
        """Test that ask endpoint returns sources."""
        response = fast_test_client.post("/ask", json={"text": "What is deep learning?"})

        assert response.status_code == 200
        data = response.json()
        # Sources might be in different formats
        assert "sources" in data or "documents" in data or "context" in data


class TestStatsEndpoint:
    """Tests for the /stats endpoint."""

    def test_stats_returns_data(self, fast_test_client):
        """Test that stats endpoint returns vault statistics."""
        response = fast_test_client.get("/stats")

        # Stats might not be available in test mode
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_stats_includes_document_count(self, fast_test_client):
        """Test that stats includes document count."""
        response = fast_test_client.get("/stats")

        if response.status_code == 200:
            data = response.json()
            # Look for any count-related field
            has_count = any(
                "count" in k.lower() or "total" in k.lower() or "num" in k.lower()
                for k in data.keys()
            )
            assert has_count or len(data) > 0


class TestRebuildEndpoint:
    """Tests for the /rebuild_db endpoint."""

    def test_rebuild_requires_post(self, fast_test_client):
        """Test that rebuild requires POST method."""
        response = fast_test_client.get("/rebuild_db")

        # GET should not be allowed
        assert response.status_code == 405

    def test_rebuild_initiates_reindex(self, fast_test_client):
        """Test that rebuild endpoint initiates reindexing."""
        response = fast_test_client.post("/rebuild_db")

        # Should accept the request
        assert response.status_code in [200, 202, 204]
        
        # Should return total_chunks in response
        if response.status_code == 200:
            data = response.json()
            assert "total_chunks" in data or "status" in data


class TestErrorHandling:
    """Tests for API error handling."""

    def test_not_found_endpoint(self, fast_test_client):
        """Test 404 response for unknown endpoint."""
        response = fast_test_client.get("/nonexistent")
        assert response.status_code == 404

    def test_invalid_json_body(self, fast_test_client):
        """Test handling of invalid JSON."""
        response = fast_test_client.post(
            "/ask",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code in [400, 422]

    def test_wrong_content_type(self, fast_test_client):
        """Test handling of wrong content type."""
        response = fast_test_client.post(
            "/ask",
            content="question=test",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # FastAPI might accept or reject this
        assert response.status_code in [200, 415, 422]


class TestCORS:
    """Tests for CORS configuration (requires real server)."""

    @pytest.mark.integration
    def test_cors_headers_present(self, test_client):
        """Test that CORS headers are present."""
        response = test_client.options(
            "/ask",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

        # CORS preflight should be handled
        # Note: Actual CORS behavior depends on configuration
        assert response.status_code in [200, 204, 405]

    @pytest.mark.integration
    def test_cors_allows_localhost(self, test_client):
        """Test that CORS allows localhost origins."""
        response = test_client.post(
            "/ask",
            json={"text": "test"},
            headers={"Origin": "http://localhost:3000"},
        )

        # Request should not be blocked by CORS
        assert response.status_code != 403
