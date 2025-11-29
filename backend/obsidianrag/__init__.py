"""
ObsidianRAG - RAG system for querying Obsidian notes using LangGraph and local LLMs.

Usage:
    # As a library
    from obsidianrag import ObsidianRAG
    
    rag = ObsidianRAG(vault_path="/path/to/vault")
    answer = rag.ask("What are my notes about Python?")
    
    # As a CLI
    $ obsidianrag serve --vault /path/to/vault
    $ obsidianrag index --vault /path/to/vault
    $ obsidianrag status
"""

__version__ = "3.0.0"
__author__ = "Enrique Vasallo"

from obsidianrag.core.rag import ObsidianRAG

__all__ = ["ObsidianRAG", "__version__"]
