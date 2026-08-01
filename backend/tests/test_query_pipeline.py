"""Tests for the shared v4 query pipeline."""

from threading import Event, Thread
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
    assert "every relevant concrete name, command, number" in sync_messages[0].content
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


def test_pipeline_merges_two_strong_lexical_passages_from_the_same_source(tmp_path):
    retriever = MagicMock()
    retriever.invoke.return_value = [
        Document(
            page_content="First passage",
            metadata={
                "source": "Note.md",
                "chunk_id": "one",
                "score": 10.0,
                "retrieval_type": "lexical",
            },
        ),
        Document(
            page_content="Second passage",
            metadata={
                "source": "Note.md",
                "chunk_id": "two",
                "score": 8.0,
                "retrieval_type": "lexical",
            },
        ),
        Document(
            page_content="Other source",
            metadata={
                "source": "Other.md",
                "chunk_id": "three",
                "score": 7.5,
                "retrieval_type": "lexical",
            },
        ),
        Document(
            page_content="Other source detail",
            metadata={
                "source": "Other.md",
                "chunk_id": "four",
                "score": 7.2,
                "retrieval_type": "lexical",
            },
        ),
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Both passages [1].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path, k=2).ask("Question")

    assert len(result.documents) == 2
    assert result.documents[0].page_content == "First passage\n\nSecond passage"
    assert result.documents[0].metadata["passage_chunk_ids"] == ["one", "two"]
    assert result.documents[1].page_content == "Other source"
    assert result.citations == ("Note.md",)


@pytest.mark.parametrize("second_score, expected_passages", [(7.0, 2), (6.9, 1)])
def test_passage_merge_applies_inclusive_relative_threshold(
    tmp_path, second_score, expected_passages
):
    retriever = MagicMock()
    retriever.invoke.return_value = [
        Document(
            page_content="Primary",
            metadata={
                "source": "Note.md",
                "chunk_id": "one",
                "score": 10.0,
                "retrieval_type": "lexical",
            },
        ),
        Document(
            page_content="Detail",
            metadata={
                "source": "Note.md",
                "chunk_id": "two",
                "score": second_score,
                "retrieval_type": "lexical",
            },
        ),
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Answer [1].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path).ask("Question")

    assert len(result.documents[0].metadata["passage_chunk_ids"]) == expected_passages


def test_context_selection_drops_low_relative_lexical_source(tmp_path):
    retriever = MagicMock()
    retriever.invoke.return_value = [
        Document(
            page_content="Primary",
            metadata={"source": "Primary.md", "score": 10.0, "retrieval_type": "lexical"},
        ),
        Document(
            page_content="Noise",
            metadata={"source": "Noise.md", "score": 6.9, "retrieval_type": "lexical"},
        ),
        Document(
            page_content="Vector fallback",
            metadata={"source": "Fallback.md", "score": 0.5, "lexical_score": 0.0},
        ),
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Primary [1].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path).ask("Question")

    assert [document.metadata["source"] for document in result.documents] == [
        "Primary.md",
        "Fallback.md",
    ]


def test_context_selection_uses_best_lexical_score_when_hybrid_leader_is_vector_only(
    tmp_path,
):
    retriever = MagicMock()
    retriever.invoke.return_value = [
        Document(
            page_content="Vector leader",
            metadata={"source": "Vector.md", "score": 1.0, "lexical_score": 0.0},
        ),
        Document(
            page_content="Lexical leader",
            metadata={"source": "Lexical.md", "score": 0.9, "lexical_score": 10.0},
        ),
        Document(
            page_content="Noise",
            metadata={"source": "Noise.md", "score": 0.8, "lexical_score": 6.0},
        ),
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Answer [1] [2].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path).ask("Question")

    assert [document.metadata["source"] for document in result.documents] == [
        "Vector.md",
        "Lexical.md",
    ]


def test_context_selection_keeps_close_lexical_sources(tmp_path):
    retriever = MagicMock()
    retriever.invoke.return_value = [
        Document(
            page_content="Primary",
            metadata={"source": "Primary.md", "score": 10.0, "retrieval_type": "lexical"},
        ),
        Document(
            page_content="Related",
            metadata={"source": "Related.md", "score": 7.0, "retrieval_type": "lexical"},
        ),
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Primary [1], related [2].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path).ask("Question")

    assert [document.metadata["source"] for document in result.documents] == [
        "Primary.md",
        "Related.md",
    ]


def test_context_selection_always_keeps_top_source(tmp_path):
    retriever = MagicMock()
    retriever.invoke.return_value = [
        Document(
            page_content="Only candidate",
            metadata={"source": "Only.md", "score": 1.0, "retrieval_type": "lexical"},
        )
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Only [1].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path).ask("Question")

    assert len(result.documents) == 1


def test_context_selection_preserves_top_k_without_lexical_scores(tmp_path):
    retriever = MagicMock()
    retriever.invoke.return_value = [
        Document(
            page_content=str(index), metadata={"source": f"{index}.md", "score": 1 - index / 10}
        )
        for index in range(3)
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Answer [1].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path, k=2).ask("Question")

    assert [document.metadata["source"] for document in result.documents] == ["0.md", "1.md"]


def test_multipart_question_retrieves_each_segment_and_keeps_each_leading_source(tmp_path):
    retriever = MagicMock()
    retriever.invoke.side_effect = [
        [
            Document(
                page_content="First answer",
                metadata={"source": "First.md", "score": 10.0, "retrieval_type": "lexical"},
            ),
            Document(
                page_content="First noise",
                metadata={"source": "Noise.md", "score": 5.0, "retrieval_type": "lexical"},
            ),
        ],
        [
            Document(
                page_content="Second answer",
                metadata={"source": "Second.md", "score": 3.0, "retrieval_type": "lexical"},
            )
        ],
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="First [1], second [2].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path, k=3).ask(
        "First question?; Second question?"
    )

    assert [call.args[0] for call in retriever.invoke.call_args_list] == [
        "First question?",
        "Second question?",
    ]
    assert [document.metadata["source"] for document in result.documents] == [
        "First.md",
        "Second.md",
    ]
    assert result.citations == ("First.md", "Second.md")


def test_multipart_context_applies_relative_threshold_per_segment(tmp_path):
    retriever = MagicMock()
    retriever.invoke.side_effect = [
        [
            Document(
                page_content="First",
                metadata={"source": "First.md", "score": 10.0, "retrieval_type": "lexical"},
            ),
            Document(
                page_content="Related first",
                metadata={"source": "First-related.md", "score": 7.0, "retrieval_type": "lexical"},
            ),
        ],
        [
            Document(
                page_content="Second",
                metadata={"source": "Second.md", "score": 3.0, "retrieval_type": "lexical"},
            ),
            Document(
                page_content="Related second",
                metadata={"source": "Second-related.md", "score": 2.1, "retrieval_type": "lexical"},
            ),
        ],
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Answer [1] [2] [3] [4].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path, k=4).ask("First?; Second?")

    assert [document.metadata["source"] for document in result.documents] == [
        "First.md",
        "Second.md",
        "First-related.md",
        "Second-related.md",
    ]


def test_multipart_merges_passages_when_the_same_source_leads_both_parts(tmp_path):
    retriever = MagicMock()
    retriever.invoke.side_effect = [
        [
            Document(
                page_content="First part primary",
                metadata={
                    "source": "Same.md",
                    "chunk_id": "a1",
                    "score": 10.0,
                    "retrieval_type": "lexical",
                },
            ),
            Document(
                page_content="First part detail",
                metadata={
                    "source": "Same.md",
                    "chunk_id": "a2",
                    "score": 8.0,
                    "retrieval_type": "lexical",
                },
            ),
        ],
        [
            Document(
                page_content="Second part primary",
                metadata={
                    "source": "Same.md",
                    "chunk_id": "b1",
                    "score": 9.0,
                    "retrieval_type": "lexical",
                },
            ),
            Document(
                page_content="Second part detail",
                metadata={
                    "source": "Same.md",
                    "chunk_id": "b2",
                    "score": 7.5,
                    "retrieval_type": "lexical",
                },
            ),
        ],
        [
            Document(
                page_content="Third part primary",
                metadata={
                    "source": "Same.md",
                    "chunk_id": "c1",
                    "score": 8.0,
                    "retrieval_type": "lexical",
                },
            ),
            Document(
                page_content="Third part detail",
                metadata={
                    "source": "Same.md",
                    "chunk_id": "c2",
                    "score": 6.0,
                    "retrieval_type": "lexical",
                },
            ),
        ],
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="All parts [1].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path, k=5).ask(
        "First?; Second?; Third?"
    )

    assert len(result.documents) == 1
    assert result.documents[0].metadata["passage_chunk_ids"] == ["a1", "b1", "c1", "a2"]
    assert result.documents[0].metadata["context_segments"] == [0, 1, 2]
    assert "First part detail" in result.documents[0].page_content
    assert "Second part primary" in result.documents[0].page_content
    assert "Third part primary" in result.documents[0].page_content


def test_multipart_filters_each_segment_before_merging_shared_sources(tmp_path):
    retriever = MagicMock()
    retriever.invoke.side_effect = [
        [
            Document(
                page_content="First",
                metadata={
                    "source": "Same.md",
                    "chunk_id": "a",
                    "score": 10.0,
                    "retrieval_type": "lexical",
                },
            )
        ],
        [
            Document(
                page_content="Second",
                metadata={
                    "source": "Same.md",
                    "chunk_id": "b",
                    "score": 10.0,
                    "retrieval_type": "lexical",
                },
            ),
            Document(
                page_content="Noise",
                metadata={
                    "source": "Noise.md",
                    "chunk_id": "noise",
                    "score": 6.0,
                    "retrieval_type": "lexical",
                },
            ),
        ],
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Answer [1].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path, k=5).ask("First?; Second?")

    assert [document.metadata["source"] for document in result.documents] == ["Same.md"]
    assert result.documents[0].metadata["context_segments"] == [0, 1]


def test_multipart_rejects_more_parts_than_the_bounded_merge_can_preserve(tmp_path):
    pipeline = QueryPipeline(MagicMock(), MagicMock(), vault_path=tmp_path)

    with pytest.raises(ValueError, match="at most 4"):
        pipeline.ask("one; two; three; four; five")


def test_multipart_context_limits_each_segment_to_two_sources(tmp_path):
    retriever = MagicMock()
    retriever.invoke.side_effect = [
        [
            Document(
                page_content=str(index),
                metadata={
                    "source": f"First-{index}.md",
                    "score": 10.0 - index,
                    "retrieval_type": "lexical",
                },
            )
            for index in range(3)
        ],
        [
            Document(
                page_content=str(index),
                metadata={
                    "source": f"Second-{index}.md",
                    "score": 10.0 - index,
                    "retrieval_type": "lexical",
                },
            )
            for index in range(3)
        ],
    ]
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Answer [1] [2] [3] [4].")

    result = QueryPipeline(retriever, model, vault_path=tmp_path, k=5).ask("First?; Second?")

    assert [document.metadata["source"] for document in result.documents] == [
        "First-0.md",
        "Second-0.md",
        "First-1.md",
        "Second-1.md",
    ]


def test_pipeline_retrieves_once_and_filters_invalid_citations(tmp_path):
    retriever = MagicMock()
    retriever.invoke.return_value = _documents(tmp_path)
    model = MagicMock()
    model.invoke.return_value = AIMessage(
        content="One [SOURCE 1], repeated [1], invalid [SOURCE 3]."
    )
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
        patch("obsidianrag.v4.LexicalRetriever", return_value=lexical),
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


def test_hybrid_factory_reuses_explicit_embeddings(tmp_path):
    embeddings = MagicMock()
    retriever = MagicMock()

    with (
        patch("obsidianrag.v4.Retriever", return_value=retriever) as retriever_factory,
        patch(
            "obsidianrag.core.query_pipeline.create_chat_model",
            return_value=(MagicMock(), "test"),
        ),
        patch("obsidianrag.core.db_service.get_embeddings") as get_embeddings,
    ):
        revision_path = tmp_path / "revision"
        pipeline = create_v4_query_pipeline(
            tmp_path, embeddings=embeddings, revision_path=revision_path
        )

    get_embeddings.assert_not_called()
    retriever_factory.assert_called_once_with(
        tmp_path.resolve(), embeddings, revision_path=revision_path
    )
    pipeline.close()


def test_factory_rejects_invalid_k_before_opening_retriever(tmp_path):
    with (
        patch("obsidianrag.v4.LexicalRetriever") as lexical,
        pytest.raises(ValueError, match="k must be at least 1"),
    ):
        create_v4_query_pipeline(tmp_path, engine="v4-fts", k=0)

    lexical.assert_not_called()


def test_close_waits_for_active_retrieval(tmp_path):
    started = Event()
    release = Event()
    closed = Event()

    class BlockingRetriever:
        def invoke(self, _query, k):
            started.set()
            release.wait(timeout=2)
            return []

        def close(self):
            closed.set()

    pipeline = QueryPipeline(BlockingRetriever(), MagicMock(), vault_path=tmp_path)
    retrieval_thread = Thread(target=pipeline._retrieve, args=("Question",))
    close_thread = Thread(target=pipeline.close)
    retrieval_thread.start()
    assert started.wait(timeout=1)
    close_thread.start()

    assert not closed.wait(timeout=0.05)
    release.set()
    retrieval_thread.join(timeout=1)
    close_thread.join(timeout=1)
    assert closed.is_set()


def test_factory_closes_retriever_when_model_creation_fails(tmp_path):
    lexical = MagicMock()

    with (
        patch("obsidianrag.v4.LexicalRetriever", return_value=lexical),
        patch(
            "obsidianrag.core.query_pipeline.create_chat_model",
            side_effect=RuntimeError("provider unavailable"),
        ),
        pytest.raises(RuntimeError, match="provider unavailable"),
    ):
        create_v4_query_pipeline(tmp_path, engine="v4-fts")

    lexical.close.assert_called_once_with()
