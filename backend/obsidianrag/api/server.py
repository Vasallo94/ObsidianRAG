"""FastAPI server for ObsidianRAG"""

import asyncio
import gc
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from obsidianrag.config import configure_from_vault, get_settings
from obsidianrag.core.db_service import load_or_create_db
from obsidianrag.core.qa_agent import (
    ask_question_graph,
    ask_question_graph_streaming,
    create_qa_graph,
)
from obsidianrag.core.qa_service import ModelNotAvailableError, NoDocumentsFoundError, RAGError
from obsidianrag.utils.logger import setup_logger

logger = setup_logger(__name__)

# Global state
_db = None
_qa_app = None
_db_lock = asyncio.Lock()
_chat_histories: Dict[str, List[Tuple[str, str]]] = {}
_vault_path: Optional[str] = None


def create_app(vault_path: Optional[str] = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        vault_path: Optional path to Obsidian vault

    Returns:
        Configured FastAPI application
    """
    global _vault_path
    _vault_path = vault_path

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager for startup and shutdown events"""
        global _db, _qa_app

        settings = get_settings()

        logger.info("Starting ObsidianRAG application")
        logger.info(f"Configuration: {settings.model_dump()}")

        try:
            logger.info("Loading vector database...")
            if _vault_path:
                configure_from_vault(_vault_path)

            _db = load_or_create_db()

            if _db is None:
                logger.error("Could not load database")
            else:
                logger.info("Creating LangGraph agent...")
                _qa_app = create_qa_graph(_db)
                logger.info("✅ Application started successfully")
        except Exception as e:
            logger.error(f"Error during startup: {e}", exc_info=True)
            raise

        yield

        logger.info("Shutting down ObsidianRAG application")

    application = FastAPI(
        title="ObsidianRAG API",
        description="API for querying Obsidian notes using RAG",
        version="3.0.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    settings = get_settings()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware to measure request processing time
    @application.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        logger.info(f"Processing time: {process_time:.4f} seconds")
        return response

    # Register routes
    _register_routes(application)

    return application


# Pydantic models
class Question(BaseModel):
    text: str = Field(..., description="The question you want to ask")
    session_id: Optional[str] = Field(None, description="Session ID to maintain context")


class Source(BaseModel):
    source: str = Field(..., description="The source of the information")
    score: float = Field(0.0, description="Reranker relevance score (higher is better)")
    retrieval_type: str = Field(
        "retrieved", description="Retrieval type: 'retrieved' or 'graphrag_link'"
    )


class Answer(BaseModel):
    question: str
    result: str
    sources: List[Source]
    text_blocks: List[str]
    process_time: float = Field(..., description="Processing time in seconds")
    session_id: str = Field(..., description="Session ID used")


def _register_routes(application: FastAPI):
    """Register all API routes."""

    @application.get("/", summary="Root endpoint")
    async def root():
        """Welcome endpoint for the API."""
        return {"message": "Welcome to ObsidianRAG API", "version": "3.0.0"}

    @application.post("/ask", response_model=Answer, summary="Ask a question")
    async def ask(question: Question, request: Request):
        """Ask a question and get an answer with context."""
        try:
            logger.info(f"Received question: {question.text}")
            start_time = time.time()

            if _qa_app is None:
                raise HTTPException(
                    status_code=503, detail="System not initialized. Try again in a few moments."
                )

            session_id = question.session_id
            if not session_id:
                session_id = str(uuid.uuid4())
                _chat_histories[session_id] = []
                logger.info(f"New session created: {session_id}")

            history = _chat_histories.get(session_id, [])

            async with _db_lock:
                qa_graph = create_qa_graph(_db)

                loop = asyncio.get_event_loop()
                result, sources = await loop.run_in_executor(
                    None, lambda: ask_question_graph(qa_graph, question.text, history)
                )

            history.append((question.text, result))
            _chat_histories[session_id] = history

            process_time = time.time() - start_time
            logger.info(f"Response generated in {process_time:.4f} seconds")
            text_blocks = [source.page_content for source in sources]

            source_list = [
                Source(
                    source=source.metadata.get("source", "Unknown"),
                    score=source.metadata.get("score", 0.0),
                    retrieval_type=source.metadata.get("retrieval_type", "retrieved"),
                )
                for source in sources
            ]
            source_list.sort(key=lambda x: x.score, reverse=True)

            return Answer(
                question=question.text,
                result=result,
                sources=source_list,
                text_blocks=text_blocks,
                process_time=process_time,
                session_id=session_id,
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

    @application.post("/ask/stream", summary="Ask a question with streaming")
    async def ask_stream(question: Question, request: Request):
        """Ask a question and stream the response with progress updates via SSE."""
        import time as time_module

        from obsidianrag.core.qa_service import create_hybrid_retriever

        async def event_generator() -> AsyncGenerator[str, None]:
            """Generate SSE events for the streaming response."""
            event_count = 0
            stream_start = time_module.time()

            try:
                if _db is None:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'System not initialized'})}\n\n"
                    return

                session_id = question.session_id or str(uuid.uuid4())
                history = _chat_histories.get(session_id, [])

                # Create retriever for streaming
                retriever = create_hybrid_retriever(_db)

                # Send start event
                logger.info("📤 [SSE] Sending start event")
                yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"

                # Stream with direct retrieval and LLM streaming
                last_event = None
                async for event in ask_question_graph_streaming(
                    _qa_app, question.text, history, retriever=retriever, db=_db
                ):
                    event_count += 1
                    event_type = event.get("type", "unknown")
                    elapsed = time_module.time() - stream_start

                    if event_type == "token":
                        # Log every 10th token to avoid spam
                        if event_count % 10 == 0:
                            logger.info(f"📤 [SSE #{event_count}] +{elapsed:.2f}s token batch")
                    else:
                        logger.info(f"📤 [SSE #{event_count}] +{elapsed:.2f}s {event_type}")

                    yield f"data: {json.dumps(event)}\n\n"
                    last_event = event

                # Update history
                if last_event and last_event.get("type") == "answer":
                    history.append((question.text, last_event.get("answer", "")))
                    _chat_histories[session_id] = history

                total_time = time_module.time() - stream_start
                logger.info(f"✅ [SSE] Stream complete: {event_count} events in {total_time:.2f}s")

            except Exception as e:
                logger.error(f"Streaming error: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            # Send end event
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get("/health", summary="System status")
    async def health():
        """Check system status and show current configuration."""
        settings = get_settings()
        return {
            "status": "ok",
            "model": settings.llm_model,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model
            if settings.embedding_provider == "huggingface"
            else settings.ollama_embedding_model,
            "db_ready": _db is not None,
        }

    @application.get("/stats", summary="Vault statistics")
    async def get_stats():
        """Get statistics about the indexed Obsidian vault."""
        settings = get_settings()
        if _db is None:
            return {"error": "Database not ready"}

        try:
            db_data = _db.get()
            documents = db_data.get("documents", [])
            metadatas = db_data.get("metadatas", [])

            total_chunks = len(documents)
            total_chars = sum(len(doc) for doc in documents)
            total_words = sum(len(doc.split()) for doc in documents)

            sources = set()
            folders = set()
            links = set()

            for meta in metadatas:
                source = meta.get("source", "")
                if source:
                    sources.add(source)
                    parts = source.split("/")
                    if len(parts) > 1:
                        folders.add(parts[-2])

                links_str = meta.get("links", "")
                if links_str:
                    for link in links_str.split(","):
                        if link.strip():
                            links.add(link.strip())

            return {
                "total_notes": len(sources),
                "total_chunks": total_chunks,
                "total_words": total_words,
                "total_chars": total_chars,
                "avg_words_per_chunk": total_words // total_chunks if total_chunks > 0 else 0,
                "folders": len(folders),
                "internal_links": len(links),
                "vault_path": settings.obsidian_path.split("/")[-1]
                if settings.obsidian_path
                else "Unknown",
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}", exc_info=True)
            return {"error": "Failed to retrieve vault statistics"}

    @application.post("/rebuild_db", summary="Rebuild database")
    async def rebuild_db():
        """Force rebuild of the vector database to index new files."""
        try:
            logger.info("Database rebuild request received")
            global _db, _qa_app

            async with _db_lock:
                _db = None
                _qa_app = None
                gc.collect()

                _db = load_or_create_db(force_rebuild=True)

                if _db is None:
                    raise HTTPException(status_code=500, detail="Error rebuilding database")

                _qa_app = create_qa_graph(_db)
                
                # Get statistics to return
                db_data = _db.get()
                total_chunks = len(db_data.get("documents", []))

            return {
                "status": "success", 
                "message": "Database rebuilt and graph updated",
                "total_chunks": total_chunks
            }
        except Exception as e:
            logger.error(f"Error rebuilding DB: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to rebuild database")


# Default app for direct uvicorn usage
app = create_app()


def run_server(vault_path: str, host: str = "127.0.0.1", port: int = 8000):
    """Run the server programmatically.

    Args:
        vault_path: Path to Obsidian vault
        host: Host to bind to
        port: Port to bind to
    """
    server_app = create_app(vault_path)
    uvicorn.run(server_app, host=host, port=port)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
