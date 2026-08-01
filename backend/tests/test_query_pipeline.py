"""Tests for the shared v4 query pipeline."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from obsidianrag.core.query_pipeline import QueryPipeline, create_v4_query_pipeline


def _documents(vault):
    return [
        Document(
            page_content="First fact",
            metadata={
                "source": str(vault / "Notes" / "First.md"),
                "score": 0.9,
                "retrieval_type": "hybrid",
            },
        ),
        Document(
            page_content="Duplicate chunk",
            metadata={"source": str(vault / "Notes" / "First.md")},
        ),
        Document(
            page_content="Second fact",
            metadata={"source": "Notes/Second.md", "score": 0.8},
        ),
    ]


def _message_signature(messages):
    return [(type(message).__name__, message.content) for message in messages]


def test_sync_and_stream_share_prompt_history_and_source_semantics(tmp_path):
    retriever = MagicMock()
    retriever.invoke.return_value = _documents(tmp_path)
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Supported [1], second [2], invalid [9].")
    pipeline = QueryPipeline(retriever, model, vault_path=tmp_path, k=2)
    history = [("Previous question", "Previous answer")]

    sync_result = pipeline.ask("Current question", history)
    sync_messages = model.invoke.call_args.args[0]

    streamed_messages = []

    async def fake_stream(messages, _settings, *, model):
        streamed_messages.extend(messages)
        assert model is pipeline.model
        for token in ("Supported [1], ", "second [2], invalid [9]."):
            yield token

    async def collect_events():
        with patch("obsidianrag.core.query_pipeline.stream_chat_model_tokens", fake_stream):
            return [event async for event in pipeline.stream("Current question", history)]

    import asyncio

    events = asyncio.run(collect_events())
    final = events[-1]

    assert retriever.invoke.call_count == 2
    retriever.invoke.assert_called_with("Current question", k=2)
    assert _message_signature(sync_messages) == _message_signature(streamed_messages)
    assert [message.content for message in sync_messages[1:]] == [
        "Previous question",
        "Previous answer",
        "Current question",
    ]
    assert "[SOURCE 1]\nPath: Notes/First.md" in sync_messages[0].content
    assert "[SOURCE 2]\nPath: Notes/Second.md" in sync_messages[0].content
    assert "untrusted data" in sync_messages[0].content
    assert "does not support an answer" in sync_messages[0].content
    assert sync_result.citations == ("Notes/First.md", "Notes/Second.md")
    assert final["answer"] == sync_result.answer
    assert final["citations"] == list(sync_result.citations)
    assert [source["source"] for source in final["sources"]] == [
        "Notes/First.md",
        "Notes/Second.md",
    ]
    assert [event["type"] for event in events] == [
        "status",
        "retrieve_complete",
        "status",
        "token",
        "token",
        "answer",
    ]


def test_pipeline_retrieves_once_and_filters_invalid_citations(tmp_path):
    retriever = MagicMock()
    retriever.invoke.return_value = _documents(tmp_path)
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="One [1], repeated [1], invalid [3].")
    pipeline = QueryPipeline(retriever, model, vault_path=tmp_path, k=2)

    result = pipeline.ask("Question")

    retriever.invoke.assert_called_once_with("Question", k=2)
    assert len(result.documents) == 2
    assert result.citations == ("Notes/First.md",)


@pytest.mark.parametrize(
    "question", ["", "   ", "x" * 5001], ids=["empty", "whitespace", "too-long"]
)
def test_pipeline_validates_question_before_retrieval(tmp_path, question):
    retriever = MagicMock()
    pipeline = QueryPipeline(retriever, MagicMock(), vault_path=tmp_path)

    with pytest.raises(ValueError):
        pipeline.ask(question)

    retriever.invoke.assert_not_called()


def test_lexical_factory_does_not_load_embeddings_and_owns_retriever(tmp_path):
    lexical = MagicMock()
    model = MagicMock()

    with (
        patch("obsidianrag.v4.ExperimentalLexicalRetriever", return_value=lexical),
        patch("obsidianrag.core.query_pipeline.create_chat_model", return_value=(model, "test")),
        patch("obsidianrag.core.db_service.get_embeddings") as get_embeddings,
    ):
        pipeline = create_v4_query_pipeline(tmp_path, engine="v4-fts", k=3)

    get_embeddings.assert_not_called()
    assert pipeline.retriever is lexical
    assert pipeline.k == 3
    assert pipeline.retrieval_k == 25

    pipeline.close()
    lexical.close.assert_called_once_with()


def test_factory_rejects_invalid_k_before_opening_retriever(tmp_path):
    with (
        patch("obsidianrag.v4.ExperimentalLexicalRetriever") as lexical,
        pytest.raises(ValueError, match="k must be at least 1"),
    ):
        create_v4_query_pipeline(tmp_path, engine="v4-fts", k=0)

    lexical.assert_not_called()


def test_factory_closes_retriever_when_model_creation_fails(tmp_path):
    lexical = MagicMock()

    with (
        patch("obsidianrag.v4.ExperimentalLexicalRetriever", return_value=lexical),
        patch(
            "obsidianrag.core.query_pipeline.create_chat_model",
            side_effect=RuntimeError("provider unavailable"),
        ),
        pytest.raises(RuntimeError, match="provider unavailable"),
    ):
        create_v4_query_pipeline(tmp_path, engine="v4-fts")

    lexical.close.assert_called_once_with()
