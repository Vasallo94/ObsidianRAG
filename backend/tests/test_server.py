"""Focused tests for the v4 FastAPI runtime."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from langchain_core.documents import Document

import obsidianrag.api.server as server
from obsidianrag.config import get_settings
from obsidianrag.core.query_pipeline import QueryResult, await_thread
from obsidianrag.v4 import (
    FullRebuildRequired,
    IndexBuildLocked,
    IndexBuildResult,
    IndexCorruptionError,
    IndexPathError,
    IndexStatus,
    PruneResult,
    RevisionInUse,
)


def _status(state: str = "missing", revision: str | None = None) -> IndexStatus:
    return IndexStatus(state=state, active_revision=revision)  # type: ignore[arg-type]


def _pipeline(answer: str = "Answer [1]") -> MagicMock:
    pipeline = MagicMock()
    document = Document(
        page_content="Evidence",
        metadata={"source": "Notes/Test.md", "score": 0.9, "retrieval_type": "hybrid"},
    )
    pipeline.ask.return_value = QueryResult(
        question="Question", answer=answer, documents=(document,), citations=("Notes/Test.md",)
    )

    async def stream(_question, _history):
        yield {"type": "status", "message": "Searching your notes..."}
        yield {
            "type": "answer",
            "question": "Question",
            "answer": answer,
            "sources": [{"source": "Notes/Test.md", "score": 0.9}],
            "citations": ["Notes/Test.md"],
        }

    pipeline.stream = stream
    return pipeline


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    statuses,
    pipelines=(),
) -> tuple[server.FastAPI, MagicMock, MagicMock]:
    if isinstance(statuses, list):
        status_values = iter(statuses)
        current_status = None

        def next_status(_vault, embeddings=None):
            nonlocal current_status
            if embeddings is None:
                current_status = next(status_values)
            return current_status

        status_mock = MagicMock(side_effect=next_status)
    else:
        status_mock = MagicMock(return_value=statuses)
    pipeline_mock = MagicMock(side_effect=list(pipelines))
    monkeypatch.setattr(server, "get_embeddings", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(server, "index_status", status_mock)
    monkeypatch.setattr(server, "create_v4_query_pipeline", pipeline_mock)
    monkeypatch.setattr(
        server,
        "active_revision",
        MagicMock(side_effect=IndexCorruptionError("missing")),
    )
    return server.create_app(str(tmp_path)), status_mock, pipeline_mock


def _events(response) -> list[dict]:
    return [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line]


def test_startup_missing_never_builds_and_exposes_api4_health(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app, _, pipeline_factory = _configure(monkeypatch, tmp_path, statuses=_status())
    build = MagicMock()
    monkeypatch.setattr(server, "build_index", build)

    with TestClient(app) as client:
        capabilities = client.get("/capabilities").json()
        health = client.get("/health")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["api_version"] == 4
    assert health.json()["query_ready"] is False
    assert capabilities["api_version"] == 4
    assert capabilities["features"] == [
        "hybrid-retrieval",
        "incremental-indexing",
        "index-lifecycle",
        "sse",
    ]
    assert "ollama" in capabilities["providers"]
    build.assert_not_called()
    pipeline_factory.assert_not_called()


def test_apps_isolate_settings_without_creating_v3_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    vault_one = tmp_path / "one"
    vault_two = tmp_path / "two"
    vault_one.mkdir()
    vault_two.mkdir()
    seen: list[tuple[Path, str]] = []

    def inspect_status(vault: Path, _embeddings=None) -> IndexStatus:
        seen.append((vault, get_settings().obsidian_path))
        return _status()

    monkeypatch.setattr(server, "get_embeddings", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(server, "index_status", inspect_status)
    app_one = server.create_app(str(vault_one))
    app_two = server.create_app(str(vault_two))

    with TestClient(app_one) as client:
        assert client.get("/index/status").status_code == 200
    with TestClient(app_two) as client:
        assert client.get("/index/status").status_code == 200

    assert app_one.state.runtime.settings is not app_two.state.runtime.settings
    assert app_one.state.runtime.settings.obsidian_path == str(vault_one)
    assert app_two.state.runtime.settings.obsidian_path == str(vault_two)
    assert {(vault, configured) for vault, configured in seen} == {
        (vault_one, str(vault_one)),
        (vault_two, str(vault_two)),
    }
    assert not (vault_one / ".obsidianrag").exists()
    assert not (vault_two / ".obsidianrag").exists()


def test_missing_pipeline_queries_return_structured_503(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app, _, _ = _configure(monkeypatch, tmp_path, statuses=_status())

    with TestClient(app) as client:
        answer = client.post("/ask", json={"text": "Question"})
        stream = client.post("/ask/stream", json={"text": "Question"})

    for response in (answer, stream):
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "code": "index_not_ready",
            "message": "Build or load the v4 index first",
        }


def test_same_session_turns_serialize_without_blocking_other_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    pipeline = _pipeline()
    started = Event()
    release = Event()
    observed: list[tuple[str, list[tuple[str, str]]]] = []
    template = pipeline.ask.return_value

    def controlled_ask(question: str, history: list[tuple[str, str]]) -> QueryResult:
        observed.append((question, list(history)))
        if question == "first":
            started.set()
            assert release.wait(5)
        return QueryResult(
            question=question,
            answer=f"{question} answer",
            documents=template.documents,
            citations=template.citations,
        )

    pipeline.ask.side_effect = controlled_ask
    app, _, _ = _configure(
        monkeypatch, tmp_path, statuses=_status("current", "revision-1"), pipelines=[pipeline]
    )

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(client.post, "/ask", json={"text": "first", "session_id": "shared"})
        assert started.wait(2)
        second = executor.submit(
            client.post, "/ask", json={"text": "second", "session_id": "shared"}
        )
        other = executor.submit(
            client.post, "/ask", json={"text": "other", "session_id": "independent"}
        )
        try:
            assert other.result(timeout=2).status_code == 200
            assert not second.done()
        finally:
            release.set()
        assert first.result(timeout=2).status_code == 200
        assert second.result(timeout=2).status_code == 200

    histories = {question: history for question, history in observed}
    assert histories["first"] == []
    assert histories["other"] == []
    assert histories["second"] == [("first", "first answer")]


def test_ask_uses_v4_pipeline_and_preserves_response_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    pipeline = _pipeline()
    app, _, _ = _configure(
        monkeypatch, tmp_path, statuses=_status("current", "revision-1"), pipelines=[pipeline]
    )

    with TestClient(app) as client:
        response = client.post("/ask", json={"text": "Question", "session_id": "session"})

    assert response.status_code == 200
    assert response.json()["result"] == "Answer [1]"
    assert response.json()["sources"][0]["source"] == "Notes/Test.md"
    assert response.json()["text_blocks"] == ["Evidence"]
    pipeline.ask.assert_called_once()
    pipeline.close.assert_called_once_with()


def test_stream_history_propagates_to_the_next_session_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    pipeline = _pipeline("Stream answer [1]")
    observed: list[tuple[str, list[tuple[str, str]]]] = []
    template: QueryResult = pipeline.ask.return_value

    def record_history(question: str, history: list[tuple[str, str]]) -> QueryResult:
        observed.append((question, list(history)))
        return template

    pipeline.ask.side_effect = record_history
    app, _, _ = _configure(
        monkeypatch, tmp_path, statuses=_status("current", "revision-1"), pipelines=[pipeline]
    )

    with TestClient(app) as client:
        streamed = client.post("/ask/stream", json={"text": "First", "session_id": "shared"})
        answer = client.post("/ask", json={"text": "Second", "session_id": "shared"})

    assert streamed.status_code == 200
    assert answer.status_code == 200
    assert observed == [("Second", [("First", "Stream answer [1]")])]


def test_successful_build_swaps_and_closes_unused_old_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    old = _pipeline("old")
    new = _pipeline("new")
    app, _, pipeline_factory = _configure(
        monkeypatch,
        tmp_path,
        statuses=_status("current", "revision-1"),
        pipelines=[old, new],
    )
    monkeypatch.setattr(
        server,
        "build_index",
        MagicMock(
            return_value=IndexBuildResult(
                revision="revision-2", notes=2, chunks=3, path=tmp_path / "revision-2"
            )
        ),
    )

    with TestClient(app) as client:
        response = client.post("/index/build", json={})
        health = client.get("/health")

    assert response.status_code == 200
    assert response.json()["revision"] == "revision-2"
    assert health.json()["serving_revision"] == "revision-2"
    candidate_call = pipeline_factory.call_args_list[1]
    assert candidate_call.kwargs["revision_path"] == tmp_path / "revision-2"
    assert candidate_call.kwargs["settings"] is app.state.runtime.settings
    old.close.assert_called_once_with()
    new.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_old_checked_out_slot_closes_only_after_release(tmp_path: Path):
    runtime = server._Runtime(tmp_path)
    old = _pipeline("old")
    new = _pipeline("new")
    await runtime._swap(server._PipelineSlot(old, "revision-1"))
    checked_out = await runtime.acquire()

    await runtime._swap(server._PipelineSlot(new, "revision-2"))
    old.close.assert_not_called()
    assert await runtime.serving_revision() == "revision-2"

    await runtime.release(checked_out)
    old.close.assert_called_once_with()
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_cancelled_thread_query_keeps_old_slot_until_worker_finishes(tmp_path: Path):
    runtime = server._Runtime(tmp_path)
    old = _pipeline("old")
    new = _pipeline("new")
    started = Event()
    release_worker = Event()

    def blocking_ask(_question, _history):
        started.set()
        release_worker.wait(2)
        return old.ask.return_value

    old.ask.side_effect = blocking_ask
    await runtime._swap(server._PipelineSlot(old, "revision-1"))

    async def query() -> None:
        slot = await runtime.acquire()
        try:
            await await_thread(slot.pipeline.ask, "Question", [])
        finally:
            await runtime.release(slot)

    task = asyncio.create_task(query())
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    await runtime._swap(server._PipelineSlot(new, "revision-2"))
    await asyncio.sleep(0)
    old.close.assert_not_called()

    release_worker.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    old.close.assert_called_once_with()
    await runtime.shutdown()


@pytest.mark.parametrize("failure_stage", ["build", "candidate"])
def test_build_or_candidate_failure_preserves_old_serving_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_stage: str
):
    old = _pipeline("old")
    pipeline_effects: list[MagicMock | Exception] = [old]
    if failure_stage == "candidate":
        pipeline_effects.append(RuntimeError("candidate failed"))
    app, _, _ = _configure(
        monkeypatch,
        tmp_path,
        statuses=_status("current", "revision-1"),
        pipelines=pipeline_effects,
    )
    if failure_stage == "build":
        build_effect: object = RuntimeError("build failed")
    else:
        build_effect = IndexBuildResult(
            revision="revision-2", notes=2, chunks=3, path=tmp_path / "revision-2"
        )
    monkeypatch.setattr(server, "build_index", MagicMock(side_effect=[build_effect]))

    with TestClient(app) as client:
        response = client.post("/index/build", json={})
        health = client.get("/health")

    assert response.status_code == 500
    assert health.json()["serving_revision"] == "revision-1"
    old.close.assert_called_once_with()  # shutdown, not failed build


def test_candidate_failure_reports_split_then_noop_build_reconciles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    old = _pipeline("old")
    replacement = _pipeline("new")
    revision = IndexBuildResult(
        revision="revision-2", notes=2, chunks=3, path=tmp_path / "revision-2"
    )
    app, _, pipeline_factory = _configure(
        monkeypatch,
        tmp_path,
        statuses=[
            _status("current", "revision-1"),
            _status("current", "revision-2"),
        ],
        pipelines=[old, RuntimeError("candidate failed"), replacement],
    )
    monkeypatch.setattr(server, "build_index", MagicMock(side_effect=[revision, revision]))

    with TestClient(app) as client:
        failed = client.post("/index/build", json={})
        status = client.get("/index/status")
        reconciled = client.post("/index/build", json={})
        health = client.get("/health")

    assert failed.status_code == 500
    assert status.json()["state"] == "stale"
    assert status.json()["active_revision"] == "revision-2"
    assert status.json()["serving_revision"] == "revision-1"
    assert reconciled.status_code == 200
    assert health.json()["serving_revision"] == "revision-2"
    assert pipeline_factory.call_args_list[1].kwargs["revision_path"] == revision.path
    assert pipeline_factory.call_args_list[2].kwargs["revision_path"] == revision.path
    old.close.assert_called_once_with()


@pytest.mark.parametrize("stream_fails", [False, True])
def test_sse_releases_pipeline_on_completion_and_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stream_fails: bool
):
    pipeline = _pipeline()
    if stream_fails:

        async def failing_stream(_question, _history):
            yield {"type": "status", "message": "Searching"}
            raise RuntimeError("stream failed")

        pipeline.stream = failing_stream
    app, _, _ = _configure(
        monkeypatch, tmp_path, statuses=_status("current", "revision-1"), pipelines=[pipeline]
    )

    with TestClient(app) as client:
        response = client.post("/ask/stream", json={"text": "Question"})
        events = _events(response)
        assert app.state.runtime._serving.users == 0

    assert response.status_code == 200
    assert events[0]["type"] == "start"
    assert events[-1]["type"] == "done"
    assert any(event["type"] == ("error" if stream_fails else "answer") for event in events)


@pytest.mark.asyncio
async def test_sse_background_releases_slot_when_body_never_starts(tmp_path: Path):
    app = server.create_app(str(tmp_path))
    runtime = app.state.runtime
    pipeline = _pipeline()
    await runtime._swap(server._PipelineSlot(pipeline, "revision-1"))
    route = next(
        route for route in app.routes if isinstance(route, APIRoute) and route.path == "/ask/stream"
    )

    response = await route.endpoint(server.Question(text="Question", session_id=None))
    assert runtime._serving.users == 1
    assert response.background is not None
    await response.background()
    assert runtime._serving.users == 0

    await runtime.shutdown()


def test_status_surfaces_active_serving_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pipeline = _pipeline()
    app, _, _ = _configure(
        monkeypatch,
        tmp_path,
        statuses=[
            _status("current", "revision-1"),
            _status("current", "revision-2"),
        ],
        pipelines=[pipeline],
    )

    with TestClient(app) as client:
        response = client.get("/index/status")

    assert response.status_code == 200
    assert response.json()["state"] == "stale"
    assert response.json()["active_revision"] == "revision-2"
    assert response.json()["serving_revision"] == "revision-1"
    assert response.json()["query_ready"] is True


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (RevisionInUse("busy"), "revision_in_use"),
        (IndexCorruptionError("missing"), "index_not_ready"),
    ],
)
def test_prune_conflicts_are_structured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: Exception, code: str
):
    app, _, _ = _configure(monkeypatch, tmp_path, statuses=_status())
    monkeypatch.setattr(server, "prune_revisions", MagicMock(side_effect=error))

    with TestClient(app) as client:
        response = client.post("/index/prune")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == code
    assert "busy" not in response.text


def test_prune_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app, _, _ = _configure(monkeypatch, tmp_path, statuses=_status())
    monkeypatch.setattr(
        server,
        "prune_revisions",
        MagicMock(return_value=PruneResult(("old",), "active")),
    )

    with TestClient(app) as client:
        response = client.post("/index/prune")

    assert response.json() == {
        "status": "success",
        "active_revision": "active",
        "deleted_revisions": ["old"],
    }


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (FullRebuildRequired("details"), 409, "full_rebuild_required"),
        (IndexBuildLocked("details"), 409, "index_build_locked"),
        (IndexPathError("/private/path"), 400, "unsafe_index_path"),
    ],
)
def test_build_errors_are_safe_and_structured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: Exception,
    status_code: int,
    code: str,
):
    app, _, _ = _configure(monkeypatch, tmp_path, statuses=_status())
    monkeypatch.setattr(server, "build_index", MagicMock(side_effect=error))

    with TestClient(app) as client:
        response = client.post("/index/build", json={})

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert "/private/path" not in response.text


def test_removed_v3_lifecycle_routes_are_not_registered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app, _, _ = _configure(monkeypatch, tmp_path, statuses=_status())

    with TestClient(app) as client:
        assert client.get("/stats").status_code == 404
        assert client.post("/rebuild_db").status_code == 404
