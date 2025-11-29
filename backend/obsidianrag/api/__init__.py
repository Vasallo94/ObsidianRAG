"""
FastAPI server for ObsidianRAG.

This module provides the HTTP API for the Obsidian plugin
and other clients to interact with the RAG system.
"""

from obsidianrag.api.server import app, create_app

__all__ = ["app", "create_app"]
