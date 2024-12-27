import logging

from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain_community.llms import Ollama

logger = logging.getLogger(__name__)

# Definir el prompt de sistema
system_prompt = """Eres un asistente AI especializado en analizar y responder preguntas en español sobre mis notas de Obsidian. Tu tarea es interpretar la información proporcionada en el contexto de mis notas y ofrecer respuestas precisas, concisas y relevantes extraídas de la pregunta que te haga y de la información de mis notas.

Instrucciones específicas:
1. Analiza cuidadosamente el contexto proporcionado de las notas de Obsidian.
2. Relaciona la pregunta del usuario con la información relevante en las notas.
3. Proporciona respuestas que sean directamente relevantes para el contenido de mis notas, nada más. No tienes por qué citarlo todo, solo lo que tenga que ver con la pregunta.
4. Si la información en las notas es insuficiente para responder completamente, indícalo claramente sin inventar una respuesta. Se breve y honesto.
5. Mantén un tono profesional y objetivo en tus respuestas.
6. Cita o haz referencia a partes específicas de las notas cuando sea apropiado. Hazlo usando comillas españolas (« ») para indicar citas textuales.
7. Si detectas patrones o temas recurrentes en las notas, menciónalos si son relevantes para la pregunta.
8. Estructura la información en Markdown para que sea legible y esté bien formateada.

Recuerda, tu objetivo es ayudarme a comprender mejor y utilizar la información de mis propias notas de Obsidian."""

# Crear el template del prompt
prompt_template = PromptTemplate(
    input_variables=["context", "question"],
    template=system_prompt + "\n\nQuestion: {question}\n\nContext: {context}\nAnswer:"
)

def create_qa_chain(db):
    logger.info("Inicializando modelo Ollama")
    llm = Ollama(model="llama3.2")  # Asegúrate de que el modelo está correctamente especificado
    logger.info("Creando cadena de recuperación y respuesta con prompt personalizado")
    qa_chain_instance = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=db.as_retriever(search_kwargs={"k": 4}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt_template}
    )
    logger.info("Cadena RetrievalQA configurada correctamente.")
    return qa_chain_instance

# Función para hacer preguntas
def ask_question(qa_chain, question):
    logger.info(f"Procesando pregunta: {question}")
    try:
        # Usar el método adecuado para invocar la cadena
        result = qa_chain({"query": question})
        logger.info("Respuesta generada")
        return result["result"], result["source_documents"]
    except Exception as e:
        logger.error(f"Error al ejecutar RetrievalQA: {e}")
        return "", []
