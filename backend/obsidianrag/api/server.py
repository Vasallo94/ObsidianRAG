"""FastAPI server for the v4 ObsidianRAG runtime."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, AsyncIterator, List, Optional, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from obsidianrag.config import Settings, get_settings, settings_override
from obsidianrag.core.db_service import get_embeddings
from obsidianrag.core.llm_provider import list_llm_models
from obsidianrag.core.query_pipeline import QueryPipeline, await_thread, create_v4_query_pipeline
from obsidianrag.utils.logger import setup_logger
from obsidianrag.v4 import (
    FullRebuildRequired,
    IndexBuildLocked,
    IndexCorruptionError,
    IndexPathError,
    RevisionInUse,
    active_revision,
    build_index,
    index_status,
    prune_revisions,
)

logger = setup_logger(__name__)

API_VERSION = 4
MAX_SESSIONS = 100
MAX_HISTORY_PER_SESSION = 20


class _LRUSessionStore:
    """Bounded application-scoped session store with LRU eviction."""

    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self._store: OrderedDict[str, List[Tuple[str, str]]] = OrderedDict()
        self._max = max_sessions

    def get(self, sid: str) -> List[Tuple[str, str]]:
        if sid in self._store:
            self._store.move_to_end(sid)
            return list(self._store[sid])
        return []

    def set(self, sid: str, history: List[Tuple[str, str]]) -> None:
        self._store[sid] = history[-MAX_HISTORY_PER_SESSION:]
        self._store.move_to_end(sid)
        if len(self._store) > self._max:
            self._store.popitem(last=False)


@dataclass
class _SessionLock:
    lock: asyncio.Lock
    users: int = 0


@dataclass(eq=False)
class _PipelineSlot:
    pipeline: QueryPipeline
    revision: str
    users: int = 0
    retired: bool = False
    closed: bool = False


class _IndexNotReady(RuntimeError):
    pass


class _Runtime:
    """Own the serving pipeline and retire revisions after checked-out users finish."""

    def __init__(self, vault_path: Path | None, settings: Settings | None = None):
        self.vault_path = vault_path.resolve() if vault_path is not None else None
        self.settings = settings or get_settings().model_copy(deep=True)
        self.histories = _LRUSessionStore()
        self._session_locks: OrderedDict[str, _SessionLock] = OrderedDict()
        self._session_locks_guard = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._index_lock = asyncio.Lock()
        self._serving: _PipelineSlot | None = None
        self._retired: list[_PipelineSlot] = []

    @asynccontextmanager
    async def session_turn(self, session_id: str) -> AsyncIterator[None]:
        async with self._session_locks_guard:
            entry = self._session_locks.get(session_id)
            if entry is None:
                entry = _SessionLock(asyncio.Lock())
                self._session_locks[session_id] = entry
            entry.users += 1
            self._session_locks.move_to_end(session_id)
            self._trim_session_locks()
        try:
            async with entry.lock:
                yield
        finally:
            async with self._session_locks_guard:
                entry.users -= 1
                self._trim_session_locks()

    def _trim_session_locks(self) -> None:
        while len(self._session_locks) > MAX_SESSIONS:
            idle = next(
                (
                    session_id
                    for session_id, entry in self._session_locks.items()
                    if entry.users == 0
                ),
                None,
            )
            if idle is None:
                return
            del self._session_locks[idle]

    async def startup(self) -> None:
        if self.vault_path is None:
            logger.warning("No vault is configured; query service is not ready")
            return
        try:
            status = await self._raw_status()
            if status.state != "current" or status.active_revision is None:
                logger.info("v4 index is %s; startup will not build it", status.state)
                return
            pipeline = await await_thread(
                create_v4_query_pipeline, self.vault_path, settings=self.settings
            )
            await self._swap(_PipelineSlot(pipeline, status.active_revision))
            logger.info("Serving v4 revision %s", status.active_revision)
        except Exception as error:
            logger.warning("v4 query pipeline is not ready at startup: %s", error)

    async def shutdown(self) -> None:
        to_close: list[_PipelineSlot] = []
        async with self._state_lock:
            slots = [*self._retired]
            if self._serving is not None:
                slots.append(self._serving)
                self._serving = None
            for slot in slots:
                slot.retired = True
                if slot.users == 0 and not slot.closed:
                    slot.closed = True
                    to_close.append(slot)
            self._retired = [slot for slot in slots if not slot.closed]
        for slot in to_close:
            await self._close(slot)

    async def acquire(self) -> _PipelineSlot:
        async with self._state_lock:
            slot = self._serving
            if slot is None:
                raise _IndexNotReady("No query pipeline is ready")
            slot.users += 1
            return slot

    async def release(self, slot: _PipelineSlot) -> None:
        close = False
        async with self._state_lock:
            slot.users -= 1
            if slot.users < 0:
                raise RuntimeError("Pipeline slot released more than once")
            if slot.retired and slot.users == 0 and not slot.closed:
                slot.closed = True
                close = True
                if slot in self._retired:
                    self._retired.remove(slot)
        if close:
            await self._close(slot)

    async def _close(self, slot: _PipelineSlot) -> None:
        try:
            await await_thread(slot.pipeline.close)
        except Exception as error:
            logger.warning("Could not close retired query pipeline: %s", error)

    async def _swap(self, candidate: _PipelineSlot) -> None:
        close: _PipelineSlot | None = None
        async with self._state_lock:
            old = self._serving
            self._serving = candidate
            if old is not None:
                old.retired = True
                if old.users == 0 and not old.closed:
                    old.closed = True
                    close = old
                else:
                    self._retired.append(old)
        if close is not None:
            await self._close(close)

    async def serving_revision(self) -> str | None:
        async with self._state_lock:
            return self._serving.revision if self._serving is not None else None

    async def _raw_status(self):
        vault = self._require_vault()
        status = await await_thread(index_status, vault)
        if status.state not in {"current", "stale"}:
            return status
        embeddings = await await_thread(get_embeddings)
        return await await_thread(index_status, vault, embeddings)

    async def status(self) -> dict[str, Any]:
        serving = await self.serving_revision()
        if self.vault_path is None:
            return {
                "state": "missing",
                "active_revision": None,
                "serving_revision": serving,
                "query_ready": serving is not None,
                "indexed_notes": 0,
                "indexed_chunks": 0,
                "changed_notes": 0,
                "deleted_notes": 0,
                "reason": "Vault is not configured",
            }
        status = await self._raw_status()
        payload = asdict(status)
        payload["serving_revision"] = serving
        payload["query_ready"] = serving is not None
        if status.active_revision != serving and (status.active_revision is not None or serving):
            payload["state"] = "stale"
            payload["reason"] = "Active and serving revisions differ"
        elif status.state == "current" and serving is None:
            payload["state"] = "stale"
            payload["reason"] = "The active revision is not loaded for queries"
        return payload

    async def active_revision_name(self) -> str | None:
        if self.vault_path is None:
            return None
        try:
            revision = await await_thread(active_revision, self.vault_path)
            return revision.name
        except RuntimeError:
            return None

    async def build(self, *, full_rebuild: bool):
        vault = self._require_vault()
        async with self._index_lock:
            embeddings = await await_thread(get_embeddings)
            result = await await_thread(build_index, vault, embeddings, full_rebuild=full_rebuild)
            # Activation has completed, but the serving slot is unchanged until the
            # candidate owns all query resources successfully.
            candidate_pipeline = await await_thread(
                create_v4_query_pipeline,
                vault,
                embeddings=embeddings,
                settings=self.settings,
                revision_path=result.path,
            )
            await self._swap(_PipelineSlot(candidate_pipeline, result.revision))
            return result

    async def prune(self):
        vault = self._require_vault()
        async with self._index_lock:
            return await await_thread(prune_revisions, vault)

    def _require_vault(self) -> Path:
        if self.vault_path is None:
            raise IndexPathError("Vault is not configured")
        return self.vault_path


# Pydantic models
class Question(BaseModel):
    text: str = Field(..., description="The question you want to ask", max_length=5000)
    session_id: Optional[str] = Field(None, description="Session ID to maintain context")


class Source(BaseModel):
    source: str = Field(..., description="The source of the information")
    score: float = Field(0.0, description="Retrieval relevance score (higher is better)")
    retrieval_type: str = Field("retrieved", description="Retrieval method")


class Answer(BaseModel):
    question: str
    result: str
    sources: List[Source]
    text_blocks: List[str]
    process_time: float = Field(..., description="Processing time in seconds")
    session_id: str = Field(..., description="Session ID used")


class IndexBuildRequest(BaseModel):
    full_rebuild: bool = False


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _source_list(documents) -> list[Source]:
    return [
        Source(
            source=str(document.metadata.get("source", "Unknown")),
            score=float(document.metadata.get("score", 0.0)),
            retrieval_type=str(document.metadata.get("retrieval_type", "retrieved")),
        )
        for document in documents
    ]


def create_app(vault_path: Optional[str] = None) -> FastAPI:
    """Create the application without building an index during startup."""
    runtime_settings = get_settings().model_copy(deep=True)
    configured_vault = vault_path or runtime_settings.obsidian_path
    if configured_vault:
        runtime_settings.configure_paths(configured_vault)
    runtime = _Runtime(
        Path(configured_vault) if configured_vault else None,
        settings=runtime_settings,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logger.info("Starting ObsidianRAG API v4")
        with settings_override(runtime.settings):
            await runtime.startup()
            try:
                yield
            finally:
                logger.info("Shutting down ObsidianRAG application")
                await runtime.shutdown()

    from obsidianrag import __version__

    application = FastAPI(
        title="ObsidianRAG API",
        description="API for querying Obsidian notes using RAG",
        version=__version__,
        lifespan=lifespan,
    )
    application.state.runtime = runtime

    application.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.middleware("http")
    async def add_process_time_header(request, call_next):
        start_time = time.time()
        with settings_override(runtime.settings):
            response = await call_next(request)
        response.headers["X-Process-Time"] = str(time.time() - start_time)
        return response

    _register_routes(application)
    return application


def _register_routes(application: FastAPI) -> None:
    """Register the v4-only HTTP contract."""
    runtime: _Runtime = application.state.runtime

    @application.get("/", summary="Root endpoint")
    async def root():
        from obsidianrag import __version__

        return {
            "message": "Welcome to ObsidianRAG API",
            "api_version": API_VERSION,
            "version": __version__,
        }

    @application.post("/ask", response_model=Answer, summary="Ask a question")
    async def ask(question: Question):
        start_time = time.time()
        session_id = question.session_id or str(uuid.uuid4())
        async with runtime.session_turn(session_id):
            try:
                slot = await runtime.acquire()
            except _IndexNotReady as error:
                raise _error(503, "index_not_ready", "Build or load the v4 index first") from error
            try:
                history = runtime.histories.get(session_id)
                result = await await_thread(slot.pipeline.ask, question.text, history)
                history.append((question.text, result.answer))
                runtime.histories.set(session_id, history)
                sources = _source_list(result.documents)
                return Answer(
                    question=result.question,
                    result=result.answer,
                    sources=sources,
                    text_blocks=[document.page_content for document in result.documents],
                    process_time=time.time() - start_time,
                    session_id=session_id,
                )
            except ValueError as error:
                raise _error(400, "invalid_question", "Question is invalid") from error
            except HTTPException:
                raise
            except Exception as error:
                logger.error("Query failed: %s", error, exc_info=True)
                raise _error(500, "query_failed", "The query could not be completed") from error
            finally:
                await runtime.release(slot)

    @application.post("/ask/stream", summary="Ask a question with streaming")
    async def ask_stream(question: Question):
        try:
            slot = await runtime.acquire()
        except _IndexNotReady as error:
            raise _error(503, "index_not_ready", "Build or load the v4 index first") from error

        session_id = question.session_id or str(uuid.uuid4())

        async def event_generator() -> AsyncGenerator[str, None]:
            async with runtime.session_turn(session_id):
                history = runtime.histories.get(session_id)
                last_event: dict[str, Any] | None = None
                try:
                    yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"
                    async for event in slot.pipeline.stream(question.text, history):
                        last_event = event
                        yield f"data: {json.dumps(event)}\n\n"
                    if last_event and last_event.get("type") == "answer":
                        history.append((question.text, str(last_event.get("answer", ""))))
                        runtime.histories.set(session_id, history)
                except Exception as error:
                    logger.error("Streaming query failed: %s", error, exc_info=True)
                    event = {
                        "type": "error",
                        "code": "query_failed",
                        "message": "The query could not be completed",
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            background=BackgroundTask(runtime.release, slot),
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get("/capabilities", summary="Backend protocol capabilities")
    async def capabilities():
        from obsidianrag import __version__

        return {
            "api_version": API_VERSION,
            "backend_version": __version__,
            "features": [
                "hybrid-retrieval",
                "incremental-indexing",
                "index-lifecycle",
                "sse",
            ],
            "providers": ["ollama", "lmstudio", "custom"],
        }

    @application.get("/health", summary="System status")
    async def health():
        from obsidianrag import __version__

        settings = runtime.settings
        serving = await runtime.serving_revision()
        active = await runtime.active_revision_name()
        return {
            "status": "ok",
            "api_version": API_VERSION,
            "version": __version__,
            "query_ready": serving is not None,
            "active_revision": active,
            "serving_revision": serving,
            "llm_provider": settings.llm_provider,
            "llm_api_format": settings.llm_api_format,
            "model": settings.llm_model,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model
            if settings.embedding_provider == "huggingface"
            else settings.ollama_embedding_model,
        }

    @application.get("/models", summary="Available LLM models")
    async def models():
        try:
            return {"models": await await_thread(list_llm_models)}
        except Exception as error:
            logger.warning("Could not list LLM models: %s", error)
            raise _error(502, "models_unavailable", "Could not list available models") from error

    @application.get("/index/status", summary="v4 index status")
    async def get_index_status():
        try:
            return await runtime.status()
        except IndexPathError as error:
            raise _error(400, "unsafe_index_path", "Index paths are unsafe") from error
        except Exception as error:
            logger.error("Could not inspect v4 index: %s", error, exc_info=True)
            raise _error(500, "index_status_failed", "Could not inspect the v4 index") from error

    @application.post("/index/build", summary="Build or refresh the v4 index")
    async def build(request: IndexBuildRequest):
        try:
            result = await runtime.build(full_rebuild=request.full_rebuild)
            return {
                "status": "success",
                "revision": result.revision,
                "notes": result.notes,
                "chunks": result.chunks,
                "reused_chunks": result.reused_chunks,
                "reindexed_notes": result.reindexed_notes,
                "deleted_notes": result.deleted_notes,
                "query_ready": True,
            }
        except FullRebuildRequired as error:
            raise _error(409, "full_rebuild_required", "A full rebuild is required") from error
        except IndexBuildLocked as error:
            raise _error(409, "index_build_locked", "Another index operation is running") from error
        except IndexPathError as error:
            raise _error(400, "unsafe_index_path", "Index paths are unsafe") from error
        except Exception as error:
            logger.error("v4 index build failed: %s", error, exc_info=True)
            raise _error(500, "index_build_failed", "The v4 index could not be built") from error

    @application.post("/index/prune", summary="Prune inactive v4 revisions")
    async def prune():
        try:
            result = await runtime.prune()
            return {
                "status": "success",
                "active_revision": result.active_revision,
                "deleted_revisions": list(result.deleted_revisions),
            }
        except RevisionInUse as error:
            raise _error(409, "revision_in_use", "An inactive revision is still in use") from error
        except (IndexCorruptionError, IndexBuildLocked) as error:
            raise _error(409, "index_not_ready", "No prunable v4 index is ready") from error
        except IndexPathError as error:
            raise _error(400, "unsafe_index_path", "Index paths are unsafe") from error
        except Exception as error:
            logger.error("v4 index prune failed: %s", error, exc_info=True)
            raise _error(
                500, "index_prune_failed", "Inactive revisions could not be pruned"
            ) from error


# Default app for direct uvicorn usage
app = create_app()


def run_server(vault_path: str, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the v4 server programmatically."""
    uvicorn.run(create_app(vault_path), host=host, port=port)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
