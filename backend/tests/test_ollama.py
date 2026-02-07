import importlib.util
import os
import subprocess
import sys
from unittest import mock

import httpx
import pytest


# Fixture to load ollama module safely without triggering package init at collection time
@pytest.fixture
def ollama_module():
    # Load ollama.py directly to avoid triggering obsidianrag package initialization
    # preventing ImportError: cannot load module more than once per process (numpy)
    file_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../obsidianrag/utils/ollama.py")
    )
    spec = importlib.util.spec_from_file_location("obsidianrag.utils.ollama", file_path)
    ollama = importlib.util.module_from_spec(spec)

    # We don't strictly need to register it in sys.modules for the test to work,
    # but for coverage to track it as the real module, we might want to.
    # However, modifying sys.modules inside a test might affect others.
    # Let's try registering it to ensure coverage works, but we should restore it?
    # Or just let it be.

    sys.modules["obsidianrag.utils.ollama"] = ollama
    spec.loader.exec_module(ollama)
    return ollama


# ==============================================================================
# Tests for pull_ollama_model
# ==============================================================================


def test_pull_ollama_model_success(monkeypatch, ollama_module):
    """Test successful model pull."""
    mock_result = mock.Mock(returncode=0, stderr="")
    monkeypatch.setattr(subprocess, "run", mock.Mock(return_value=mock_result))
    assert ollama_module.pull_ollama_model("mini-mix") is True


def test_pull_ollama_model_failure(monkeypatch, ollama_module):
    """Test failure during model pull (non-zero exit code)."""
    mock_result = mock.Mock(returncode=1, stderr="error")
    monkeypatch.setattr(subprocess, "run", mock.Mock(return_value=mock_result))
    assert ollama_module.pull_ollama_model("mini-mix") is False


def test_pull_ollama_model_timeout(monkeypatch, ollama_module):
    """Test timeout during model pull."""
    monkeypatch.setattr(
        subprocess, "run", mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="", timeout=10))
    )
    assert ollama_module.pull_ollama_model("mini-mix") is False


def test_pull_ollama_model_cli_missing(monkeypatch, ollama_module):
    """Test missing Ollama CLI."""
    monkeypatch.setattr(subprocess, "run", mock.Mock(side_effect=FileNotFoundError()))
    assert ollama_module.pull_ollama_model("mini-mix") is False


def test_pull_ollama_model_generic_exception(monkeypatch, ollama_module):
    """Test generic exception during model pull."""
    monkeypatch.setattr(subprocess, "run", mock.Mock(side_effect=Exception("Unexpected error")))
    assert ollama_module.pull_ollama_model("mini-mix") is False


# ==============================================================================
# Tests for get_available_ollama_models
# ==============================================================================


def test_get_available_ollama_models_success(monkeypatch, ollama_module):
    """Test successfully retrieving available models."""
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"models": [{"name": "llama3:latest"}, {"name": "gemma:2b"}]}

    monkeypatch.setattr(httpx, "get", mock.Mock(return_value=mock_response))

    models = ollama_module.get_available_ollama_models()
    assert "llama3" in models
    assert "gemma" in models
    assert len(models) == 2


def test_get_available_ollama_models_api_failure(monkeypatch, ollama_module):
    """Test API failure (non-200 status code)."""
    mock_response = mock.Mock()
    mock_response.status_code = 500
    monkeypatch.setattr(httpx, "get", mock.Mock(return_value=mock_response))

    models = ollama_module.get_available_ollama_models()
    assert models == []


def test_get_available_ollama_models_exception(monkeypatch, ollama_module):
    """Test exception during API call."""
    monkeypatch.setattr(httpx, "get", mock.Mock(side_effect=Exception("Connection refused")))

    models = ollama_module.get_available_ollama_models()
    assert models == []


# ==============================================================================
# Tests for ensure_model_available
# ==============================================================================


def test_ensure_model_available_already_exists(monkeypatch, ollama_module):
    """Test when model is already available."""
    mock_get = mock.Mock(return_value=["my-model"])
    monkeypatch.setattr(ollama_module, "get_available_ollama_models", mock_get)

    assert ollama_module.ensure_model_available("my-model") is True
    mock_get.assert_called_once()


def test_ensure_model_available_needs_pull_success(monkeypatch, ollama_module):
    """Test when model is missing and needs to be pulled successfully."""
    monkeypatch.setattr(ollama_module, "get_available_ollama_models", mock.Mock(return_value=[]))
    mock_pull = mock.Mock(return_value=True)
    monkeypatch.setattr(ollama_module, "pull_ollama_model", mock_pull)

    assert ollama_module.ensure_model_available("new-model") is True
    mock_pull.assert_called_with("new-model", 600)


def test_ensure_model_available_needs_pull_failure(monkeypatch, ollama_module):
    """Test when model is missing and pull fails."""
    monkeypatch.setattr(ollama_module, "get_available_ollama_models", mock.Mock(return_value=[]))
    mock_pull = mock.Mock(return_value=False)
    monkeypatch.setattr(ollama_module, "pull_ollama_model", mock_pull)

    assert ollama_module.ensure_model_available("bad-model") is False
    mock_pull.assert_called_with("bad-model", 600)
