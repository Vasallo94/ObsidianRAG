"""Ollama utility functions for model management"""

import logging
import subprocess
from typing import List

logger = logging.getLogger(__name__)


def get_available_ollama_models(base_url: str = "http://localhost:11434") -> List[str]:
    """Get list of available models in Ollama.

    Args:
        base_url: Ollama API base URL

    Returns:
        List of model names (without tags)
    """
    try:
        import httpx

        response = httpx.get(f"{base_url}/api/tags", timeout=5.0)
        if response.status_code == 200:
            return [m["name"].split(":")[0] for m in response.json().get("models", [])]
    except Exception as e:
        logger.warning(f"Could not get Ollama models: {e}")
    return []


def pull_ollama_model(model: str, timeout: int = 600) -> bool:
    """Pull an Ollama model if not available.

    Args:
        model: Model name to pull
        timeout: Timeout in seconds (default 10 min for embeddings, use 900 for large LLMs)

    Returns:
        True if model was pulled successfully, False on error
    """
    logger.info(f"📥 Downloading Ollama model: {model}...")
    try:
        result = subprocess.run(
            ["ollama", "pull", model], capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            logger.info(f"✅ Model '{model}' downloaded successfully")
            return True
        else:
            logger.error(f"❌ Failed to pull model: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"❌ Timeout pulling model '{model}' (>{timeout // 60} min)")
        return False
    except FileNotFoundError:
        logger.error("❌ Ollama CLI not found. Please install Ollama first.")
        return False
    except Exception as e:
        logger.error(f"❌ Error pulling model: {e}")
        return False


def ensure_model_available(
    model: str, base_url: str = "http://localhost:11434", timeout: int = 600
) -> bool:
    """Ensure a model is available in Ollama, downloading if necessary.

    Args:
        model: Model name to ensure
        base_url: Ollama API base URL
        timeout: Download timeout in seconds

    Returns:
        True if model is available, False otherwise
    """
    available = get_available_ollama_models(base_url)

    if model in available:
        logger.debug(f"✅ Model '{model}' already available")
        return True

    logger.info(f"⚠️ Model '{model}' not found. Downloading...")
    return pull_ollama_model(model, timeout)
