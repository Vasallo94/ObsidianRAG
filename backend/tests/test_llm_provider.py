"""Tests for provider-neutral chat model construction."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from obsidianrag.config import Settings
from obsidianrag.core.llm_provider import create_chat_model


def test_ollama_chat_model_uses_configured_temperature():
    settings = Settings(
        llm_provider="ollama",
        llm_model="gemma3",
        llm_temperature=0.25,
        _env_file=None,
    )

    with (
        patch("obsidianrag.core.llm_provider._verify_ollama_model", return_value="gemma3"),
        patch("langchain_ollama.ChatOllama") as chat_ollama,
    ):
        _, model_name = create_chat_model(settings)

    assert model_name == "gemma3"
    assert chat_ollama.call_args.kwargs["temperature"] == 0.25


def test_compatible_chat_model_uses_configured_temperature():
    settings = Settings(
        llm_provider="custom",
        llm_api_format="chat-completions",
        llm_model="test-model",
        llm_temperature=0.1,
        compatible_base_url="http://localhost:1234/v1",
        _env_file=None,
    )

    with (
        patch(
            "obsidianrag.core.llm_provider._verify_chat_completions_model",
            return_value="test-model",
        ),
        patch("langchain_openai.ChatOpenAI") as chat_openai,
    ):
        create_chat_model(settings)

    assert chat_openai.call_args.kwargs["temperature"] == 0.1


@pytest.mark.parametrize("temperature", [-0.1, 2.1])
def test_temperature_must_stay_in_provider_safe_range(temperature):
    with pytest.raises(ValidationError):
        Settings(llm_temperature=temperature, _env_file=None)
