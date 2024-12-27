import logging
import os
import time
import warnings
from typing import List

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.db_service import load_or_create_db
from services.qa_service import ask_question, create_qa_chain

load_dotenv()

# Configuración del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suprimir advertencias específicas
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

app = FastAPI(
    title="Obsidian RAG API",
    description="API para consultar notas de Obsidian usando RAG",
    version="1.0.0"
)

# Middleware para medir el tiempo de las solicitudes
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"Tiempo de procesamiento: {process_time:.4f} segundos")
    return response

# Cargar o crear la base de datos
obsidian_path = os.getenv('OBSIDIAN_PATH')
db = load_or_create_db(obsidian_path)
# Crear la cadena QA
qa_chain_instance = create_qa_chain(db)

class Question(BaseModel):
    text: str = Field(..., description="La pregunta que quieres hacer")

class Source(BaseModel):
    source: str = Field(..., description="La fuente de la información")

class Answer(BaseModel):
    question: str
    result: str
    sources: List[Source]
    text_blocks: List[str]
    process_time: float = Field(..., description="Tiempo de procesamiento en segundos")  

@app.post("/ask", response_model=Answer, summary="Haz una pregunta", description="Este endpoint permite hacer una pregunta y obtener una respuesta con contexto.")
async def ask(question: Question, request: Request):
    """
    Endpoint para hacer una pregunta y obtener una respuesta con contexto.
    - **question**: La pregunta que quieres hacer.
    """
    try:
        logger.info(f"Recibida pregunta: {question.text}")
        start_time = time.time()
        result, sources = ask_question(qa_chain_instance, question.text)
        process_time = time.time() - start_time
        logger.info(f"Respuesta generada en {process_time:.4f} segundos")
        text_blocks = [source.page_content for source in sources]
        return Answer(
            question=question.text,
            result=result,
            sources=[Source(source=source.metadata.get('source', 'Desconocido')) for source in sources],
            text_blocks=text_blocks,
            process_time=process_time  
        )
    except Exception as e:
        logger.error(f"Error al procesar la pregunta: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", summary="Endpoint raíz", description="Endpoint de bienvenida a la API.")
async def root():
    """
    Endpoint de bienvenida a la API.
    """
    return {"message": "Bienvenido a la API de Obsidian RAG"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)