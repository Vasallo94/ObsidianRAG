"""Database service for vector storage and document management"""

import gc
import logging
import os
import re
import shutil
import uuid
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
    # Clean links (remove alias like [[Note|Alias]] -> Note)
    cleaned_links = [link.split("|")[0].strip() for link in links]
    # Remove duplicates while preserving order
    seen = set()
    unique_links = []
    for link in cleaned_links:
        if link and link not in seen:
            seen.add(link)
            unique_links.append(link)
    return unique_links


def get_embeddings() -> Embeddings:
    """Get configured embeddings model based on provider setting.

    Automatically downloads the model if not available in Ollama.
    Falls back to HuggingFace if download fails.
    """
    settings = get_settings()
    provider = settings.embedding_provider.lower()

    if provider == "ollama":
        model = settings.ollama_embedding_model
        logger.info(f"Trying to load Ollama embeddings: {model}")

        # Check if model is available in Ollama
        try:
            import httpx

            response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            if response.status_code == 200:
                available_models = [
                    m["name"].split(":")[0] for m in response.json().get("models", [])
                ]
                if model not in available_models:
                    logger.warning(
                        f"⚠️ Model '{model}' not found in Ollama. Attempting to download..."
                    )
                    # Try to pull the model automatically (10 min timeout for embeddings)
                    if pull_ollama_model(model, timeout=600):
                        embeddings = OllamaEmbeddings(
                            model=model, base_url=settings.ollama_base_url
                        )
                        logger.info(f"✅ Ollama embeddings ({model}) loaded successfully")
                        return embeddings
                    else:
                        logger.warning("🔄 Falling back to HuggingFace embeddings...")
                        provider = "huggingface"  # Fallback
                else:
                    embeddings = OllamaEmbeddings(model=model, base_url=settings.ollama_base_url)
                    logger.info(f"✅ Ollama embeddings ({model}) loaded successfully")
                    return embeddings
            else:
                logger.warning("⚠️ Could not connect to Ollama. Falling back to HuggingFace...")
                provider = "huggingface"
        except Exception as e:
            logger.warning(f"⚠️ Error checking Ollama: {e}. Falling back to HuggingFace...")
            provider = "huggingface"

    # Default: HuggingFace (or fallback)
    model = settings.embedding_model
    logger.info(f"Initializing HuggingFace embeddings: {model}")
    embeddings = HuggingFaceEmbeddings(model_name=model)
    logger.info(f"✅ HuggingFace embeddings ({model}) loaded successfully")

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


def load_documents_from_paths(filepaths: Set[str]) -> List[Document]:
    """Load documents from specific file paths with link extraction"""
    documents = []

    for filepath in filepaths:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract Obsidian links
            links = extract_obsidian_links(content)

            doc = Document(
                page_content=content,
                metadata={"source": filepath, "links": ",".join(links) if links else ""},
            )
            documents.append(doc)

            if links:
                logger.debug(f"Extracted {len(links)} links from {filepath}")

        except Exception as e:
            logger.warning(f"Could not load {filepath}: {e}")

    logger.info(f"Loaded {len(documents)} documents from specified paths")
    return documents


def load_all_obsidian_documents(obsidian_path: str) -> List[Document]:
    """Load all documents from Obsidian vault using recursive walk"""
    logger.info("Loading Obsidian documents (.md) recursively")

    # File patterns to exclude (binary, canvas, etc.)
    EXCLUDED_PATTERNS = [
        ".excalidraw.md",  # Excalidraw drawings (base64)
        ".canvas",  # Canvas files
        "untitled",  # Untitled files
    ]

    documents = []
    total_files = 0
    loaded_files = 0
    skipped_files = 0
    total_links_found = 0

    for root, _, files in os.walk(obsidian_path):
        for file in files:
            if file.endswith(".md"):
                total_files += 1
                filepath = os.path.join(root, file)

                # Skip excluded patterns
                if any(pattern in file.lower() for pattern in EXCLUDED_PATTERNS):
                    skipped_files += 1
                    logger.debug(f"Skipping excluded file: {file}")
                    continue

                try:
                    # Try UTF-8 first
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        # Fallback to latin-1
                        logger.warning(f"UTF-8 decode failed for {filepath}, trying latin-1")
                        with open(filepath, "r", encoding="latin-1") as f:
                            content = f.read()

                    if content.strip():  # Skip empty files
                        # Extract links using centralized function
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

                        # Debug logging for files with many links
                        if len(links) > 5:
                            logger.debug(f"Note '{file}' has {len(links)} links: {links[:5]}...")

                except Exception as e:
                    logger.error(f"Error loading file {filepath}: {e}")

    logger.info(f"Loaded {loaded_files} of {total_files} notes ({skipped_files} excluded)")
    logger.info(f"Total links extracted: {total_links_found}")
    return documents


def update_db_incrementally(
    db: Chroma, new_files: Set[str], modified_files: Set[str], deleted_files: Set[str]
) -> Chroma:
    """
    Update database incrementally with only changed files

    Args:
        db: Existing ChromaDB instance
        new_files: Set of new file paths
        modified_files: Set of modified file paths
        deleted_files: Set of deleted file paths

    Returns:
        Updated ChromaDB instance
    """
    logger.info("Applying incremental update to database")

    # Delete removed files
    if deleted_files:
        logger.info(f"Removing {len(deleted_files)} deleted documents")
        for filepath in deleted_files:
            try:
                # Delete by metadata filter
                db.delete(where={"source": filepath})
            except Exception as e:
                logger.warning(f"Could not delete {filepath}: {e}")

    # Add/update modified and new files
    files_to_process = new_files | modified_files

    if files_to_process:
        logger.info(f"Processing {len(files_to_process)} new/modified documents")

        # For modified files, delete old versions first
        for filepath in modified_files:
            try:
                db.delete(where={"source": filepath})
            except Exception as e:
                logger.warning(f"Could not delete old version of {filepath}: {e}")

        # Load and chunk new/modified documents
        documents = load_documents_from_paths(files_to_process)

        if documents:
            text_splitter = get_text_splitter()
            texts = text_splitter.split_documents(documents)
            logger.info(f"Created {len(texts)} text chunks")

            # Add to database only if we have chunks
            if texts:
                db.add_documents(texts)
                logger.info("Documents added to database")
            else:
                logger.warning("No text chunks generated from documents (files may be empty)")

    return db


def load_or_create_db(
    obsidian_path: Optional[str] = None, force_rebuild: bool = False
) -> Optional[Chroma]:
    """
    Load or create vector database with incremental indexing support

    Args:
        obsidian_path: Path to Obsidian vault (uses settings if None)
        force_rebuild: Force full rebuild ignoring incremental updates

    Returns:
        ChromaDB instance or None if no documents
    """
    settings = get_settings()
    logger.info("Starting vector database load or creation")

    # Get obsidian path from settings if not provided
    if not obsidian_path:
        obsidian_path = settings.obsidian_path

    if not obsidian_path:
        raise ValueError("OBSIDIAN_PATH must be set in environment or settings")

    embeddings = get_embeddings()
    persist_directory = settings.db_path

    # Check if we should do incremental update
    if (
        os.path.exists(persist_directory)
        and not force_rebuild
        and settings.enable_incremental_indexing
    ):
        logger.info("Checking for changes for incremental update")
        tracker = FileMetadataTracker(settings.metadata_file)

        # Check if we should do full rebuild based on change ratio
        if tracker.should_rebuild(obsidian_path):
            logger.warning("Too many changes detected, doing full rebuild")
            force_rebuild = True
        else:
            new_files, modified_files, deleted_files = tracker.detect_changes(obsidian_path)

            if not new_files and not modified_files and not deleted_files:
                logger.info("No changes, loading existing database")
                db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
                return db

            # Do incremental update
            logger.info("Performing incremental update")
            db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
            db = update_db_incrementally(db, new_files, modified_files, deleted_files)

            # Update metadata tracker
            tracker.update_metadata(obsidian_path)

            return db

    # Full rebuild from scratch
    if force_rebuild:
        logger.info("Forcing full database rebuild")

    # Load all documents
    documents = load_all_obsidian_documents(obsidian_path)

    if not documents:
        logger.warning("No documents loaded. Check the path and files")
        return None

    # Split documents
    logger.info("Splitting documents into chunks")
    text_splitter = get_text_splitter()
    texts = text_splitter.split_documents(documents)
    logger.info(f"Created {len(texts)} text chunks")

    if force_rebuild and os.path.exists(persist_directory):
        # Atomic rebuild: create in temp directory then swap
        temp_dir = f"{persist_directory}_{uuid.uuid4().hex}"
        logger.info(f"Creating new database in temporary directory: {temp_dir}")

        try:
            # Create DB in temp directory
            temp_db = Chroma.from_documents(
                texts,
                embeddings,
                persist_directory=temp_dir,
                collection_metadata={"hnsw:space": "cosine"},
            )

            # Release resources
            del temp_db
            gc.collect()

            # Replace old directory atomically
            logger.info(f"Removing old directory: {persist_directory}")
            shutil.rmtree(persist_directory)

            logger.info(f"Moving {temp_dir} to {persist_directory}")
            os.rename(temp_dir, persist_directory)

            # Load from final location
            db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
            logger.info("Database rebuilt and loaded successfully")

        except Exception as e:
            logger.error(f"Error during atomic rebuild: {e}")
            # Cleanup on error
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise e
    else:
        # First time creation
        logger.info("Creating new vector database")
        db = Chroma.from_documents(
            texts,
            embeddings,
            persist_directory=persist_directory,
            collection_metadata={"hnsw:space": "cosine"},
        )
        logger.info("Vector database created successfully")

    # Update metadata tracker after successful indexing
    if settings.enable_incremental_indexing:
        tracker = FileMetadataTracker(settings.metadata_file)
        tracker.update_metadata(obsidian_path)
        logger.info("Metadata tracker updated")

    return db
