"""Main ObsidianRAG class - high-level interface for the RAG system"""

import logging
from typing import List, Optional, Tuple

from langchain_core.documents import Document

from obsidianrag.config import Settings, configure_from_vault
from obsidianrag.core.db_service import load_or_create_db
from obsidianrag.core.qa_agent import ask_question_graph, create_qa_graph

logger = logging.getLogger(__name__)


class ObsidianRAG:
    """High-level interface for querying Obsidian notes with RAG.

    Example:
        >>> from obsidianrag import ObsidianRAG
        >>> rag = ObsidianRAG(vault_path="/path/to/vault")
        >>> answer, sources = rag.ask("What are my notes about Python?")
        >>> print(answer)
    """

    def __init__(
        self, vault_path: str, settings: Optional[Settings] = None, auto_index: bool = True
    ):
        """Initialize ObsidianRAG.

        Args:
            vault_path: Path to the Obsidian vault
            settings: Optional custom settings (uses defaults if None)
            auto_index: Whether to automatically index the vault on init
        """
        self.vault_path = vault_path

        # Configure settings
        if settings:
            self._settings = settings
        else:
            self._settings = configure_from_vault(vault_path)

        self._db = None
        self._graph = None
        self._chat_history: List[Tuple[str, str]] = []

        if auto_index:
            self.index()

    @property
    def settings(self) -> Settings:
        """Get the current settings."""
        return self._settings

    @property
    def is_ready(self) -> bool:
        """Check if the RAG system is ready to answer questions."""
        return self._db is not None and self._graph is not None

    def index(self, force_rebuild: bool = False) -> "ObsidianRAG":
        """Index or re-index the Obsidian vault.

        Args:
            force_rebuild: If True, rebuild the entire index from scratch

        Returns:
            Self for method chaining
        """
        logger.info(f"Indexing vault: {self.vault_path}")
        self._db = load_or_create_db(self.vault_path, force_rebuild=force_rebuild)

        if self._db:
            logger.info("Creating QA graph...")
            self._graph = create_qa_graph(self._db)
            logger.info("✅ ObsidianRAG ready")
        else:
            logger.error("❌ Failed to load database")

        return self

    def ask(self, question: str, use_history: bool = True) -> Tuple[str, List[Document]]:
        """Ask a question about the Obsidian notes.

        Args:
            question: The question to ask
            use_history: Whether to include chat history for context

        Returns:
            Tuple of (answer, source_documents)

        Raises:
            RuntimeError: If the system is not ready
        """
        if not self.is_ready:
            raise RuntimeError("ObsidianRAG not ready. Call index() first.")

        history = self._chat_history if use_history else []
        answer, sources = ask_question_graph(self._graph, question, history)

        # Update history
        self._chat_history.append((question, answer))

        return answer, sources

    def clear_history(self) -> "ObsidianRAG":
        """Clear the chat history.

        Returns:
            Self for method chaining
        """
        self._chat_history = []
        return self

    def get_stats(self) -> dict:
        """Get statistics about the indexed vault.

        Returns:
            Dictionary with vault statistics
        """
        if not self._db:
            return {"error": "Database not loaded"}

        try:
            db_data = self._db.get()
            documents = db_data.get("documents", [])
            metadatas = db_data.get("metadatas", [])

            total_chunks = len(documents)
            total_chars = sum(len(doc) for doc in documents)
            total_words = sum(len(doc.split()) for doc in documents)

            sources = set()
            folders = set()
            links = set()

            for meta in metadatas:
                source = meta.get("source", "")
                if source:
                    sources.add(source)
                    parts = source.split("/")
                    if len(parts) > 1:
                        folders.add(parts[-2])

                links_str = meta.get("links", "")
                if links_str:
                    for link in links_str.split(","):
                        if link.strip():
                            links.add(link.strip())

            return {
                "total_notes": len(sources),
                "total_chunks": total_chunks,
                "total_words": total_words,
                "total_chars": total_chars,
                "avg_words_per_chunk": total_words // total_chunks if total_chunks > 0 else 0,
                "folders": len(folders),
                "internal_links": len(links),
                "vault_path": self.vault_path,
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}
