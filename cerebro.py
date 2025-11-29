import os
import time
import warnings
import uuid
import asyncio
import gc
from typing import List, Optional, Dict, Tuple

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config.settings import settings
from services.db_service import load_or_create_db
from services.qa_service import (
    RAGError, 
    ModelNotAvailableError, 
    NoDocumentsFoundError
)
from services.qa_agent import create_qa_graph, ask_question_graph
from utils.logger import setup_logger

load_dotenv()

# Configuración del logging
logger = setup_logger(__name__)

# Suprimir advertencias específicas
warnings.filterwarnings("ignore", category=FutureWarning)


app = FastAPI(
    title="Obsidian RAG API",
    description="API para consultar notas de Obsidian usando RAG",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# Global state management
db = None
qa_app = None
db_lock = asyncio.Lock()
chat_histories: Dict[str, List[Tuple[str, str]]] = {}

# Initialize on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and QA graph on startup"""
    global db, qa_app
    
    logger.info("Iniciando aplicación ObsidianRAG")
    logger.info(f"Configuración: {settings.model_dump()}")
    
    try:
        logger.info("Cargando base de datos vectorial...")
        db = load_or_create_db()
        
        if db is None:
            logger.error("No se pudo cargar la base de datos")
            return
        
        logger.info("Creando agente LangGraph...")
        qa_app = create_qa_graph(db)
        
        logger.info("✅ Aplicación iniciada exitosamente")
    except Exception as e:
        logger.error(f"Error durante startup: {e}", exc_info=True)
        raise




chat_histories: Dict[str, List[Tuple[str, str]]] = {}

class Question(BaseModel):
    text: str = Field(..., description="La pregunta que quieres hacer")
    session_id: Optional[str] = Field(None, description="ID de sesión para mantener el contexto")

class Source(BaseModel):
    source: str = Field(..., description="La fuente de la información")
    score: float = Field(0.0, description="Puntuación de relevancia del reranker (mayor es mejor)")
    retrieval_type: str = Field("retrieved", description="Tipo de recuperación: 'retrieved' o 'graphrag_link'")

class Answer(BaseModel):
    question: str
    result: str
    sources: List[Source]
    text_blocks: List[str]
    process_time: float = Field(..., description="Tiempo de procesamiento en segundos")
    session_id: str = Field(..., description="ID de sesión utilizado")

@app.post("/ask", response_model=Answer, summary="Haz una pregunta", description="Este endpoint permite hacer una pregunta y obtener una respuesta con contexto.")
async def ask(question: Question, request: Request):
    """
    Endpoint para hacer una pregunta y obtener una respuesta con contexto.
    - **question**: La pregunta que quieres hacer.
    - **session_id**: Opcional. Si no se envía, se genera uno nuevo.
    """
    try:
        logger.info(f"Recibida pregunta: {question.text}")
        start_time = time.time()
        
        # Check if system is ready
        if qa_app is None:
            raise HTTPException(
                status_code=503, 
                detail="Sistema no inicializado. Intente de nuevo en unos momentos."
            )
        
        # Gestión de sesión
        session_id = question.session_id
        if not session_id:
            session_id = str(uuid.uuid4())
            chat_histories[session_id] = []
            logger.info(f"Nueva sesión creada: {session_id}")
        
        # Obtener historial
        history = chat_histories.get(session_id, [])
        
        # Hacer la pregunta con historial
        async with db_lock:
            # Run in thread pool since LangGraph might be blocking
            loop = asyncio.get_event_loop()
            result, sources = await loop.run_in_executor(
                None, 
                lambda: ask_question_graph(qa_app, question.text, history)
            )
        
        # Actualizar historial
        history.append((question.text, result))
        chat_histories[session_id] = history
        
        process_time = time.time() - start_time
        logger.info(f"Respuesta generada en {process_time:.4f} segundos")
        text_blocks = [source.page_content for source in sources]
        
        # Create source list and sort by score (highest first)
        source_list = [
            Source(
                source=source.metadata.get('source', 'Desconocido'),
                score=source.metadata.get('score', 0.0),
                retrieval_type=source.metadata.get('retrieval_type', 'retrieved')
            ) for source in sources
        ]
        source_list.sort(key=lambda x: x.score, reverse=True)
        
        return Answer(
            question=question.text,
            result=result,
            sources=source_list,
            text_blocks=text_blocks,
            process_time=process_time,
            session_id=session_id
        )
    except ModelNotAvailableError as e:
        logger.error(f"Ollama no disponible: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))
    except NoDocumentsFoundError as e:
        logger.error(f"No hay documentos: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except RAGError as e:
        logger.error(f"Error RAG: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@app.post("/rebuild_db", summary="Reconstruir base de datos", description="Fuerza la reconstrucción de la base de datos vectorial para indexar nuevos archivos.")
async def rebuild_db():
    """
    Endpoint para forzar la reconstrucción de la base de datos.
    """
    try:
        logger.info("Solicitud de reconstrucción de DB recibida")
        global db, qa_app
        
        async with db_lock:
            # Intentar liberar recursos antes de reconstruir
            db = None
            qa_app = None
            gc.collect()
            
            # Reconstruir DB
            db = load_or_create_db(force_rebuild=True)
            
            if db is None:
                raise HTTPException(status_code=500, detail="Error al reconstruir la base de datos")
            
            # Recrear grafo
            qa_app = create_qa_graph(db)
            
        return {"status": "success", "message": "Base de datos reconstruida y grafo actualizado"}
    except Exception as e:
        logger.error(f"Error al reconstruir la DB: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", summary="Endpoint raíz", description="Endpoint de bienvenida a la API.")
async def root():
    """
    Endpoint de bienvenida a la API.
    """
    return {"message": "Bienvenido a la API de Obsidian RAG"}

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host=settings.api_host, 
        port=settings.api_port,
        reload=settings.api_reload
    )