"""Tests for v4 embedding and splitter factories."""

from unittest.mock import MagicMock, patch

import pytest

from obsidianrag.config import Settings, settings_override
from obsidianrag.core.db_service import get_embeddings, get_text_splitter


def test_huggingface_embeddings_use_configured_model():
    settings = Settings(embedding_provider="huggingface", embedding_model="test/model")
    embeddings = MagicMock()
    with (
        settings_override(settings),
        patch(
            "obsidianrag.core.db_service.HuggingFaceEmbeddings",
            return_value=embeddings,
        ) as factory,
    ):
        assert get_embeddings() is embeddings

    factory.assert_called_once_with(model_name="test/model")


def test_ollama_embeddings_fail_without_contacting_pull_after_connection_error():
    settings = Settings(embedding_provider="ollama")
    with (
        settings_override(settings),
        patch("httpx.get", side_effect=ConnectionError("offline")),
        patch("obsidianrag.core.db_service.pull_ollama_model") as pull,
        pytest.raises(RuntimeError, match="Could not connect to Ollama"),
    ):
        get_embeddings()

    pull.assert_not_called()


def test_text_splitter_uses_configured_sizes():
    settings = Settings(chunk_size=200, chunk_overlap=25)
    with settings_override(settings):
        splitter = get_text_splitter()

    assert splitter._chunk_size == 200
    assert splitter._chunk_overlap == 25
