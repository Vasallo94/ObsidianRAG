import logging
import os

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import ObsidianLoader
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)

persist_directory = 'db'

def load_or_create_db(obsidian_path: str = None):
    logger.info("Iniciando carga o creación de la base de datos vectorial")
    
    # Cargar documentos de Obsidian
    logger.info("Cargando documentos de Obsidian")
    obsidian_path = os.getenv('OBSIDIAN_PATH')
    loader = ObsidianLoader(obsidian_path)
    documents = loader.load()
    logger.info(f"Se cargaron {len(documents)} documentos")

    # Dividir los documentos en chunks más pequeños
    logger.info("Dividiendo documentos en chunks")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=len,
        separators=["#", "##", "###", "####"]
    )
    texts = text_splitter.split_documents(documents)
    logger.info(f"Se crearon {len(texts)} chunks de texto")

    # Inicializar el modelo de embeddings de Hugging Face
    logger.info("Inicializando modelo de embeddings")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    logger.info("Modelo de embeddings cargado correctamente.")
    
    # Crear o cargar la base de datos vectorial con Chroma
    if os.path.exists(persist_directory):
        logger.info("Cargando base de datos vectorial existente")
        db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
    else:
        logger.info("Creando nueva base de datos vectorial")
        db = Chroma.from_documents(texts, embeddings, persist_directory=persist_directory)
    
    logger.info("Base de datos vectorial cargada/creada exitosamente")
    return db