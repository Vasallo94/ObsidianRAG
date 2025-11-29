import logging
import os
import shutil
import uuid
import gc
from typing import Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import ObsidianLoader
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

from config.settings import settings
from services.metadata_tracker import FileMetadataTracker

logger = logging.getLogger(__name__)


def get_embeddings() -> HuggingFaceEmbeddings:
    """Get configured embeddings model"""
    logger.info(f"Inicializando modelo de embeddings: {settings.embedding_model}")
    embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)
    logger.info("Modelo de embeddings cargado correctamente")
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
    """Load documents from specific file paths"""
    documents = []
    
    for filepath in filepaths:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            doc = Document(
                page_content=content,
                metadata={'source': filepath}
            )
            documents.append(doc)
        except Exception as e:
            logger.warning(f"Could not load {filepath}: {e}")
    
    logger.info(f"Loaded {len(documents)} documents from specified paths")
    return documents


def load_all_obsidian_documents(obsidian_path: str) -> list[Document]:
    """Load all documents from Obsidian vault using recursive walk"""
    logger.info("Cargando documentos de Obsidian (.md) recursivamente")
    
    documents = []
    total_files = 0
    loaded_files = 0
    
    for root, _, files in os.walk(obsidian_path):
        for file in files:
            if file.endswith('.md'):
                total_files += 1
                filepath = os.path.join(root, file)
                
                try:
                    # Debug specific file
                    if "Fractales.md" in file:
                        logger.info(f"!!! FOUND Fractales.md at {filepath} !!!")

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
                        # Extract links
                        import re
                        links = re.findall(r'\[\[(.*?)\]\]', content)
                        # Clean links (remove alias like [[Note|Alias]])
                        cleaned_links = [link.split('|')[0] for link in links]
                        
                        doc = Document(
                            page_content=content,
                            metadata={
                                'source': filepath,
                                'links': ','.join(cleaned_links)
                            }
                        )
                        documents.append(doc)
                        loaded_files += 1
                        if "Fractales.md" in file:
                            logger.info(f"!!! LOADED Fractales.md successfully. Content len: {len(content)} !!!")
                    else:
                        if "Fractales.md" in file:
                            logger.warning(f"!!! Fractales.md is empty !!!")
                        
                except Exception as e:
                    logger.error(f"Error cargando archivo {filepath}: {e}")
    
    logger.info(f"Se cargaron {loaded_files} de {total_files} notas de Obsidian")
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