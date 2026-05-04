"""QA Service with hybrid search and reranking"""

import logging
from typing import List, cast

from langchain_classic.retrievers import (
    ContextualCompressionRetriever,
    EnsembleRetriever,
)
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from obsidianrag.config import get_settings

logger = logging.getLogger(__name__)


class RAGError(Exception):
    """Base exception for RAG-related errors"""

    pass


class ModelNotAvailableError(RAGError):
    """LLM model is not available"""

    pass


class NoDocumentsFoundError(RAGError):
    """No documents found in database or retrieval"""

    pass


def verify_ollama_available():
    """Verify that Ollama is running and accessible"""
    settings = get_settings()
    try:
        import requests

        response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
        response.raise_for_status()
        logger.info("Ollama is available")
    except Exception as e:
        logger.error("Ollama is not available: %s", e)
        raise ModelNotAvailableError(
            f"Ollama is not running at {settings.ollama_base_url}. Run: ollama serve"
        )


def create_hybrid_retriever(db):
    """Create a hybrid retriever with BM25 + Vector search."""
    settings = get_settings()
    logger.info("=" * 50)
    logger.info("Configuring Hybrid Search (BM25 + Vector)")
    logger.info("=" * 50)

    try:
        db_data = db.get()
        texts = db_data["documents"]
        metadatas = db_data["metadatas"]

        if not texts:
            logger.warning("No documents found in DB")
            raise NoDocumentsFoundError("Database is empty")

        docs_with_links = sum(1 for m in metadatas if m.get("links", ""))
        total_links = sum(
            len(m.get("links", "").split(",")) for m in metadatas if m.get("links", "")
        )
        logger.info(
            "DB Stats: %d chunks, %d with links, %d total links",
            len(texts),
            docs_with_links,
            total_links,
        )

        docs = [Document(page_content=t, metadata=m) for t, m in zip(texts, metadatas)]
        bm25_retriever = BM25Retriever.from_documents(docs)
        bm25_retriever.k = settings.bm25_k
        logger.info("   BM25 k=%d", settings.bm25_k)

        chroma_retriever = db.as_retriever(search_kwargs={"k": settings.retrieval_k})
        logger.info("   Vector k=%d", settings.retrieval_k)

        ensemble_retriever = EnsembleRetriever(
            retrievers=[bm25_retriever, chroma_retriever],
            weights=[settings.bm25_weight, settings.vector_weight],
        )
        logger.info(
            "   Ensemble weights: BM25=%.1f, Vector=%.1f",
            settings.bm25_weight,
            settings.vector_weight,
        )

        logger.info("EnsembleRetriever created successfully")
        return ensemble_retriever

    except NoDocumentsFoundError:
        raise
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Error creating hybrid retriever: %s. Using only Vector Search", e)
        return db.as_retriever(search_kwargs={"k": settings.retrieval_k})


def create_retriever_with_reranker(db):
    """Create a retriever with optional reranking."""
    settings = get_settings()
    ensemble_retriever = create_hybrid_retriever(db)

    if settings.use_reranker:
        logger.info("Adding reranker: %s", settings.reranker_model)
        logger.info("   Reranker top_n=%d", settings.reranker_top_n)
        try:
            model = HuggingFaceCrossEncoder(model_name=settings.reranker_model)
            compressor = CrossEncoderReranker(model=model, top_n=settings.reranker_top_n)

            retriever = ContextualCompressionRetriever(
                base_compressor=compressor, base_retriever=ensemble_retriever
            )
            logger.info("Reranker configured successfully")
            logger.info("=" * 50)
            return retriever
        except (OSError, ImportError) as e:
            logger.error("Could not configure reranker: %s. Using ensemble without reranker", e)
            return ensemble_retriever
    else:
        logger.info("Reranker disabled in configuration")
        return ensemble_retriever


def retrieve_with_links(retriever, query: str) -> List[Document]:
    """Retrieve documents and their linked references (GraphRAG)"""
    docs = retriever.invoke(query)

    linked_sources = set()
    for doc in docs:
        links_str = doc.metadata.get("links", "")
        if links_str:
            for link in links_str.split(","):
                if link.strip():
                    linked_sources.add(link.strip())

    if linked_sources:
        logger.info("GraphRAG: Found %d linked notes", len(linked_sources))

    return cast(List[Document], docs)
