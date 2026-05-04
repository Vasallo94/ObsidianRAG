"""LangGraph-based QA Agent for ObsidianRAG"""

import json
import os
import re
import time
from datetime import datetime
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
from langchain_core.language_models.chat_models import BaseChatModel
from obsidianrag.core.qa_service import create_retriever_with_reranker
from obsidianrag.utils.logger import setup_logger

logger = setup_logger(__name__)


def extract_links_from_content(content: str) -> List[str]:
    """Extract Obsidian [[links]] from content as fallback when metadata is empty"""
    links = re.findall(r"\[\[(.*?)\]\]", content)
    # Clean links (remove alias like [[Note|Alias]] -> Note)
    cleaned = [link.split("|")[0].strip() for link in links]
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for link in cleaned:
        if link and link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def read_full_document(filepath: str) -> str:
    """Read the complete content of a document file"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, "r", encoding="latin-1") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading {filepath}: {e}")
            return ""
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return ""


class GraphTracer:
    """Tracer for detailed graph execution logging"""

    def __init__(self):
        self.start_time = None
        self.node_times = {}
        self.events = []

    def start(self, question: str, history_len: int):
        """Start tracing a new graph execution"""
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
        """Log entering a node"""
        self.node_times[node_name] = {"start": time.time()}
        self._log_event(
            f"NODE_ENTER:{node_name}",
            {
                "state_keys": list(state_summary.keys()),
                "context_docs": state_summary.get("context_count", 0),
                "question": state_summary.get("question", "")[:50],
            },
        )

    def exit_node(self, node_name: str, result_summary: dict):
        """Log exiting a node"""
        if node_name in self.node_times:
            elapsed = time.time() - self.node_times[node_name]["start"]
            self.node_times[node_name]["elapsed"] = elapsed
        else:
            elapsed = 0
        self._log_event(
            f"NODE_EXIT:{node_name}", {"elapsed_seconds": round(elapsed, 3), **result_summary}
        )

    def end(self, result_summary: dict):
        """End tracing"""
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
        """Log an event"""
        event = {"type": event_type, "data": data, "time": time.time()}
        self.events.append(event)
        # Log to console with color coding
        if "START" in event_type:
            logger.info(f"[{event_type}] {json.dumps(data, ensure_ascii=False)}")
        elif "ENTER" in event_type:
            logger.info(f"[{event_type}] {json.dumps(data, ensure_ascii=False)}")
        elif "EXIT" in event_type:
            logger.info(f"[{event_type}] {json.dumps(data, ensure_ascii=False)}")
        elif "END" in event_type:
            logger.info(f"[{event_type}] {json.dumps(data, ensure_ascii=False)}")
        else:
            logger.debug(f"[{event_type}] {json.dumps(data, ensure_ascii=False)}")

    def _print_summary(self):
        """Print execution summary"""
        logger.info("=" * 60)
        logger.info("GRAPH EXECUTION SUMMARY")
        logger.info("=" * 60)
        for event in self.events:
            logger.info(f"  {event['type']}: {event['data']}")
        logger.info("=" * 60)


# Global tracer instance
tracer = GraphTracer()


# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: List[Document]
    question: str
    answer: str


# --- Nodes ---


def retrieve_node(state: AgentState, retriever, db):
    """Node to retrieve documents based on the last user message"""
    question = state["question"]

    # Trace node entry
    tracer.enter_node(
        "retrieve", {"question": question, "context_count": len(state.get("context", []))}
    )

    logger.info(f"[RETRIEVE NODE] Starting retrieval for: '{question}'")

    # Retrieve docs
    start_retrieval = time.time()
    docs = retriever.invoke(question)
    retrieval_time = time.time() - start_retrieval

    logger.info(
        f"[RETRIEVE NODE] Retrieved {len(docs)} initial documents in {retrieval_time:.2f}s"
    )

    # Capture reranker scores
    for i, doc in enumerate(docs):
        relevance_score = doc.metadata.get("relevance_score", None)
        if relevance_score is not None:
            doc.metadata["score"] = float(relevance_score)
        else:
            doc.metadata["score"] = 1.0 - (i * 0.1)

    # Sort docs by score
    docs = sorted(docs, key=lambda d: d.metadata.get("score", 0), reverse=True)

    # Log retrieved docs
    for i, doc in enumerate(docs):
        source = doc.metadata.get("source", "Unknown")
        score = doc.metadata.get("score", 0)
        logger.info(f"   Doc {i + 1} (score: {score:.4f}): {os.path.basename(source)}")

    # Full document expansion for fragmented sources
    source_counts: dict[str, int] = {}
    for doc in docs:
        source = doc.metadata.get("source", "")
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1

    fragmented_sources = {s for s, count in source_counts.items() if count > 1}

    if fragmented_sources:
        logger.info(
            f"[FULL DOC] Detected {len(fragmented_sources)} fragmented documents, reading full content..."
        )

        full_docs = []
        for source in fragmented_sources:
            if os.path.exists(source):
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

    # Fetch linked documents
    if linked_sources:
        logger.info(f"[GRAPHRAG] Attempting to fetch {len(linked_sources)} linked notes...")

        try:
            db_data = db.get()
            all_metadatas = db_data["metadatas"]
            all_docs_content = db_data["documents"]

            linked_docs = []
            for idx, metadata in enumerate(all_metadatas):
                source_path = metadata.get("source", "")
                for link_name in linked_sources:
                    if link_name.lower() in source_path.lower():
                        linked_doc = Document(page_content=all_docs_content[idx], metadata=metadata)
                        linked_docs.append(linked_doc)
                        break

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
                logger.info(f"[GRAPHRAG] Added {len(docs_to_add)} linked documents to context")
        except Exception as e:
            logger.error(f"[GRAPHRAG] Error fetching linked docs: {e}")

    # Filter out documents with low relevance scores
    MIN_SCORE_THRESHOLD = 0.3  # Minimum score to include in context
    docs_before_filter = len(docs)
    docs = [d for d in docs if d.metadata.get("score", 0) >= MIN_SCORE_THRESHOLD]
    docs_filtered = docs_before_filter - len(docs)

    if docs_filtered > 0:
        logger.info(
            f"[FILTER] Removed {docs_filtered} low-score docs (score < {MIN_SCORE_THRESHOLD})"
        )

    logger.info(f"[RETRIEVE NODE] Final context: {len(docs)} documents")

    tracer.exit_node(
        "retrieve", {"final_docs": len(docs), "retrieval_time_seconds": round(retrieval_time, 3)}
    )

    return {"context": docs}


def generate_node(state: AgentState, llm_chain):
    """Node to generate the answer using retrieved context"""
    settings = get_settings()
    question = state["question"]
    context = state["context"]
    messages = state["messages"]

    tracer.enter_node("generate", {"question": question[:50], "context_count": len(context)})

    logger.info(f"[GENERATE NODE] Generating answer with {len(context)} docs")

    # Format context
    context_parts = []
    for i, doc in enumerate(context):
        source = doc.metadata.get("source", "Unknown")
        source_name = os.path.basename(source) if source else "Unknown"
        context_parts.append(f"[Note: {source_name}]\n{doc.page_content}")

    context_str = "\n\n---\n\n".join(context_parts)
    logger.info(f"[GENERATE NODE] Context length: {len(context_str)} characters")

    # Generate
    logger.info(f"[GENERATE NODE] Invoking LLM ({settings.llm_model})...")
    start_llm = time.time()
    response = llm_chain.invoke(
        {"context": context_str, "question": question, "chat_history": messages[:-1]}
    )
    llm_time = time.time() - start_llm

    logger.info(f"[GENERATE NODE] Answer generated ({len(response)} chars) in {llm_time:.2f}s")

    tracer.exit_node(
        "generate", {"answer_length": len(response), "llm_time_seconds": round(llm_time, 3)}
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

    system_prompt = """You are a personal assistant that answers questions based on the user's Obsidian notes provided below in the CONTEXT section.

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
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ]
    )

    llm_chain = prompt | llm | StrOutputParser()

    workflow = StateGraph(AgentState)

    workflow.add_node("retrieve", lambda state: retrieve_node(state, retriever, db))
    workflow.add_node("generate", lambda state: generate_node(state, llm_chain))

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

    tracer.start(question, len(chat_history))

    logger.info(f"[GRAPH START] Question: '{question}'")

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

        logger.info(f"[GRAPH END] Answer length: {len(result['answer'])} chars")

        tracer.end(
            {
                "answer_length": len(result["answer"]),
                "context_docs": len(result["context"]),
                "total_invoke_time": round(invoke_time, 3),
            }
        )

        return result["answer"], result["context"]
    except Exception as e:
        logger.error(f"[GRAPH ERROR] Exception during graph execution: {e}")
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
    - {"type": "token", "content": "..."}  # Individual tokens
    - {"type": "answer", "answer": "...", "sources": [...]}
    """
    import asyncio

    if chat_history is None:
        chat_history = []

    logger.info(f"[STREAM START] Question: '{question}'")
    settings = get_settings()

    try:
        start_invoke = time.time()

        # Yield initial status
        yield {"type": "status", "message": "Searching your notes..."}
        await asyncio.sleep(0.01)

        # Step 1: Run retrieve node directly (not through graph to avoid generate)
        logger.info(f"[STREAM] Running retrieval for: '{question}'")

        # Build a minimal state for retrieve_node
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

        # Call retrieve_node directly
        retrieve_result = retrieve_node(state, retriever, db)
        final_context = retrieve_result.get("context", [])

        logger.info(f"[STREAM] Retrieved {len(final_context)} documents")

        # Yield retrieve complete event
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

        # Step 2: Stream LLM generation token by token
        yield {"type": "status", "message": "Generating answer..."}
        await asyncio.sleep(0.01)

        # Format context for LLM
        context_parts = []
        for doc in final_context:
            source = doc.metadata.get("source", "Unknown")
            source_name = os.path.basename(source) if source else "Unknown"
            context_parts.append(f"[Note: {source_name}]\n{doc.page_content}")
        context_str = "\n\n---\n\n".join(context_parts)

        # Build the prompt
        system_prompt = """You are a personal assistant that answers questions based on the user's Obsidian notes provided below in the CONTEXT section.

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

---
CONTEXT (User's Obsidian Notes):
{context}
---
"""

        full_prompt = (
            system_prompt.format(context=context_str) + f"\n\nQuestion: {question}\n\nAnswer:"
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
            f"[STREAM] Prompt length: {len(full_prompt)} chars, Context: {len(context_str)} chars"
        )

        async for chunk in stream_chat_model_tokens(single_human_message(full_prompt), settings, model=llm):
            token_count += 1

            if first_token_time is None:
                first_token_time = time.time()
                ttft = first_token_time - llm_start_time
                logger.info(f"[TTFT] Time to First Token: {ttft:.3f}s")
                yield {"type": "ttft", "seconds": round(ttft, 3)}

            full_answer += chunk
            yield {"type": "token", "content": chunk}
            logger.debug(f"[TOKEN #{token_count}] '{chunk[:20]}...' yielded")

        llm_end_time = time.time()
        llm_total_time = llm_end_time - llm_start_time
        tokens_per_second = token_count / llm_total_time if llm_total_time > 0 else 0

        logger.info(
            f"[STREAM] LLM complete: {len(full_answer)} chars, {token_count} tokens in {llm_total_time:.2f}s ({tokens_per_second:.1f} tok/s)"
        )

        invoke_time = time.time() - start_invoke

        # Format sources from captured context
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

        # Final answer event
        yield {
            "type": "answer",
            "question": question,
            "answer": full_answer,
            "sources": sources,
            "process_time": round(invoke_time, 3),
        }

        logger.info(f"[STREAM END] Total time: {invoke_time:.2f}s")

    except Exception as e:
        logger.error(f"[STREAM ERROR] Exception: {e}")
        import traceback

        logger.error(traceback.format_exc())
        yield {"type": "error", "message": str(e)}
