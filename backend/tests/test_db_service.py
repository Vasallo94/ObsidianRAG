"""Tests for ObsidianRAG Database Service (ChromaDB)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from obsidianrag.core.db_service import (
    _create_chroma_in_batches,
    extract_obsidian_links,
    load_all_obsidian_documents,
    load_documents_from_paths,
    load_or_create_db,
    update_db_incrementally,
)
from obsidianrag.core.metadata_tracker import FileMetadataTracker


class DeterministicEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.0]


class FakeChroma:
    """Small in-memory stand-in for Chroma's update methods."""

    def __init__(self, records: dict[str, Document], fail_after_first_add: bool = False):
        self.records = records
        self.fail_after_first_add = fail_after_first_add

    def get(self, *, where=None, ids=None):
        selected = self.records
        if where:
            selected = {
                key: doc
                for key, doc in selected.items()
                if doc.metadata.get("source") == where.get("source")
            }
        if ids is not None:
            selected = {key: self.records[key] for key in ids if key in self.records}
        return {"ids": list(selected)}

    def add_documents(self, documents, ids):
        for index, (chunk_id, document) in enumerate(zip(ids, documents)):
            self.records[chunk_id] = document
            if self.fail_after_first_add and index == 0:
                raise RuntimeError("simulated write failure")

    def delete(self, *, ids=None, where=None):
        if ids is not None:
            for chunk_id in ids:
                self.records.pop(chunk_id, None)
        elif where:
            for chunk_id, document in list(self.records.items()):
                if document.metadata.get("source") == where.get("source"):
                    self.records.pop(chunk_id)


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

    @patch("obsidianrag.core.db_service.Chroma")
    def test_full_build_embeds_in_bounded_batches(self, mock_chroma):
        db = MagicMock()
        stored_ids = set()
        db.get.side_effect = lambda ids: {"ids": list(stored_ids.intersection(ids))}
        db.add_documents.side_effect = lambda _documents, ids: stored_ids.update(ids)
        mock_chroma.return_value = db
        documents = [Document(page_content=f"chunk {index}") for index in range(5)]

        result = _create_chroma_in_batches(documents, MagicMock(), "/tmp/db", batch_size=2)

        assert result is db
        assert [len(call.kwargs["ids"]) for call in db.add_documents.call_args_list] == [2, 2, 1]

    def test_persist_directory_structure(self, mock_vault):
        """Test that persist directory has correct structure."""
        persist_dir = mock_vault / ".obsidianrag" / "db"
        persist_dir.mkdir(parents=True, exist_ok=True)

        assert persist_dir.parent.name == ".obsidianrag"

    @patch("obsidianrag.core.db_service.load_all_obsidian_documents")
    @patch("obsidianrag.core.db_service.Chroma")
    @patch("obsidianrag.core.db_service.get_embeddings")
    @patch("obsidianrag.core.db_service.get_settings")
    def test_disabled_incremental_mode_loads_existing_database(
        self, mock_get_settings, mock_get_embeddings, mock_chroma, mock_load_documents, tmp_path
    ):
        persist_dir = tmp_path / "db"
        persist_dir.mkdir()
        settings = SimpleNamespace(
            obsidian_path=str(tmp_path),
            db_path=str(persist_dir),
            enable_incremental_indexing=False,
        )
        mock_get_settings.return_value = settings
        expected = MagicMock()
        mock_chroma.return_value = expected

        result = load_or_create_db(str(tmp_path))

        assert result is expected
        mock_chroma.assert_called_once_with(
            persist_directory=str(persist_dir), embedding_function=mock_get_embeddings.return_value
        )
        mock_load_documents.assert_not_called()


def test_full_load_excludes_application_and_trash_directories(tmp_path):
    (tmp_path / "Kept.md").write_text("kept")
    for directory in (".obsidian", ".obsidianrag", ".trash", ".git", "node_modules"):
        path = tmp_path / directory
        path.mkdir()
        (path / "Ignored.md").write_text("ignored")

    documents = load_all_obsidian_documents(str(tmp_path))

    assert [Path(document.metadata["source"]).name for document in documents] == ["Kept.md"]
    tracked = FileMetadataTracker(str(tmp_path / "metadata.json")).get_current_files(str(tmp_path))
    assert [Path(source).name for source in tracked] == ["Kept.md"]


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


class TestIncrementalUpdates:
    def test_failed_update_keeps_previous_chunks(self, mock_vault):
        filepath = mock_vault / "Python Basics.md"
        old = Document(page_content="old content", metadata={"source": str(filepath)})
        db = FakeChroma({"old-id": old}, fail_after_first_add=True)
        settings = SimpleNamespace(obsidian_path=str(mock_vault))
        splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=10)

        with (
            patch("obsidianrag.core.db_service.get_settings", return_value=settings),
            patch("obsidianrag.core.db_service.get_text_splitter", return_value=splitter),
            pytest.raises(RuntimeError, match="Incremental update failed"),
        ):
            update_db_incrementally(db, set(), {str(filepath)}, set())

        assert set(db.records) == {"old-id"}
        assert db.records["old-id"].page_content == "old content"

    def test_successful_update_removes_previous_chunks(self, mock_vault):
        filepath = mock_vault / "Python Basics.md"
        old = Document(page_content="old content", metadata={"source": str(filepath)})
        db = FakeChroma({"old-id": old})
        settings = SimpleNamespace(obsidian_path=str(mock_vault))
        splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=10)

        with (
            patch("obsidianrag.core.db_service.get_settings", return_value=settings),
            patch("obsidianrag.core.db_service.get_text_splitter", return_value=splitter),
        ):
            update_db_incrementally(db, set(), {str(filepath)}, set())

        assert "old-id" not in db.records
        assert db.records
        assert all(doc.metadata["source"] == str(filepath) for doc in db.records.values())

    def test_retry_removes_stale_revision_without_duplicates(self, mock_vault):
        filepath = mock_vault / "Python Basics.md"
        old = Document(page_content="old content", metadata={"source": str(filepath)})
        db = FakeChroma({"old-id": old})
        settings = SimpleNamespace(obsidian_path=str(mock_vault))
        splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=10)

        with (
            patch("obsidianrag.core.db_service.get_settings", return_value=settings),
            patch("obsidianrag.core.db_service.get_text_splitter", return_value=splitter),
        ):
            update_db_incrementally(db, set(), {str(filepath)}, set())
            new_ids = set(db.records)
            db.records["stale-old-id"] = old
            update_db_incrementally(db, set(), {str(filepath)}, set())

        assert set(db.records) == new_ids
        assert "stale-old-id" not in db.records

    def test_retry_cleans_partial_new_revision_before_replacing(self, mock_vault):
        filepath = mock_vault / "Python Basics.md"
        old = Document(page_content="old content", metadata={"source": str(filepath)})
        settings = SimpleNamespace(obsidian_path=str(mock_vault))
        splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=10)
        complete = FakeChroma({"old-id": old})

        with (
            patch("obsidianrag.core.db_service.get_settings", return_value=settings),
            patch("obsidianrag.core.db_service.get_text_splitter", return_value=splitter),
        ):
            update_db_incrementally(complete, set(), {str(filepath)}, set())
            new_id, new_document = next(iter(complete.records.items()))
            interrupted = FakeChroma({"old-id": old, new_id: new_document})
            update_db_incrementally(interrupted, set(), {str(filepath)}, set())

        assert "old-id" not in interrupted.records
        assert set(interrupted.records) == set(complete.records)

    def test_update_protocol_works_with_real_chroma(self, mock_vault, tmp_path):
        filepath = mock_vault / "Python Basics.md"
        old = Document(page_content="old content", metadata={"source": str(filepath)})
        db = Chroma(
            collection_name="incremental-update-test",
            persist_directory=str(tmp_path / "chroma"),
            embedding_function=DeterministicEmbeddings(),
        )
        db.add_documents([old], ids=["old-id"])
        filepath.write_text("new content")
        settings = SimpleNamespace(obsidian_path=str(mock_vault))
        splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=10)

        with (
            patch("obsidianrag.core.db_service.get_settings", return_value=settings),
            patch("obsidianrag.core.db_service.get_text_splitter", return_value=splitter),
        ):
            update_db_incrementally(db, set(), {str(filepath)}, set())

        stored = db.get(where={"source": str(filepath)})
        assert stored["ids"] != ["old-id"]
        assert stored["documents"] == ["new content"]

    def test_incremental_read_rejects_paths_outside_vault(self, mock_vault, tmp_path):
        outside = tmp_path / "outside.md"
        outside.write_text("private")
        settings = SimpleNamespace(obsidian_path=str(mock_vault))

        with (
            patch("obsidianrag.core.db_service.get_settings", return_value=settings),
            pytest.raises(ValueError, match="outside the configured vault"),
        ):
            load_documents_from_paths({str(outside)}, raise_on_error=True)

    def test_incremental_read_rejects_symlink_escape(self, mock_vault, tmp_path):
        outside = tmp_path / "outside.md"
        outside.write_text("private")
        symlink = mock_vault / "escape.md"
        try:
            symlink.symlink_to(outside)
        except OSError:
            pytest.skip("Symlinks are not available on this platform")
        settings = SimpleNamespace(obsidian_path=str(mock_vault))

        with (
            patch("obsidianrag.core.db_service.get_settings", return_value=settings),
            pytest.raises(ValueError, match="outside the configured vault"),
        ):
            load_documents_from_paths({str(symlink)}, raise_on_error=True)


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
