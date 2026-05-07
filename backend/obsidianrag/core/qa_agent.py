"""LangGraph-based QA Agent for ObsidianRAG"""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional, Sequence, Tuple

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from obsidianrag.config import get_settings
from obsidianrag.core.llm_provider import (
    create_chat_model,
    single_human_message,
    stream_chat_model_tokens,
)
from obsidianrag.core.qa_service import create_retriever_with_reranker
from obsidianrag.utils.logger import setup_logger

logger = setup_logger(__name__)

SYSTEM_PROMPT = """You are a personal assistant that answers questions based on the user's Obsidian notes provided below in the CONTEXT section.

CRITICAL RULE - LANGUAGE:
**YOU MUST RESPOND IN THE SAME LANGUAGE AS THE USER'S QUESTION.**
- If the user asks in Spanish respond entirely in Spanish
- If the user asks in English respond entirely in English
- NEVER switch languages. Match the user's language exactly.

OTHER RULES:
1. **USE THE CONTEXT**: The notes below contain the information you need. READ THEM CAREFULLY before answering.
2. **Exact Quotes**: If asked for specific text, quote it EXACTLY as it appears.
3. **Honesty**: ONLY if the context is completely empty or truly irrelevant, say you couldn't find the information.
4. **Format**: Use Markdown for formatting.
5. **Direct**: Be concise and to the point.

IMPORTANT: The context below contains relevant notes. Use them to answer the question.

---
CONTEXT (User's Obsidian Notes):
{context}
---
"""


def _is_safe_vault_path(filepath: str) -> bool:
    """Check that a filepath resolves within the configured vault boundary."""
    settings = get_settings()
    vault = settings.obsidian_path
    if not vault:
        return False
    try:
        resolved = Path(filepath).resolve()
        vault_resolved = Path(vault).resolve()
        return resolved.is_relative_to(vault_resolved)
    except (ValueError, OSError):
        return False


def extract_links_from_content(content: str) -> List[str]:
    """Extract Obsidian [[links]] from content as fallback when metadata is empty"""
    links = re.findall(r"\[\[(.*?)\]\]", content)
    cleaned = [link.split("|")[0].strip() for link in links]
    seen = set()
    unique = []
    for link in cleaned:
        if link and link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def read_full_document(filepath: str) -> str:
    """Read the complete content of a document file"""
    if not _is_safe_vault_path(filepath):
        logger.warning("Blocked read outside vault boundary: %s", filepath)
        return ""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, "r", encoding="latin-1") as f:
                return f.read()
        except Exception as e:
            logger.error("Error reading %s: %s", filepath, e)
            return ""
    except Exception as e:
        logger.error("Error reading %s: %s", filepath, e)
        return ""


class GraphTracer:
    """Tracer for detailed graph execution logging"""

    def __init__(self):
        self.start_time = None
        self.node_times = {}
        self.events = []

    def start(self, question: str, history_len: int):
        self.start_time = time.time()
        self.node_times = {}
        self.events = []
        self._log_event(
            "GRAPH_START",
            {
                "question": question,
                "history_messages": history_len,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def enter_node(self, node_name: str, state_summary: dict):
        self.node_times[node_name] = {"start": time.time()}
        self._log_event(
            "NODE_ENTER:%s" % node_name,
            {
                "state_keys": list(state_summary.keys()),
                "context_docs": state_summary.get("context_count", 0),
                "question": state_summary.get("question", "")[:50],
            },
        )

    def exit_node(self, node_name: str, result_summary: dict):
        if node_name in self.node_times:
            elapsed = time.time() - self.node_times[node_name]["start"]
            self.node_times[node_name]["elapsed"] = elapsed
        else:
            elapsed = 0
        self._log_event(
            "NODE_EXIT:%s" % node_name,
            {"elapsed_seconds": round(elapsed, 3), **result_summary},
        )

    def end(self, result_summary: dict):
        total_time = time.time() - self.start_time if self.start_time else 0
        self._log_event(
            "GRAPH_END",
            {
                "total_elapsed_seconds": round(total_time, 3),
                "node_timings": {
                    k: round(v.get("elapsed", 0), 3) for k, v in self.node_times.items()
                },
                **result_summary,
            },
        )
        self._print_summary()

    def _log_event(self, event_type: str, data: dict):
        event = {"type": event_type, "data": data, "time": time.time()}
        self.events.append(event)
        logger.info("[%s] %s", event_type, json.dumps(data, ensure_ascii=False))

    def _print_summary(self):
        logger.info("=" * 60)
        logger.info("GRAPH EXECUTION SUMMARY")
        logger.info("=" * 60)
        for event in self.events:
            logger.info("  %s: %s", event["type"], event["data"])
        logger.info("=" * 60)


# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: List[Document]
    question: str
    answer: str


# --- Nodes ---


def retrieve_node(state: AgentState, retriever, db, tracer: Optional[GraphTracer] = None):
    """Node to retrieve documents based on the last user message"""
    question = state["question"]

    if tracer:
        tracer.enter_node(
            "retrieve", {"question": question, "context_count": len(state.get("context", []))}
        )

    logger.info("[RETRIEVE NODE] Starting retrieval for: '%s'", question)

    start_retrieval = time.time()
    docs = retriever.invoke(question)
    retrieval_time = time.time() - start_retrieval

    logger.info(
        "[RETRIEVE NODE] Retrieved %d initial documents in %.2fs", len(docs), retrieval_time
    )

    for i, doc in enumerate(docs):
        relevance_score = doc.metadata.get("relevance_score", None)
        if relevance_score is not None:
            doc.metadata["score"] = float(relevance_score)
        else:
            doc.metadata["score"] = 1.0 - (i * 0.1)

    docs = sorted(docs, key=lambda d: d.metadata.get("score", 0), reverse=True)

    for i, doc in enumerate(docs):
        source = doc.metadata.get("source", "Unknown")
        score = doc.metadata.get("score", 0)
        logger.info("   Doc %d (score: %.4f): %s", i + 1, score, os.path.basename(source))

    # Full document expansion for fragmented sources
    source_counts: dict[str, int] = {}
    for doc in docs:
        source = doc.metadata.get("source", "")
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1

    fragmented_sources = {s for s, count in source_counts.items() if count > 1}

    if fragmented_sources:
        logger.info(
            "[FULL DOC] Detected %d fragmented documents, reading full content...",
            len(fragmented_sources),
        )

        full_docs = []
        for source in fragmented_sources:
            if os.path.exists(source) and _is_safe_vault_path(source):
                full_content = read_full_document(source)
                if full_content:
                    source_scores = [
                        d.metadata.get("score", 0)
                        for d in docs
                        if d.metadata.get("source") == source
                    ]
                    max_score = max(source_scores) if source_scores else 0.5

                    all_links = extract_links_from_content(full_content)
                    full_doc = Document(
                        page_content=full_content,
                        metadata={
                            "source": source,
                            "links": ",".join(all_links),
                            "full_document": True,
                            "score": max_score,
                        },
                    )
                    full_docs.append(full_doc)

        if full_docs:
            docs = [d for d in docs if d.metadata.get("source") not in fragmented_sources]
            docs.extend(full_docs)
            docs = sorted(docs, key=lambda d: d.metadata.get("score", 0), reverse=True)

    # GraphRAG: Extract and follow links
    linked_sources = set()

    for doc in docs:
        links_str = doc.metadata.get("links", "")

        if not links_str:
            content_links = extract_links_from_content(doc.page_content)
            if content_links:
                links_str = ",".join(content_links)
                doc.metadata["links"] = links_str

        if links_str:
            links = [link.strip() for link in links_str.split(",") if link.strip()]
            if links:
                linked_sources.update(links)

    # Fetch linked documents using metadata-only query first
    if linked_sources:
        logger.info("[GRAPHRAG] Attempting to fetch %d linked notes...", len(linked_sources))

        try:
            db_metadata = db.get(include=["metadatas"])
            all_metadatas = db_metadata["metadatas"]
            all_ids = db_metadata["ids"]

            matching_ids = []
            for idx, metadata in enumerate(all_metadatas):
                source_path = metadata.get("source", "")
                for link_name in linked_sources:
                    if link_name.lower() in source_path.lower():
                        matching_ids.append(all_ids[idx])
                        break

            linked_docs = []
            if matching_ids:
                matched = db.get(ids=matching_ids)
                for i in range(len(matched["ids"])):
                    linked_docs.append(
                        Document(
                            page_content=matched["documents"][i],
                            metadata=matched["metadatas"][i],
                        )
                    )

            existing_sources = {d.metadata.get("source") for d in docs}
            new_linked_docs = [
                d for d in linked_docs if d.metadata.get("source") not in existing_sources
            ]

            if new_linked_docs:
                docs_to_add = new_linked_docs[:5]
                min_retrieved_score = min((d.metadata.get("score", 0.5) for d in docs), default=0.5)
                linked_base_score = min_retrieved_score * 0.9

                for i, linked_doc in enumerate(docs_to_add):
                    linked_doc.metadata["score"] = linked_base_score * (1 - i * 0.05)
                    linked_doc.metadata["retrieval_type"] = "graphrag_link"

                docs.extend(docs_to_add)
                logger.info("[GRAPHRAG] Added %d linked documents to context", len(docs_to_add))
        except Exception as e:
            logger.error("[GRAPHRAG] Error fetching linked docs: %s", e)

    # Filter out documents with low relevance scores
    MIN_SCORE_THRESHOLD = 0.3
    docs_before_filter = len(docs)
    docs = [d for d in docs if d.metadata.get("score", 0) >= MIN_SCORE_THRESHOLD]
    docs_filtered = docs_before_filter - len(docs)

    if docs_filtered > 0:
        logger.info(
            "[FILTER] Removed %d low-score docs (score < %s)", docs_filtered, MIN_SCORE_THRESHOLD
        )

    logger.info("[RETRIEVE NODE] Final context: %d documents", len(docs))

    if tracer:
        tracer.exit_node(
            "retrieve",
            {"final_docs": len(docs), "retrieval_time_seconds": round(retrieval_time, 3)},
        )

    return {"context": docs}


def generate_node(state: AgentState, llm_chain, tracer: Optional[GraphTracer] = None):
    """Node to generate the answer using retrieved context"""
    settings = get_settings()
    question = state["question"]
    context = state["context"]
    messages = state["messages"]

    if tracer:
        tracer.enter_node("generate", {"question": question[:50], "context_count": len(context)})

    logger.info("[GENERATE NODE] Generating answer with %d docs", len(context))

    context_parts = []
    for i, doc in enumerate(context):
        source = doc.metadata.get("source", "Unknown")
        source_name = os.path.basename(source) if source else "Unknown"
        context_parts.append("[Note: %s]\n%s" % (source_name, doc.page_content))

    context_str = "\n\n---\n\n".join(context_parts)
    logger.info("[GENERATE NODE] Context length: %d characters", len(context_str))

    logger.info("[GENERATE NODE] Invoking LLM (%s)...", settings.llm_model)
    start_llm = time.time()
    response = llm_chain.invoke(
        {"context": context_str, "question": question, "chat_history": messages[:-1]}
    )
    llm_time = time.time() - start_llm

    logger.info("[GENERATE NODE] Answer generated (%d chars) in %.2fs", len(response), llm_time)

    if tracer:
        tracer.exit_node(
            "generate",
            {"answer_length": len(response), "llm_time_seconds": round(llm_time, 3)},
        )

    return {"answer": response, "messages": [AIMessage(content=response)]}


def create_qa_graph(db):
    """Build the LangGraph agent using the model configured in settings"""
    settings = get_settings()

    llm, resolved_model = create_chat_model(settings)
    logger.info(
        "Using %s model: %s",
        settings.llm_provider,
        resolved_model,
    )

    retriever = create_retriever_with_reranker(db)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ]
    )

    llm_chain = prompt | llm | StrOutputParser()

    tracer = GraphTracer()

    workflow = StateGraph(AgentState)

    workflow.add_node("retrieve", lambda state: retrieve_node(state, retriever, db, tracer=tracer))
    workflow.add_node("generate", lambda state: generate_node(state, llm_chain, tracer=tracer))

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    app = workflow.compile()
    return app


def ask_question_graph(
    app, question: str, chat_history: Optional[List[Tuple[str, str]]] = None
) -> Tuple[str, List[Document]]:
    """Adapter to call the graph from the API"""
    if chat_history is None:
        chat_history = []

    tracer = GraphTracer()
    tracer.start(question, len(chat_history))

    logger.info("[GRAPH START] Question: '%s'", question)

    history_messages: List[BaseMessage] = []
    for q, a in chat_history:
        history_messages.append(HumanMessage(content=q))
        history_messages.append(AIMessage(content=a))

    history_messages.append(HumanMessage(content=question))

    inputs = {"question": question, "messages": history_messages, "context": []}

    try:
        start_invoke = time.time()
        result = app.invoke(inputs)
        invoke_time = time.time() - start_invoke

        logger.info("[GRAPH END] Answer length: %d chars", len(result["answer"]))

        tracer.end(
            {
                "answer_length": len(result["answer"]),
                "context_docs": len(result["context"]),
                "total_invoke_time": round(invoke_time, 3),
            }
        )

        return result["answer"], result["context"]
    except Exception as e:
        logger.error("[GRAPH ERROR] Exception during graph execution: %s", e)
        tracer.end({"error": str(e)})
        raise


async def ask_question_graph_streaming(
    app,
    question: str,
    chat_history: Optional[List[Tuple[str, str]]] = None,
    retriever=None,
    db=None,
):
    """Streaming version that yields events including token-by-token LLM output.

    This function bypasses the normal graph execution for generate node,
    running retrieve through the graph but doing LLM streaming directly.

    Yields dict events with structure:
    - {"type": "status", "message": "..."}
    - {"type": "retrieve_complete", "docs_count": 5, "sources": [...]}
    - {"type": "token", "content": "..."}
    - {"type": "answer", "answer": "...", "sources": [...]}
    """
    if chat_history is None:
        chat_history = []

    tracer = GraphTracer()
    logger.info("[STREAM START] Question: '%s'", question)
    settings = get_settings()

    try:
        start_invoke = time.time()

        yield {"type": "status", "message": "Searching your notes..."}
        await asyncio.sleep(0.01)

        logger.info("[STREAM] Running retrieval for: '%s'", question)

        history_messages: List[BaseMessage] = []
        for q, a in chat_history:
            history_messages.append(HumanMessage(content=q))
            history_messages.append(AIMessage(content=a))
        history_messages.append(HumanMessage(content=question))

        state: AgentState = {
            "messages": history_messages,
            "question": question,
            "context": [],
            "answer": "",
        }

        # Run retrieval in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        retrieve_result = await loop.run_in_executor(
            None, lambda: retrieve_node(state, retriever, db, tracer=tracer)
        )
        final_context = retrieve_result.get("context", [])

        logger.info("[STREAM] Retrieved %d documents", len(final_context))

        sources = []
        for doc in final_context:
            sources.append(
                {
                    "source": doc.metadata.get("source", "Unknown"),
                    "score": doc.metadata.get("score", 0),
                }
            )
        yield {
            "type": "retrieve_complete",
            "docs_count": len(final_context),
            "sources": sources[:6],
        }
        await asyncio.sleep(0.01)

        yield {"type": "status", "message": "Generating answer..."}
        await asyncio.sleep(0.01)

        context_parts = []
        for doc in final_context:
            source = doc.metadata.get("source", "Unknown")
            source_name = os.path.basename(source) if source else "Unknown"
            context_parts.append("[Note: %s]\n%s" % (source_name, doc.page_content))
        context_str = "\n\n---\n\n".join(context_parts)

        full_prompt = (
            SYSTEM_PROMPT.format(context=context_str) + "\n\nQuestion: %s\n\nAnswer:" % question
        )

        full_answer = ""
        first_token_time = None
        llm_start_time = time.time()
        token_count = 0

        llm, resolved_model = create_chat_model(settings)
        logger.info(
            "[STREAM] Starting LLM streaming (%s:%s)...",
            settings.llm_provider,
            resolved_model,
        )
        logger.info(
            "[STREAM] Prompt length: %d chars, Context: %d chars",
            len(full_prompt),
            len(context_str),
        )

        async for chunk in stream_chat_model_tokens(
            single_human_message(full_prompt), settings, model=llm
        ):
            token_count += 1

            if first_token_time is None:
                first_token_time = time.time()
                ttft = first_token_time - llm_start_time
                logger.info("[TTFT] Time to First Token: %.3fs", ttft)
                yield {"type": "ttft", "seconds": round(ttft, 3)}

            full_answer += chunk
            yield {"type": "token", "content": chunk}
            logger.debug("[TOKEN #%d] '%s...' yielded", token_count, chunk[:20])

        llm_end_time = time.time()
        llm_total_time = llm_end_time - llm_start_time
        tokens_per_second = token_count / llm_total_time if llm_total_time > 0 else 0

        logger.info(
            "[STREAM] LLM complete: %d chars, %d tokens in %.2fs (%.1f tok/s)",
            len(full_answer),
            token_count,
            llm_total_time,
            tokens_per_second,
        )

        invoke_time = time.time() - start_invoke

        sources = []
        for doc in final_context:
            sources.append(
                {
                    "source": doc.metadata.get("source", "Unknown"),
                    "score": doc.metadata.get("score", 0),
                    "retrieval_type": doc.metadata.get("retrieval_type", "retrieved"),
                }
            )
        sources.sort(key=lambda x: x["score"], reverse=True)

        yield {
            "type": "answer",
            "question": question,
            "answer": full_answer,
            "sources": sources,
            "process_time": round(invoke_time, 3),
        }

        logger.info("[STREAM END] Total time: %.2fs", invoke_time)

    except Exception as e:
        logger.error("[STREAM ERROR] Exception: %s", e)
        import traceback

        logger.error(traceback.format_exc())
        yield {"type": "error", "message": str(e)}
