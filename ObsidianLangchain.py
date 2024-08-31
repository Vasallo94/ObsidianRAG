import logging
import os
import warnings

from langchain.chains import RetrievalQA
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import ObsidianLoader
from langchain_community.llms import Ollama
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Configuración del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suprimir advertencias específicas
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Directorio para guardar la base de datos vectorial
persist_directory = 'db'

# Función para cargar o crear la base de datos vectorial
def load_or_create_db():
    logger.info("Iniciando carga o creación de la base de datos vectorial")
    
    # Cargar documentos de Obsidian
    logger.info("Cargando documentos de Obsidian")
    loader = ObsidianLoader('/Users/enriquebook/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Secundo Selebro')
    documents = loader.load()
    logger.info(f"Se cargaron {len(documents)} documentos")

    # Dividir los documentos en chunks más pequeños
    logger.info("Dividiendo documentos en chunks")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    texts = text_splitter.split_documents(documents)
    logger.info(f"Se crearon {len(texts)} chunks de texto")

    # Inicializar el modelo de embeddings de Hugging Face
    logger.info("Inicializando modelo de embeddings")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    # Crear o cargar la base de datos vectorial con Chroma
    if os.path.exists(persist_directory):
        logger.info("Cargando base de datos vectorial existente")
        db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
    else:
        logger.info("Creando nueva base de datos vectorial")
        db = Chroma.from_documents(texts, embeddings, persist_directory=persist_directory)
    
    logger.info("Base de datos vectorial cargada/creada exitosamente")
    return db

# Cargar o crear la base de datos
db = load_or_create_db()

# Inicializar Ollama
logger.info("Inicializando modelo Ollama")
llm = Ollama(model="llama3.1")

# Crear una cadena de recuperación y respuesta
logger.info("Creando cadena de recuperación y respuesta")
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=db.as_retriever(search_kwargs={"k": 3}),
    return_source_documents=True
)

# Función para hacer preguntas
def ask_question(question):
    logger.info(f"Procesando pregunta: {question}")
    result = qa_chain.invoke({"query": question})
    logger.info("Respuesta generada")
    return result["result"], result["source_documents"]

# Ejemplo de uso
if __name__ == "__main__":
    logger.info("Iniciando ejemplo de uso")
    question = "¿Cuál es el tema principal de mis notas sobre inteligencia artificial?"
    answer, sources = ask_question(question)
    print(f"Respuesta: {answer}\n")
    print("Fuentes:")
    for source in sources:
        print(f"- {source.metadata['source']}")
    logger.info("Ejemplo de uso completado")