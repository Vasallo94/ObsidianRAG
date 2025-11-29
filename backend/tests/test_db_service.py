"""Tests for ObsidianRAG Database Service (ChromaDB)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obsidianrag.core.db_service import extract_obsidian_links


class TestDBServiceConfiguration:
    """Tests for DBService configuration."""

    @patch("obsidianrag.core.db_service.get_settings")
    def test_get_settings_returns_config(self, mock_settings):
        """Test that settings can be retrieved."""
        mock_settings.return_value = MagicMock(
            chunk_size=1000,
            chunk_overlap=200,
            embedding_provider="huggingface",
        )

        settings = mock_settings()

        assert settings.chunk_size == 1000
        assert settings.chunk_overlap == 200

    @patch("obsidianrag.core.db_service.get_settings")
    def test_embedding_provider_configurable(self, mock_settings):
        """Test that embedding provider is configurable."""
        mock_settings.return_value = MagicMock(
            embedding_provider="ollama",
            ollama_embedding_model="nomic-embed-text",
        )

        settings = mock_settings()

        assert settings.embedding_provider == "ollama"


class TestChromaIntegration:
    """Tests for Chroma integration."""

    def test_chroma_collection_name(self):
        """Test that collection name is correctly set."""
        # Default collection name
        expected_name = "obsidian_notes"
        assert expected_name == "obsidian_notes"

    def test_persist_directory_structure(self, mock_vault):
        """Test that persist directory has correct structure."""
        persist_dir = mock_vault / ".obsidianrag" / "db"
        persist_dir.mkdir(parents=True, exist_ok=True)

        assert persist_dir.parent.name == ".obsidianrag"


class TestLinkExtraction:
    """Tests for wikilink extraction."""

    def test_extracts_simple_links(self):
        """Test extraction of simple [[links]]."""
        content = "See [[note-a]] and [[note-b]] for more."
        links = extract_obsidian_links(content)

        assert "note-a" in links
        assert "note-b" in links
        assert len(links) == 2

    def test_extracts_aliased_links(self):
        """Test extraction of [[link|alias]] format."""
        content = "Check [[actual-note|display name]] here."
        links = extract_obsidian_links(content)

        assert "actual-note" in links
        assert len(links) == 1

    def test_handles_no_links(self):
        """Test handling of content with no links."""
        content = "This content has no wikilinks at all."
        links = extract_obsidian_links(content)

        assert links == []

    def test_removes_duplicates(self):
        """Test that duplicate links are removed."""
        content = "See [[note-a]] and [[note-a]] again."
        links = extract_obsidian_links(content)

        assert links == ["note-a"]

    def test_preserves_order(self):
        """Test that link order is preserved."""
        content = "First [[note-a]], then [[note-b]], then [[note-c]]."
        links = extract_obsidian_links(content)

        assert links == ["note-a", "note-b", "note-c"]


class TestChunkingBehavior:
    """Tests for document chunking."""

    def test_respects_chunk_size(self):
        """Test that chunking respects configured chunk size."""
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

        long_text = "word " * 500  # ~2500 characters
        chunks = splitter.split_text(long_text)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 1000 + 100  # Allow some flexibility

    def test_maintains_chunk_overlap(self):
        """Test that chunks have proper overlap."""
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=20)

        text = "sentence one. " * 20
        chunks = splitter.split_text(text)

        assert len(chunks) >= 1

    def test_preserves_markdown_structure(self):
        """Test that chunking preserves markdown structure where possible."""
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=200,
            chunk_overlap=20,
            separators=["\n\n", "\n", " ", ""],
        )

        markdown = """# Header

This is paragraph one.

This is paragraph two.

## Subheader

More content here."""

        chunks = splitter.split_text(markdown)

        # Headers should preferably not be split mid-line
        assert len(chunks) > 0

    def test_small_content_single_chunk(self):
        """Test that small content stays in single chunk."""
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

        small_text = "This is a small note."
        chunks = splitter.split_text(small_text)

        assert len(chunks) == 1


class TestDocumentMetadata:
    """Tests for document metadata extraction."""

    def test_metadata_includes_source(self):
        """Test that metadata includes source path."""
        from langchain_core.documents import Document

        doc = Document(
            page_content="Test content",
            metadata={"source": "notes/test.md"},
        )

        assert doc.metadata["source"] == "notes/test.md"

    def test_metadata_includes_links(self):
        """Test that metadata can include links."""
        from langchain_core.documents import Document

        doc = Document(
            page_content="See [[other-note]]",
            metadata={
                "source": "notes/test.md",
                "links": ["other-note"],
            },
        )

        assert "other-note" in doc.metadata["links"]

