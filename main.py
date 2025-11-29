import os
import time
import warnings
import uuid
import asyncio
import gc
from contextlib import asynccontextmanager
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

# Logging configuration
logger = setup_logger(__name__)

# Suprimir advertencias específicas
warnings.filterwarnings("ignore", category=FutureWarning)

# Global state management
db = None
qa_app = None
db_lock = asyncio.Lock()
chat_histories: Dict[str, List[Tuple[str, str]]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    global db, qa_app
    
    # Startup
    logger.info("Starting ObsidianRAG application")
    logger.info(f"Configuration: {settings.model_dump()}")
    
    try:
        logger.info("Loading vector database...")
        db = load_or_create_db()
        
        if db is None:
            logger.error("Could not load database")
        else:
            logger.info("Creating LangGraph agent...")
            qa_app = create_qa_graph(db)
            logger.info("✅ Application started successfully")
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        raise
    
    yield  # Application runs here
    
    # Shutdown (cleanup if needed)
    logger.info("Shutting down ObsidianRAG application")


app = FastAPI(
    title="Obsidian RAG API",
    description="API para consultar notas de Obsidian usando RAG",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware to measure request processing time
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"Processing time: {process_time:.4f} seconds")
    return response


chat_histories: Dict[str, List[Tuple[str, str]]] = {}

class Question(BaseModel):
    text: str = Field(..., description="The question you want to ask")
    session_id: Optional[str] = Field(None, description="Session ID to maintain context")

class Source(BaseModel):
    source: str = Field(..., description="The source of the information")
    score: float = Field(0.0, description="Reranker relevance score (higher is better)")
    retrieval_type: str = Field("retrieved", description="Retrieval type: 'retrieved' or 'graphrag_link'")

class Answer(BaseModel):
    question: str
    result: str
    sources: List[Source]
    text_blocks: List[str]
    process_time: float = Field(..., description="Processing time in seconds")
    session_id: str = Field(..., description="Session ID used")

@app.post("/ask", response_model=Answer, summary="Ask a question", description="This endpoint allows you to ask a question and get an answer with context.")
async def ask(question: Question, request: Request):
    """
    Endpoint to ask a question and get an answer with context.
    - **question**: The question you want to ask.
    - **session_id**: Optional. If not provided, a new one is generated.
    """
    try:
        logger.info(f"Received question: {question.text}")
        start_time = time.time()
        
        # Check if system is ready
        if qa_app is None:
            raise HTTPException(
                status_code=503, 
                detail="System not initialized. Try again in a few moments."
            )
        
        # Session management
        session_id = question.session_id
        if not session_id:
            session_id = str(uuid.uuid4())
            chat_histories[session_id] = []
            logger.info(f"New session created: {session_id}")
        
        # Get history
        history = chat_histories.get(session_id, [])
        
        # Ask question using the model configured in settings
        async with db_lock:
            # Create graph with configured model
            qa_graph = create_qa_graph(db)
            
            # Run in thread pool since LangGraph might be blocking
            loop = asyncio.get_event_loop()
            result, sources = await loop.run_in_executor(
                None, 
                lambda: ask_question_graph(qa_graph, question.text, history)
            )
        
        # Update history
        history.append((question.text, result))
        chat_histories[session_id] = history
        
        process_time = time.time() - start_time
        logger.info(f"Response generated in {process_time:.4f} seconds")
        text_blocks = [source.page_content for source in sources]
        
        # Create source list and sort by score (highest first)
        source_list = [
            Source(
                source=source.metadata.get('source', 'Unknown'),
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
        logger.error(f"Ollama not available: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))
    except NoDocumentsFoundError as e:
        logger.error(f"No documents found: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except RAGError as e:
        logger.error(f"RAG error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health", summary="System status", description="Check system status and show current configuration.")
async def health():
    """
    Endpoint to check system status.
    """
    return {
        "status": "ok",
        "model": settings.llm_model,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model if settings.embedding_provider == "huggingface" else settings.ollama_embedding_model,
        "db_ready": db is not None
    }


@app.post("/rebuild_db", summary="Rebuild database", description="Force rebuild of the vector database to index new files.")
async def rebuild_db():
    """
    Endpoint to force database rebuild.
    """
    try:
        logger.info("Database rebuild request received")
        global db, qa_app
        
        async with db_lock:
            # Try to release resources before rebuilding
            db = None
            qa_app = None
            gc.collect()
            
            # Rebuild DB
            db = load_or_create_db(force_rebuild=True)
            
            if db is None:
                raise HTTPException(status_code=500, detail="Error rebuilding database")
            
            # Recreate graph
            qa_app = create_qa_graph(db)
            
        return {"status": "success", "message": "Database rebuilt and graph updated"}
    except Exception as e:
        logger.error(f"Error rebuilding DB: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", summary="Root endpoint", description="Welcome endpoint for the API.")
async def root():
    """
    Welcome endpoint for the API.
    """
    return {"message": "Welcome to the Obsidian RAG API"}

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host=settings.api_host, 
        port=settings.api_port,
        reload=settings.api_reload
    )