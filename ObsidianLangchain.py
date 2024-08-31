import logging
import os
import warnings

from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
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
        separators=["#", "##", "###", "####"]
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


# Definir el prompt de sistema
system_prompt = """Eres un asistente AI especializado en analizar y responder preguntas sobre mis notas de Obsidian. Tu tarea es interpretar la información proporcionada en el contexto de las mis notas y ofrecer respuestas precisas, concisas y relevantes a la pregunta que se te haga.

Instrucciones específicas:
1. Analiza cuidadosamente el contexto proporcionado de las notas de Obsidian.
2. Relaciona la pregunta del usuario con la información relevante en las notas.
3. Proporciona respuestas que sean directamente relevantes para el contenido de mis notas.
4. Si la información en las notas es insuficiente para responder completamente, indícalo claramente sin inventar una respuesta.
5. Mantén un tono profesional y objetivo en tus respuestas.
6. Cita o haz referencia a partes específicas de las notas cuando sea apropiado.
7. Si detectas patrones o temas recurrentes en las notas, menciónalo si es relevante para la pregunta.
8. Estructura la información en markdown para que sea legible y bien formateada.

Recuerda, tu objetivo es ayudarme a comprender mejor y utilizar la información de mis propias notas de Obsidian."""

# Crear el template del prompt
prompt_template = PromptTemplate(
    input_variables=["context", "question"],
    template=system_prompt + "\n\nQuestion: {question}\n\nContext: {context}\nAnswer:"
)

# Inicializar Ollama
logger.info("Inicializando modelo Ollama")
llm = Ollama(model="llama3.1")

# Crear una cadena de recuperación y respuesta
logger.info("Creando cadena de recuperación y respuesta con prompt personalizado")
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=db.as_retriever(search_kwargs={"k": 4}),
    return_source_documents=True,
    chain_type_kwargs={"prompt": prompt_template}
)

# Función para hacer preguntas
def ask_question(question):
    logger.info(f"Procesando pregunta: {question}")
    result = qa_chain.invoke({"query": question})
    logger.info("Respuesta generada")
    return result["result"], result["source_documents"]

# Este bloque solo se ejecutará si el script se ejecuta directamente
if __name__ == "__main__":
    logger.info("Modo de prueba: ejecutando ejemplo de uso")
    question = "QUé opino sobre el infinito?"
    answer, sources = ask_question(question) 
    print(f"Respuesta: {answer}\n")
    print("Fuentes:")
    for source in sources:
        print(f"- {source.metadata['source']}")
    logger.info("Ejemplo de uso completado")