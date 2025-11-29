import gc
import logging
import os
import re
import shutil
import uuid
from typing import Optional, Union

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_community.document_loaders import ObsidianLoader
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaEmbeddings

from config.settings import settings
from services.metadata_tracker import FileMetadataTracker

logger = logging.getLogger(__name__)


def extract_obsidian_links(content: str) -> list[str]:
    """Extract Obsidian wikilinks [[Note]] or [[Note|Alias]] from content"""
    links = re.findall(r'\[\[(.*?)\]\]', content)
    # Clean links (remove alias like [[Note|Alias]] -> Note)
    cleaned_links = [link.split('|')[0].strip() for link in links]
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
    
    Falls back to HuggingFace if Ollama embedding model is not available.
    """
    provider = settings.embedding_provider.lower()
    
    if provider == "ollama":
        model = settings.ollama_embedding_model
        logger.info(f"Intentando cargar Ollama embeddings: {model}")
        
        # Check if model is available in Ollama
        try:
            import httpx
            response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            if response.status_code == 200:
                available_models = [m["name"].split(":")[0] for m in response.json().get("models", [])]
                if model not in available_models:
                    logger.warning(f"⚠️ Modelo '{model}' no encontrado en Ollama. Modelos disponibles: {available_models}")
                    logger.warning(f"💡 Ejecuta: ollama pull {model}")
                    logger.info("🔄 Fallback a HuggingFace embeddings...")
                    provider = "huggingface"  # Fallback
                else:
                    embeddings = OllamaEmbeddings(
                        model=model,
                        base_url=settings.ollama_base_url
                    )
                    logger.info(f"✅ Ollama embeddings ({model}) cargado correctamente")
                    return embeddings
            else:
                logger.warning(f"⚠️ No se pudo conectar a Ollama. Fallback a HuggingFace...")
                provider = "huggingface"
        except Exception as e:
            logger.warning(f"⚠️ Error verificando Ollama: {e}. Fallback a HuggingFace...")
            provider = "huggingface"
    
    # Default: HuggingFace (or fallback)
    model = settings.embedding_model
    logger.info(f"Inicializando HuggingFace embeddings: {model}")
    embeddings = HuggingFaceEmbeddings(model_name=model)
    logger.info(f"✅ HuggingFace embeddings ({model}) cargado correctamente")
    
    return embeddings


def get_text_splitter() -> RecursiveCharacterTextSplitter:
    """Get configured text splitter"""
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=len,
        separators=["#", "##", "###", "####", "\n\n", "\n", " ", ""]
    )


def load_documents_from_paths(filepaths: set[str]) -> list[Document]:
    """Load documents from specific file paths with link extraction"""
    documents = []
    
    for filepath in filepaths:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract Obsidian links
            links = extract_obsidian_links(content)
            
            doc = Document(
                page_content=content,
                metadata={
                    'source': filepath,
                    'links': ','.join(links) if links else ''
                }
            )
            documents.append(doc)
            
            if links:
                logger.debug(f"Extracted {len(links)} links from {filepath}")
                
        except Exception as e:
            logger.warning(f"Could not load {filepath}: {e}")
    
    logger.info(f"Loaded {len(documents)} documents from specified paths")
    return documents


def load_all_obsidian_documents(obsidian_path: str) -> list[Document]:
    """Load all documents from Obsidian vault using recursive walk"""
    logger.info("Cargando documentos de Obsidian (.md) recursivamente")
    
    # Patrones de archivos a excluir (binarios, canvas, etc.)
    EXCLUDED_PATTERNS = [
        '.excalidraw.md',  # Excalidraw drawings (base64)
        '.canvas',          # Canvas files
        'untitled',         # Untitled files
    ]
    
    documents = []
    total_files = 0
    loaded_files = 0
    skipped_files = 0
    total_links_found = 0
    
    for root, _, files in os.walk(obsidian_path):
        for file in files:
            if file.endswith('.md'):
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
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        # Fallback to latin-1
                        logger.warning(f"UTF-8 decode failed for {filepath}, trying latin-1")
                        with open(filepath, 'r', encoding='latin-1') as f:
                            content = f.read()
                    
                    if content.strip():  # Skip empty files
                        # Extract links using centralized function
                        links = extract_obsidian_links(content)
                        total_links_found += len(links)
                        
                        doc = Document(
                            page_content=content,
                            metadata={
                                'source': filepath,
                                'links': ','.join(links) if links else ''
                            }
                        )
                        documents.append(doc)
                        loaded_files += 1
                        
                        # Debug logging for files with many links
                        if len(links) > 5:
                            logger.debug(f"Note '{file}' has {len(links)} links: {links[:5]}...")
                        
                except Exception as e:
                    logger.error(f"Error cargando archivo {filepath}: {e}")
    
    logger.info(f"Se cargaron {loaded_files} de {total_files} notas ({skipped_files} excluidos)")
    logger.info(f"Total de enlaces extraídos: {total_links_found}")
    return documents


def update_db_incrementally(
    db: Chroma,
    new_files: set[str],
    modified_files: set[str],
    deleted_files: set[str]
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
    logger.info("Aplicando actualización incremental a la base de datos")
    
    # Delete removed files
    if deleted_files:
        logger.info(f"Eliminando {len(deleted_files)} documentos eliminados")
        for filepath in deleted_files:
            try:
                # Delete by metadata filter
                db.delete(where={"source": filepath})
            except Exception as e:
                logger.warning(f"Could not delete {filepath}: {e}")
    
    # Add/update modified and new files
    files_to_process = new_files | modified_files
    
    if files_to_process:
        logger.info(f"Procesando {len(files_to_process)} documentos nuevos/modificados")
        
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
            logger.info(f"Se crearon {len(texts)} chunks de texto")
            
            # Add to database
            db.add_documents(texts)
            logger.info("Documentos añadidos a la base de datos")
    
    return db


def load_or_create_db(obsidian_path: str = None, force_rebuild: bool = False) -> Optional[Chroma]:
    """
    Load or create vector database with incremental indexing support
    
    Args:
        obsidian_path: Path to Obsidian vault (uses settings if None)
        force_rebuild: Force full rebuild ignoring incremental updates
    
    Returns:
        ChromaDB instance or None if no documents
    """
    logger.info("Iniciando carga o creación de la base de datos vectorial")
    
    # Get obsidian path from settings if not provided
    if not obsidian_path:
        obsidian_path = settings.obsidian_path
    
    if not obsidian_path:
        raise ValueError("OBSIDIAN_PATH must be set in environment or settings")
    
    embeddings = get_embeddings()
    persist_directory = settings.db_path
    
    # Check if we should do incremental update
    if (os.path.exists(persist_directory) and 
        not force_rebuild and 
        settings.enable_incremental_indexing):
        
        logger.info("Verificando si hay cambios para actualización incremental")
        tracker = FileMetadataTracker(settings.metadata_file)
        
        # Check if we should do full rebuild based on change ratio
        if tracker.should_rebuild(obsidian_path):
            logger.warning("Demasiados cambios detectados, haciendo rebuild completo")
            force_rebuild = True
        else:
            new_files, modified_files, deleted_files = tracker.detect_changes(obsidian_path)
            
            if not new_files and not modified_files and not deleted_files:
                logger.info("No hay cambios, cargando base de datos existente")
                db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
                return db
            
            # Do incremental update
            logger.info("Realizando actualización incremental")
            db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
            db = update_db_incrementally(db, new_files, modified_files, deleted_files)
            
            # Update metadata tracker
            tracker.update_metadata(obsidian_path)
            
            return db
    
    # Full rebuild from scratch
    if force_rebuild:
        logger.info("Forzando reconstrucción completa de la base de datos")
    
    # Load all documents
    documents = load_all_obsidian_documents(obsidian_path)
    
    if not documents:
        logger.warning("No se cargaron documentos. Verifique el path y los archivos")
        return None
    
    # Split documents
    logger.info("Dividiendo documentos en chunks")
    text_splitter = get_text_splitter()
    texts = text_splitter.split_documents(documents)
    logger.info(f"Se crearon {len(texts)} chunks de texto")
    
    if force_rebuild and os.path.exists(persist_directory):
        # Atomic rebuild: create in temp directory then swap
        temp_dir = f"{persist_directory}_{uuid.uuid4().hex}"
        logger.info(f"Creando nueva base de datos en directorio temporal: {temp_dir}")
        
        try:
            # Create DB in temp directory
            temp_db = Chroma.from_documents(
                texts, 
                embeddings, 
                persist_directory=temp_dir,
                collection_metadata={"hnsw:space": "cosine"}
            )
            
            # Release resources
            temp_db = None
            gc.collect()
            
            # Replace old directory atomically
            logger.info(f"Eliminando directorio antiguo: {persist_directory}")
            shutil.rmtree(persist_directory)
            
            logger.info(f"Moviendo {temp_dir} a {persist_directory}")
            os.rename(temp_dir, persist_directory)
            
            # Load from final location
            db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
            logger.info("Base de datos reconstruida y cargada exitosamente")
            
        except Exception as e:
            logger.error(f"Error durante la reconstrucción atómica: {e}")
            # Cleanup on error
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise e
    else:
        # First time creation
        logger.info("Creando nueva base de datos vectorial")
        db = Chroma.from_documents(
            texts, 
            embeddings, 
            persist_directory=persist_directory,
            collection_metadata={"hnsw:space": "cosine"}
        )
        logger.info("Base de datos vectorial creada exitosamente")
    
    # Update metadata tracker after successful indexing
    if settings.enable_incremental_indexing:
        tracker = FileMetadataTracker(settings.metadata_file)
        tracker.update_metadata(obsidian_path)
        logger.info("Metadata tracker actualizado")
    
    return db