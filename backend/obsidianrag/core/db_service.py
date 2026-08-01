"""Embedding and text-splitting factories for the v4 index."""

import logging

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from obsidianrag.config import get_settings
from obsidianrag.utils.ollama import pull_ollama_model

logger = logging.getLogger(__name__)


def get_embeddings() -> Embeddings:
    """Create the configured embedding model."""
    settings = get_settings()
    if settings.embedding_provider.lower() == "ollama":
        model = settings.ollama_embedding_model
        try:
            import httpx

            response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            available = [item["name"].split(":")[0] for item in response.json().get("models", [])]
            if model not in available and not pull_ollama_model(model, timeout=600):
                raise RuntimeError(
                    f"Ollama embedding model '{model}' is unavailable. Run: ollama pull {model}"
                )
        except RuntimeError:
            raise
        except Exception as error:
            raise RuntimeError(
                f"Could not connect to Ollama at {settings.ollama_base_url}"
            ) from error
        return OllamaEmbeddings(model=model, base_url=settings.ollama_base_url)

    logger.info("Initializing HuggingFace embeddings: %s", settings.embedding_model)
    return HuggingFaceEmbeddings(model_name=settings.embedding_model)


def get_text_splitter() -> RecursiveCharacterTextSplitter:
    """Create the configured Markdown-aware text splitter."""
    settings = get_settings()
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=len,
        separators=["#", "##", "###", "####", "\n\n", "\n", " ", ""],
    )
