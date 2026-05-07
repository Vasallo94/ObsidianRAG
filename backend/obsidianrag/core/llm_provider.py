"""LangChain chat model provider helpers."""

from __future__ import annotations

from typing import AsyncIterator, List

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import SecretStr

from obsidianrag.config import Settings, get_settings
from obsidianrag.core.qa_service import ModelNotAvailableError, verify_ollama_available
from obsidianrag.utils.logger import setup_logger
from obsidianrag.utils.ollama import get_available_ollama_models, pull_ollama_model

logger = setup_logger(__name__)


def normalize_llm_provider(provider: str) -> str:
    """Normalize provider values accepted by CLI, plugin settings, and env vars."""
    normalized = provider.strip().lower().replace("_", "-")
    if normalized == "ollama":
        return "ollama"
    if normalized in {"lmstudio", "lm-studio"}:
        return "lmstudio"
    if normalized in {"custom", "compatible", "chat-completions", "openai-compatible"}:
        return "custom"
    raise ValueError("Unsupported LLM provider. Use 'ollama', 'lmstudio', or 'custom'.")


def normalize_api_format(api_format: str) -> str:
    """Normalize low-level API format names."""
    normalized = api_format.strip().lower().replace("_", "-")
    if normalized == "ollama":
        return "ollama"
    if normalized in {"chat-completions", "openai-compatible", "openai"}:
        return "chat-completions"
    raise ValueError("Unsupported LLM API format. Use 'ollama' or 'chat-completions'.")


def create_chat_model(settings: Settings | None = None) -> tuple[BaseChatModel, str]:
    """Create a LangChain chat model for the configured runtime.

    The public provider names stay runtime-oriented (`ollama`, `lmstudio`,
    `custom`). Internally, compatible servers such as LM Studio are adapted
    through LangChain's chat model interfaces.
    """
    settings = settings or get_settings()
    provider = normalize_llm_provider(settings.llm_provider)

    if provider == "ollama":
        model_name = _verify_ollama_model(settings.llm_model, settings)
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model_name,
            base_url=settings.ollama_base_url,
            client_kwargs={"timeout": settings.request_timeout},
        ), model_name

    api_format = normalize_api_format(
        "chat-completions" if provider == "lmstudio" else settings.llm_api_format
    )

    if api_format == "ollama":
        model_name = _verify_ollama_model(settings.llm_model, settings)
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model_name,
            base_url=settings.ollama_base_url,
            client_kwargs={"timeout": settings.request_timeout},
        ), model_name

    if api_format == "chat-completions":
        model_name = _verify_chat_completions_model(settings.llm_model, settings)
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise ModelNotAvailableError(
                "Chat Completions compatible providers require the langchain-openai package."
            ) from e

        return (
            ChatOpenAI(
                model=model_name,
                base_url=settings.compatible_base_url.rstrip("/"),
                api_key=SecretStr(settings.compatible_api_key),
                timeout=settings.request_timeout,
            ),
            model_name,
        )

    raise ValueError(f"Unsupported LLM API format: {api_format}")


def list_llm_models(settings: Settings | None = None) -> List[str]:
    """List available models for providers that expose a local model catalog."""
    settings = settings or get_settings()
    provider = normalize_llm_provider(settings.llm_provider)

    api_format = normalize_api_format(
        "chat-completions" if provider == "lmstudio" else settings.llm_api_format
    )

    if provider == "ollama" or api_format == "ollama":
        return get_available_ollama_models(settings.ollama_base_url)

    response = httpx.get(
        f"{settings.compatible_base_url.rstrip('/')}/models",
        headers=_compatible_headers(settings),
        timeout=5.0,
    )
    response.raise_for_status()
    data = response.json()
    return [model["id"] for model in data.get("data", []) if model.get("id")]


async def stream_chat_model_tokens(
    messages: list[BaseMessage],
    settings: Settings | None = None,
    *,
    model: BaseChatModel | None = None,
) -> AsyncIterator[str]:
    """Stream text chunks using the configured LangChain chat model."""
    if model is None:
        model, _ = create_chat_model(settings)
    async for chunk in model.astream(messages):
        content = getattr(chunk, "content", "")
        if isinstance(content, str) and content:
            yield content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    yield part
                elif isinstance(part, dict) and isinstance(part.get("text"), str):
                    yield part["text"]


def single_human_message(prompt: str) -> list[BaseMessage]:
    """Build a simple one-message chat input for prompt-shaped workflows."""
    return [HumanMessage(content=prompt)]


def _verify_ollama_model(model: str, settings: Settings) -> str:
    verify_ollama_available()
    available_models = get_available_ollama_models(settings.ollama_base_url)

    if not available_models:
        raise ModelNotAvailableError(
            f"Cannot list Ollama models at {settings.ollama_base_url}. Is Ollama running?"
        )

    if model in available_models:
        logger.info("LLM model '%s' available in Ollama", model)
        return model

    logger.warning("Model '%s' not found in Ollama. Attempting to download...", model)
    if pull_ollama_model(model, timeout=900):
        return model

    available_preview = ", ".join(available_models[:5])
    raise ModelNotAvailableError(
        f"Model '{model}' not found in Ollama. "
        f"Available: {available_preview}. "
        f"Run: ollama pull {model}"
    )


def _verify_chat_completions_model(model: str, settings: Settings) -> str:
    try:
        available_models = list_llm_models(settings)
    except Exception as e:
        provider = normalize_llm_provider(settings.llm_provider)
        if provider == "lmstudio":
            raise ModelNotAvailableError(
                "LM Studio is not reachable. Start the local server in LM Studio settings."
            ) from e
        raise ModelNotAvailableError(
            f"Compatible chat server is not reachable at {settings.compatible_base_url}."
        ) from e

    if not available_models:
        logger.warning("Compatible chat server returned no models; using '%s'", model)
        return model
    if model in available_models:
        return model
    raise ModelNotAvailableError(
        f"Model '{model}' is not available. Available models: {', '.join(available_models)}"
    )


def _compatible_headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.compatible_api_key}",
        "Content-Type": "application/json",
    }
