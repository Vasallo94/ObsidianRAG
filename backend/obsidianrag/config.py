"""Centralized configuration for ObsidianRAG using Pydantic Settings"""

import os
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # ========== Paths ==========
    obsidian_path: str = Field(default="", description="Path to Obsidian vault")
    db_path: str = Field(default="", description="Vector database directory (relative to vault)")
    log_path: str = Field(default="", description="Logs directory")
    cache_path: str = Field(default="", description="Embedding cache directory")
    metadata_file: str = Field(default="", description="File metadata tracker")

    # ========== Model Configuration ==========
    # LLM: any Ollama model (gemma3, qwen2.5, llama3.2, mistral, etc.)
    llm_model: str = Field(default="gemma3", description="Ollama LLM model")
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama API URL")

    # Embeddings: default Ollama with embeddinggemma (fast, multilingual)
    embedding_provider: str = Field(
        default="ollama",
        description="Embeddings provider: 'ollama' (recommended) or 'huggingface'",
    )
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        description="HuggingFace embeddings model (fallback)",
    )
    ollama_embedding_model: str = Field(
        default="embeddinggemma",
        description="Ollama embeddings model (default: embeddinggemma)",
    )

    # Reranker configuration
    use_reranker: bool = Field(default=True, description="Enable reranker for better results")
    reranker_model: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        description="Cross-encoder model for reranking (Multilingual)",
    )
    reranker_top_n: int = Field(default=6, description="Number of docs after reranking")

    # ========== Retrieval Configuration ==========
    chunk_size: int = Field(default=1500, description="Text chunk size")
    chunk_overlap: int = Field(default=300, description="Overlap between chunks")
    retrieval_k: int = Field(
        default=12, description="Number of documents to retrieve before reranking"
    )
    bm25_k: int = Field(default=5, description="Number of BM25 results")

    # Ensemble weights
    bm25_weight: float = Field(default=0.4, description="Weight for BM25 retriever")
    vector_weight: float = Field(default=0.6, description="Weight for vector retriever")

    # ========== API Configuration ==========
    api_host: str = Field(default="127.0.0.1", description="FastAPI host")
    api_port: int = Field(default=8000, description="FastAPI port")
    api_reload: bool = Field(default=False, description="Enable auto-reload in development")

    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:8501", "http://localhost:3000", "app://obsidian.md"],
        description="Allowed CORS origins",
    )

    # ========== Feature Flags ==========
    enable_incremental_indexing: bool = Field(
        default=True, description="Enable incremental DB updates"
    )
    enable_analytics: bool = Field(default=True, description="Enable analytics logging")

    # ========== Performance ==========
    max_workers: int = Field(default=4, description="Thread pool max workers")
    request_timeout: int = Field(default=60, description="Request timeout in seconds")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    def configure_paths(self, vault_path: str):
        """Configure paths based on vault location.

        Sets up the database, logs, cache, and metadata paths relative to
        the vault directory in a hidden .obsidianrag folder.
        """
        vault = Path(vault_path)
        data_dir = vault / ".obsidianrag"

        self.obsidian_path = str(vault)
        self.db_path = str(data_dir / "db")
        self.log_path = str(data_dir / "logs")
        self.cache_path = str(data_dir / "cache")
        self.metadata_file = str(data_dir / "metadata.json")

        # Create directories
        os.makedirs(self.db_path, exist_ok=True)
        os.makedirs(self.log_path, exist_ok=True)
        os.makedirs(self.cache_path, exist_ok=True)

    def ensure_directories(self):
        """Create required directories if they don't exist."""
        if self.db_path:
            os.makedirs(self.db_path, exist_ok=True)
        if self.log_path:
            os.makedirs(self.log_path, exist_ok=True)
        if self.cache_path:
            os.makedirs(self.cache_path, exist_ok=True)


# Global settings instance - will be configured at runtime
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def configure_from_vault(vault_path: str) -> Settings:
    """Configure settings from a vault path.

    Args:
        vault_path: Path to the Obsidian vault

    Returns:
        Configured Settings instance
    """
    settings.configure_paths(vault_path)
    return settings
