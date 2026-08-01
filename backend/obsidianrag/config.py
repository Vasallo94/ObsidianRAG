"""Centralized configuration for ObsidianRAG using Pydantic Settings"""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    model_config = SettingsConfigDict(
        env_prefix="OBSIDIANRAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ========== Paths ==========
    obsidian_path: str = Field(default="", description="Path to Obsidian vault")

    # ========== Model Configuration ==========
    llm_provider: Literal["ollama", "lmstudio", "custom"] = Field(
        default="ollama",
        description="LLM runtime preset: 'ollama', 'lmstudio', or 'custom'",
    )
    llm_api_format: Literal["ollama", "chat-completions"] = Field(
        default="ollama",
        description="LLM API format used by the provider adapter",
    )
    llm_model: str = Field(default="gemma4:31b", description="LLM model name")
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Generation temperature; zero reduces variance and is recommended for RAG",
    )
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama API URL")
    compatible_base_url: str = Field(
        default="http://localhost:1234/v1",
        description="Base URL for chat-completions compatible APIs (LM Studio defaults to http://localhost:1234/v1)",
    )
    compatible_api_key: str = Field(
        default="lm-studio",
        description="API key for compatible providers when required (LM Studio accepts any value)",
    )

    # Embeddings
    embedding_provider: str = Field(
        default="ollama",
        description="Embeddings provider: 'ollama' (recommended) or 'huggingface'",
    )
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        description="HuggingFace embeddings model (fallback)",
    )
    ollama_embedding_model: str = Field(
        default="qwen3-embedding",
        description="Ollama embeddings model",
    )

    # ========== Retrieval Configuration ==========
    chunk_size: int = Field(default=1500, description="Text chunk size")
    chunk_overlap: int = Field(default=300, description="Overlap between chunks")
    # ========== API Configuration ==========
    api_host: str = Field(default="127.0.0.1", description="FastAPI host")
    api_port: int = Field(default=8000, description="FastAPI port")
    api_reload: bool = Field(default=False, description="Enable auto-reload in development")

    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:8501", "http://localhost:3000", "app://obsidian.md"],
        description="Allowed CORS origins",
    )

    # ========== Performance ==========
    max_workers: int = Field(default=4, description="Thread pool max workers")
    request_timeout: int = Field(default=60, description="Request timeout in seconds")

    def configure_paths(self, vault_path: str) -> None:
        """Configure the vault without creating index data."""
        self.obsidian_path = str(Path(vault_path))


# Global settings remain the default for CLI and library callers.
settings = Settings()
_settings_override: ContextVar[Settings | None] = ContextVar(
    "obsidianrag_settings_override", default=None
)


def get_settings() -> Settings:
    """Get the current app-scoped settings, or the legacy global default."""
    return _settings_override.get() or settings


@contextmanager
def settings_override(value: Settings) -> Iterator[None]:
    """Use isolated settings for the current async/thread context."""
    token = _settings_override.set(value)
    try:
        yield
    finally:
        _settings_override.reset(token)


def configure_from_vault(vault_path: str) -> Settings:
    """Configure settings from a vault path.

    Args:
        vault_path: Path to the Obsidian vault

    Returns:
        Configured Settings instance
    """
    settings.configure_paths(vault_path)
    return settings
