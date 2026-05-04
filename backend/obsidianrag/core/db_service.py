"""Database service for vector storage and document management"""

import gc
import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import List, Optional, Set

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from obsidianrag.config import get_settings
from obsidianrag.core.metadata_tracker import FileMetadataTracker
from obsidianrag.utils.ollama import pull_ollama_model

logger = logging.getLogger(__name__)


def extract_obsidian_links(content: str) -> List[str]:
    """Extract Obsidian wikilinks [[Note]] or [[Note|Alias]] from content"""
    links = re.findall(r"\[\[(.*?)\]\]", content)
    cleaned_links = [link.split("|")[0].strip() for link in links]
    seen = set()
    unique_links = []
    for link in cleaned_links:
        if link and link not in seen:
            seen.add(link)
            unique_links.append(link)
    return unique_links


def get_embeddings() -> Embeddings:
    """Get configured embeddings model based on provider setting."""
    settings = get_settings()
    provider = settings.embedding_provider.lower()

    if provider == "ollama":
        model = settings.ollama_embedding_model
        logger.info("Trying to load Ollama embeddings: %s", model)

        try:
            import httpx

            response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            if response.status_code == 200:
                available_models = [
                    m["name"].split(":")[0] for m in response.json().get("models", [])
                ]
                if model not in available_models:
                    logger.warning(
                        "Model '%s' not found in Ollama. Attempting to download...", model
                    )
                    if pull_ollama_model(model, timeout=600):
                        embeddings: Embeddings = OllamaEmbeddings(
                            model=model, base_url=settings.ollama_base_url
                        )
                        logger.info("Ollama embeddings (%s) loaded successfully", model)
                        return embeddings
                    else:
                        raise RuntimeError(
                            f"Failed to download Ollama embedding model '{model}'. "
                            f"Run: ollama pull {model}"
                        )
                else:
                    embeddings = OllamaEmbeddings(model=model, base_url=settings.ollama_base_url)
                    logger.info("Ollama embeddings (%s) loaded successfully", model)
                    return embeddings
            else:
                raise RuntimeError(
                    f"Could not connect to Ollama at {settings.ollama_base_url}. "
                    "Is Ollama running? Run: ollama serve"
                )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"Error connecting to Ollama for embeddings: {e}. "
                "Is Ollama running? Run: ollama serve"
            ) from e

    # HuggingFace provider
    model = settings.embedding_model
    logger.info("Initializing HuggingFace embeddings: %s", model)
    embeddings = HuggingFaceEmbeddings(model_name=model)
    logger.info("HuggingFace embeddings (%s) loaded successfully", model)

    return embeddings


def get_text_splitter() -> RecursiveCharacterTextSplitter:
    """Get configured text splitter"""
    settings = get_settings()
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=len,
        separators=["#", "##", "###", "####", "\n\n", "\n", " ", ""],
    )


def _is_safe_path(filepath: str, vault_path: str) -> bool:
    """Check that a filepath resolves within the vault boundary."""
    try:
        resolved = Path(filepath).resolve()
        vault_resolved = Path(vault_path).resolve()
        return resolved.is_relative_to(vault_resolved)
    except (ValueError, OSError):
        return False


def load_documents_from_paths(filepaths: Set[str]) -> List[Document]:
    """Load documents from specific file paths with link extraction"""
    documents = []

    for filepath in filepaths:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            links = extract_obsidian_links(content)

            doc = Document(
                page_content=content,
                metadata={"source": filepath, "links": ",".join(links) if links else ""},
            )
            documents.append(doc)

            if links:
                logger.debug("Extracted %d links from %s", len(links), filepath)

        except Exception as e:
            logger.warning("Could not load %s: %s", filepath, e)

    logger.info("Loaded %d documents from specified paths", len(documents))
    return documents


def load_all_obsidian_documents(obsidian_path: str) -> List[Document]:
    """Load all documents from Obsidian vault using recursive walk"""
    logger.info("Loading Obsidian documents (.md) recursively")

    EXCLUDED_PATTERNS = [
        ".excalidraw.md",
        ".canvas",
        "untitled",
    ]

    documents = []
    total_files = 0
    loaded_files = 0
    skipped_files = 0
    error_files = 0
    total_links_found = 0

    for root, _, files in os.walk(obsidian_path, followlinks=False):
        for file in files:
            if file.endswith(".md"):
                total_files += 1
                filepath = os.path.join(root, file)

                if not _is_safe_path(filepath, obsidian_path):
                    logger.warning("Skipping file outside vault boundary: %s", filepath)
                    skipped_files += 1
                    continue

                if any(pattern in file.lower() for pattern in EXCLUDED_PATTERNS):
                    skipped_files += 1
                    logger.debug("Skipping excluded file: %s", file)
                    continue

                try:
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        logger.warning("UTF-8 decode failed for %s, trying latin-1", filepath)
                        with open(filepath, "r", encoding="latin-1") as f:
                            content = f.read()

                    if content.strip():
                        links = extract_obsidian_links(content)
                        total_links_found += len(links)

                        doc = Document(
                            page_content=content,
                            metadata={
                                "source": filepath,
                                "links": ",".join(links) if links else "",
                            },
                        )
                        documents.append(doc)
                        loaded_files += 1

                        if len(links) > 5:
                            logger.debug("Note '%s' has %d links: %s...", file, len(links), links[:5])

                except Exception as e:
                    error_files += 1
                    logger.error("Error loading file %s: %s", filepath, e)

    logger.info(
        "Loaded %d of %d notes (%d excluded, %d errors)",
        loaded_files,
        total_files,
        skipped_files,
        error_files,
    )
    logger.info("Total links extracted: %d", total_links_found)
    return documents


def update_db_incrementally(
    db: Chroma, new_files: Set[str], modified_files: Set[str], deleted_files: Set[str]
) -> Chroma:
    """Update database incrementally with only changed files."""
    logger.info("Applying incremental update to database")

    if deleted_files:
        logger.info("Removing %d deleted documents", len(deleted_files))
        for filepath in deleted_files:
            try:
                db.delete(where={"source": filepath})
            except Exception as e:
                logger.warning("Could not delete %s: %s", filepath, e)

    files_to_process = new_files | modified_files

    if files_to_process:
        logger.info("Processing %d new/modified documents", len(files_to_process))

        # For modified files: load new version FIRST, then swap
        for filepath in modified_files:
            try:
                new_docs = load_documents_from_paths({filepath})
                if new_docs:
                    text_splitter = get_text_splitter()
                    new_chunks = text_splitter.split_documents(new_docs)
                    if new_chunks:
                        db.delete(where={"source": filepath})
                        db.add_documents(new_chunks)
                        logger.debug("Updated %s (%d chunks)", filepath, len(new_chunks))
            except Exception as e:
                logger.error("Failed to update %s, keeping old version: %s", filepath, e)

        # Load and chunk new documents
        if new_files:
            documents = load_documents_from_paths(new_files)
            if documents:
                text_splitter = get_text_splitter()
                texts = text_splitter.split_documents(documents)
                logger.info("Created %d text chunks from new files", len(texts))
                if texts:
                    db.add_documents(texts)
                    logger.info("New documents added to database")

    return db


def load_or_create_db(
    obsidian_path: Optional[str] = None, force_rebuild: bool = False
) -> Optional[Chroma]:
    """Load or create vector database with incremental indexing support."""
    settings = get_settings()
    logger.info("Starting vector database load or creation")

    if not obsidian_path:
        obsidian_path = settings.obsidian_path

    if not obsidian_path:
        raise ValueError("OBSIDIAN_PATH must be set in environment or settings")

    embeddings = get_embeddings()
    persist_directory = settings.db_path

    if (
        os.path.exists(persist_directory)
        and not force_rebuild
        and settings.enable_incremental_indexing
    ):
        logger.info("Checking for changes for incremental update")
        tracker = FileMetadataTracker(settings.metadata_file)

        should_rebuild, changes = tracker.should_rebuild_with_changes(obsidian_path)
        if should_rebuild:
            logger.warning("Too many changes detected, doing full rebuild")
            force_rebuild = True
        else:
            new_files, modified_files, deleted_files = changes

            if not new_files and not modified_files and not deleted_files:
                logger.info("No changes, loading existing database")
                db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
                return db

            logger.info("Performing incremental update")
            db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
            db = update_db_incrementally(db, new_files, modified_files, deleted_files)

            tracker.update_metadata(obsidian_path)

            return db

    if force_rebuild:
        logger.info("Forcing full database rebuild")

    documents = load_all_obsidian_documents(obsidian_path)

    if not documents:
        logger.warning("No documents loaded. Check the path and files")
        return None

    logger.info("Splitting documents into chunks")
    text_splitter = get_text_splitter()
    texts = text_splitter.split_documents(documents)
    logger.info("Created %d text chunks", len(texts))

    if force_rebuild and os.path.exists(persist_directory):
        temp_dir = f"{persist_directory}_{uuid.uuid4().hex}"
        logger.info("Creating new database in temporary directory: %s", temp_dir)

        try:
            temp_db = Chroma.from_documents(
                texts,
                embeddings,
                persist_directory=temp_dir,
                collection_metadata={"hnsw:space": "cosine"},
            )

            del temp_db
            gc.collect()

            logger.info("Removing old directory: %s", persist_directory)
            shutil.rmtree(persist_directory)

            logger.info("Moving %s to %s", temp_dir, persist_directory)
            os.rename(temp_dir, persist_directory)

            db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
            logger.info("Database rebuilt and loaded successfully")

        except Exception as e:
            logger.error("Error during atomic rebuild: %s", e)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise e
    else:
        logger.info("Creating new vector database")
        db = Chroma.from_documents(
            texts,
            embeddings,
            persist_directory=persist_directory,
            collection_metadata={"hnsw:space": "cosine"},
        )
        logger.info("Vector database created successfully")

    if settings.enable_incremental_indexing:
        tracker = FileMetadataTracker(settings.metadata_file)
        tracker.update_metadata(obsidian_path)
        logger.info("Metadata tracker updated")

    return db
