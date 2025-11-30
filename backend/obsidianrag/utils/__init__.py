"""Utility functions for ObsidianRAG"""

from obsidianrag.utils.logger import get_logger, setup_logger
from obsidianrag.utils.ollama import (
    ensure_model_available,
    get_available_ollama_models,
    pull_ollama_model,
)

__all__ = [
    "setup_logger",
    "get_logger",
    "pull_ollama_model",
    "get_available_ollama_models",
    "ensure_model_available",
]
