"""Centralized configuration for ObsidianRAG using Pydantic Settings"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # ========== Paths ==========
    obsidian_path: str = Field(..., description="Path to Obsidian vault")
    db_path: str = Field(default="db", description="Vector database directory")
    log_path: str = Field(default="logs", description="Logs directory")
    cache_path: str = Field(default="db/cache", description="Embedding cache directory")
    metadata_file: str = Field(default="db/metadata.json", description="File metadata tracker")
    
    # ========== Model Configuration ==========
    llm_model: str = Field(default="qwen2.5", description="Ollama LLM model name")
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama API base URL")
    
    # Embedding configuration
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        description="HuggingFace embedding model"
    )
    
    # Reranker configuration
    use_reranker: bool = Field(default=True, description="Enable reranker for better results")
    reranker_model: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        description="Cross-encoder model for reranking (Multilingual)"
    )
    reranker_top_n: int = Field(default=3, description="Number of docs after reranking")
    
    # ========== Retrieval Configuration ==========
    chunk_size: int = Field(default=800, description="Text chunk size")
    chunk_overlap: int = Field(default=200, description="Overlap between chunks")
    retrieval_k: int = Field(default=8, description="Number of documents to retrieve")
    bm25_k: int = Field(default=3, description="Number of BM25 results")
    
    # Ensemble weights
    bm25_weight: float = Field(default=0.5, description="Weight for BM25 retriever")
    vector_weight: float = Field(default=0.5, description="Weight for vector retriever")
    
    # ========== API Configuration ==========
    api_host: str = Field(default="0.0.0.0", description="FastAPI host")
    api_port: int = Field(default=8000, description="FastAPI port")
    api_reload: bool = Field(default=False, description="Enable auto-reload in development")
    
    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:8501", "http://localhost:3000"],
        description="Allowed CORS origins"
    )
    
    # ========== Feature Flags ==========
    enable_streaming: bool = Field(default=True, description="Enable streaming responses")
    enable_incremental_indexing: bool = Field(default=True, description="Enable incremental DB updates")
    enable_analytics: bool = Field(default=True, description="Enable analytics logging")
    
    # ========== Performance ==========
    max_workers: int = Field(default=4, description="Thread pool max workers")
    request_timeout: int = Field(default=60, description="Request timeout in seconds")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        os.makedirs(self.db_path, exist_ok=True)
        os.makedirs(self.log_path, exist_ok=True)
        os.makedirs(self.cache_path, exist_ok=True)


# Global settings instance
settings = Settings()
