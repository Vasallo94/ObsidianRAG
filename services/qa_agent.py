import json
import os
import re
import time
from datetime import datetime
from typing import Annotated, List, Sequence, Tuple
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import OllamaLLM
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from config.settings import settings
from services.qa_service import create_retriever_with_reranker, verify_ollama_available
from utils.logger import setup_logger

logger = setup_logger(__name__)


def extract_links_from_content(content: str) -> List[str]:
    """Extract Obsidian [[links]] from content as fallback when metadata is empty"""
    links = re.findall(r'\[\[(.*?)\]\]', content)
    # Clean links (remove alias like [[Note|Alias]] -> Note)
    cleaned = [link.split('|')[0].strip() for link in links]
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
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading {filepath}: {e}")
            return ""
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return ""

# ========== GRAPH EXECUTION TRACER ==========
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
        self._log_event("GRAPH_START", {
            "question": question,
            "history_messages": history_len,
            "timestamp": datetime.now().isoformat()
        })
        
    def enter_node(self, node_name: str, state_summary: dict):
        """Log entering a node"""
        self.node_times[node_name] = {"start": time.time()}
        self._log_event(f"NODE_ENTER:{node_name}", {
            "state_keys": list(state_summary.keys()),
            "context_docs": state_summary.get("context_count", 0),
            "question": state_summary.get("question", "")[:50]
        })
        
    def exit_node(self, node_name: str, result_summary: dict):
        """Log exiting a node"""
        if node_name in self.node_times:
            elapsed = time.time() - self.node_times[node_name]["start"]
            self.node_times[node_name]["elapsed"] = elapsed
        else:
            elapsed = 0
        self._log_event(f"NODE_EXIT:{node_name}", {
            "elapsed_seconds": round(elapsed, 3),
            **result_summary
        })
        
    def end(self, result_summary: dict):
        """End tracing"""
        total_time = time.time() - self.start_time if self.start_time else 0
        self._log_event("GRAPH_END", {
            "total_elapsed_seconds": round(total_time, 3),
            "node_timings": {k: round(v.get("elapsed", 0), 3) for k, v in self.node_times.items()},
            **result_summary
        })
        self._print_summary()
        
    def _log_event(self, event_type: str, data: dict):
        """Log an event"""
        event = {"type": event_type, "data": data, "time": time.time()}
        self.events.append(event)
        # Log to console with color coding
        if "START" in event_type:
            logger.info(f"🚀 [{event_type}] {json.dumps(data, ensure_ascii=False)}")
        elif "ENTER" in event_type:
            logger.info(f"➡️  [{event_type}] {json.dumps(data, ensure_ascii=False)}")
        elif "EXIT" in event_type:
            logger.info(f"✅ [{event_type}] {json.dumps(data, ensure_ascii=False)}")
        elif "END" in event_type:
            logger.info(f"🏁 [{event_type}] {json.dumps(data, ensure_ascii=False)}")
        else:
            logger.debug(f"📝 [{event_type}] {json.dumps(data, ensure_ascii=False)}")
            
    def _print_summary(self):
        """Print execution summary"""
        logger.info("=" * 60)
        logger.info("📊 GRAPH EXECUTION SUMMARY")
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
    tracer.enter_node("retrieve", {
        "question": question,
        "context_count": len(state.get("context", []))
    })
    
    logger.info(f"🔍 [RETRIEVE NODE] Starting retrieval for: '{question}'")
    
    # Retrieve docs
    start_retrieval = time.time()
    docs = retriever.invoke(question)
    retrieval_time = time.time() - start_retrieval
    
    logger.info(f"📄 [RETRIEVE NODE] Retrieved {len(docs)} initial documents in {retrieval_time:.2f}s")
    
    # === CAPTURE RERANKER SCORES ===
    # The CrossEncoderReranker adds 'relevance_score' to metadata
    # We normalize it to 'score' and ensure docs are ordered by it
    for i, doc in enumerate(docs):
        # Check for relevance_score from reranker
        relevance_score = doc.metadata.get('relevance_score', None)
        if relevance_score is not None:
            doc.metadata['score'] = float(relevance_score)
        else:
            # Assign position-based score if no reranker score (higher rank = higher score)
            doc.metadata['score'] = 1.0 - (i * 0.1)  # First doc = 1.0, second = 0.9, etc.
    
    # Sort docs by score (highest first) - reranker should have done this but ensure it
    docs = sorted(docs, key=lambda d: d.metadata.get('score', 0), reverse=True)
    
    # Log retrieved docs with details and scores
    for i, doc in enumerate(docs):
        source = doc.metadata.get('source', 'Unknown')
        links = doc.metadata.get('links', '')
        score = doc.metadata.get('score', 0)
        content_preview = doc.page_content[:100].replace('\n', ' ')
        logger.info(f"   📑 Doc {i+1} (score: {score:.4f}):")
        logger.info(f"      Source: {source}")
        logger.info(f"      Links metadata: '{links}'")
        logger.info(f"      Content preview: {content_preview}...")
    
    # === FULL DOCUMENT EXPANSION ===
    # If we have multiple chunks from the same file, read the complete document
    source_counts = {}
    for doc in docs:
        source = doc.metadata.get('source', '')
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1
    
    # Find sources that appear multiple times (indicates fragmented context)
    fragmented_sources = {s for s, count in source_counts.items() if count > 1}
    
    if fragmented_sources:
        logger.info(f"📖 [FULL DOC] Detected {len(fragmented_sources)} fragmented documents, reading full content...")
        
        full_docs = []
        for source in fragmented_sources:
            if os.path.exists(source):
                full_content = read_full_document(source)
                if full_content:
                    # Get the max score from chunks of this source for the full doc
                    source_scores = [d.metadata.get('score', 0) for d in docs if d.metadata.get('source') == source]
                    max_score = max(source_scores) if source_scores else 0.5
                    
                    # Extract links from full content
                    all_links = extract_links_from_content(full_content)
                    full_doc = Document(
                        page_content=full_content,
                        metadata={
                            'source': source,
                            'links': ','.join(all_links),
                            'full_document': True,
                            'score': max_score  # Inherit best score from chunks
                        }
                    )
                    full_docs.append(full_doc)
                    logger.info(f"   📄 Read full doc: {os.path.basename(source)} ({len(full_content)} chars, {len(all_links)} links, score: {max_score:.4f})")
        
        # Replace fragmented chunks with full documents
        if full_docs:
            # Remove old chunks from fragmented sources
            docs = [d for d in docs if d.metadata.get('source') not in fragmented_sources]
            docs.extend(full_docs)
            # Re-sort by score after adding full docs
            docs = sorted(docs, key=lambda d: d.metadata.get('score', 0), reverse=True)
            logger.info(f"   ✅ Replaced with {len(full_docs)} full documents")
    
    # === GRAPHRAG: Extract and follow links ===
    linked_sources = set()
    
    for doc in docs:
        # First try metadata
        links_str = doc.metadata.get('links', '')
        
        # If metadata is empty, extract from content as fallback
        if not links_str:
            content_links = extract_links_from_content(doc.page_content)
            if content_links:
                links_str = ','.join(content_links)
                doc.metadata['links'] = links_str  # Update metadata for future use
                logger.info(f"🔍 [GRAPHRAG] Extracted {len(content_links)} links from content of {os.path.basename(doc.metadata.get('source', 'Unknown'))}")
        
        if links_str:
            links = [link.strip() for link in links_str.split(',') if link.strip()]
            if links:
                logger.info(f"🔗 [GRAPHRAG] Found {len(links)} links in {os.path.basename(doc.metadata.get('source', 'Unknown'))}")
                for link in links[:5]:  # Log first 5
                    logger.info(f"      -> {link}")
                linked_sources.update(links)
    
    # Fetch linked documents if any
    if linked_sources:
        logger.info(f"🕸️ [GRAPHRAG] Attempting to fetch {len(linked_sources)} linked notes...")
        
        # Get all documents from DB to search for linked ones
        try:
            start_link_fetch = time.time()
            db_data = db.get()
            all_metadatas = db_data['metadatas']
            all_docs_content = db_data['documents']
            
            logger.info(f"   📚 DB contains {len(all_metadatas)} total chunks")
            
            linked_docs = []
            matched_links = []
            for idx, metadata in enumerate(all_metadatas):
                source_path = metadata.get('source', '')
                # Check if this doc matches any of our linked note names
                for link_name in linked_sources:
                    if link_name.lower() in source_path.lower():
                        linked_doc = Document(
                            page_content=all_docs_content[idx],
                            metadata=metadata
                        )
                        linked_docs.append(linked_doc)
                        matched_links.append(link_name)
                        logger.info(f"   ✅ Found linked note: {source_path} (matched: {link_name})")
                        break
            
            link_fetch_time = time.time() - start_link_fetch
            logger.info(f"   ⏱️ Link fetch completed in {link_fetch_time:.2f}s")
            
            # Add linked docs to context (but don't duplicate)
            existing_sources = {d.metadata.get('source') for d in docs}
            new_linked_docs = [d for d in linked_docs if d.metadata.get('source') not in existing_sources]
            
            if new_linked_docs:
                docs_to_add = new_linked_docs[:5]  # Increased from 3 to 5
                
                # Assign scores to linked docs - slightly lower than retrieved docs
                # to indicate they're relevant via links, not direct retrieval
                min_retrieved_score = min((d.metadata.get('score', 0.5) for d in docs), default=0.5)
                linked_base_score = min_retrieved_score * 0.9  # 90% of lowest retrieved score
                
                for i, linked_doc in enumerate(docs_to_add):
                    # Decreasing scores for each linked doc
                    linked_doc.metadata['score'] = linked_base_score * (1 - i * 0.05)
                    linked_doc.metadata['retrieval_type'] = 'graphrag_link'
                
                docs.extend(docs_to_add)
                logger.info(f"📚 [GRAPHRAG] Added {len(docs_to_add)} linked documents to context")
                for d in docs_to_add:
                    logger.info(f"      + {d.metadata.get('source', 'Unknown')} (score: {d.metadata.get('score', 0):.4f})")
            else:
                logger.warning(f"⚠️ [GRAPHRAG] No new linked documents found (searched {len(linked_sources)} links)")
                logger.info(f"   Links searched: {list(linked_sources)[:5]}...")
        except Exception as e:
            logger.error(f"❌ [GRAPHRAG] Error fetching linked docs: {e}")
            import traceback
            logger.error(traceback.format_exc())
    else:
        logger.info(f"⚪ [GRAPHRAG] No links found in retrieved documents metadata")
    
    logger.info(f"✅ [RETRIEVE NODE] Final context: {len(docs)} documents")
    
    # Trace node exit
    tracer.exit_node("retrieve", {
        "initial_docs": len(docs) - len(linked_sources) if linked_sources else len(docs),
        "linked_docs_added": len(linked_sources) if linked_sources else 0,
        "final_docs": len(docs),
        "retrieval_time_seconds": round(retrieval_time, 3)
    })
    
    return {"context": docs}

def generate_node(state: AgentState, llm_chain):
    """Node to generate the answer using retrieved context"""
    question = state["question"]
    context = state["context"]
    messages = state["messages"]
    
    # Trace node entry
    tracer.enter_node("generate", {
        "question": question[:50],
        "context_count": len(context)
    })
    
    logger.info(f"🤖 [GENERATE NODE] Generating answer with {len(context)} docs")
    
    # Format context
    context_str = "\n\n".join([doc.page_content for doc in context])
    logger.info(f"📝 [GENERATE NODE] Context length: {len(context_str)} characters")
    
    # Log context sources for debugging
    logger.info(f"📋 [GENERATE NODE] Context sources:")
    for i, doc in enumerate(context):
        logger.info(f"   {i+1}. {doc.metadata.get('source', 'Unknown')[:80]}...")
    
    # Generate
    logger.info(f"💭 [GENERATE NODE] Invoking LLM ({settings.llm_model})...")
    start_llm = time.time()
    response = llm_chain.invoke({
        "context": context_str,
        "question": question,
        "chat_history": messages[:-1] # Exclude current question if it's in messages
    })
    llm_time = time.time() - start_llm
    
    logger.info(f"✅ [GENERATE NODE] Answer generated ({len(response)} chars) in {llm_time:.2f}s")
    logger.info(f"📖 [GENERATE NODE] Answer preview: {response[:200]}...")
    
    # Trace node exit
    tracer.exit_node("generate", {
        "answer_length": len(response),
        "llm_time_seconds": round(llm_time, 3),
        "context_chars": len(context_str)
    })
    
    return {"answer": response, "messages": [AIMessage(content=response)]}

# --- Graph Construction ---

def create_qa_graph(db):
    """Build the LangGraph agent"""
    verify_ollama_available()
    
    # 1. Components
    llm = OllamaLLM(
        model=settings.llm_model,
        base_url=settings.ollama_base_url
    )
    
    retriever = create_retriever_with_reranker(db)
    
    # Prompt
    system_prompt = """Eres un asistente personal que responde preguntas basándose EXCLUSIVAMENTE en mis notas de Obsidian proporcionadas en el contexto.

Reglas CRÍTICAS:
1. **Cita Textual**: Si pregunto por un texto específico, cítalo EXACTAMENTE como aparece. NO resumas, NO censures y NO modifiques el lenguaje.
2. **Honestidad**: Si la respuesta no está en el contexto, di "No lo encuentro en las notas".
3. **Formato**: Usa Markdown.
4. **Directo**: Ve al grano.

Contexto:
{context}
"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}")
    ])
    
    llm_chain = prompt | llm | StrOutputParser()
    
    # 2. Graph
    workflow = StateGraph(AgentState)
    
    # Add nodes (pass db to retriever for GraphRAG)
    workflow.add_node("retrieve", lambda state: retrieve_node(state, retriever, db))
    workflow.add_node("generate", lambda state: generate_node(state, llm_chain))
    
    # Add edges
    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)
    
    # Compile
    app = workflow.compile()
    return app

# --- Interface for Cerebro ---

def ask_question_graph(app, question: str, chat_history: List[Tuple[str, str]] = []):
    """Adapter to call the graph from the API"""
    # Start tracing
    tracer.start(question, len(chat_history))
    
    logger.info(f"🚀 [GRAPH START] Question: '{question}'")
    logger.info(f"📚 [GRAPH START] Chat history: {len(chat_history)} messages")
    
    # Convert chat_history to Messages
    history_messages = []
    for q, a in chat_history:
        history_messages.append(HumanMessage(content=q))
        history_messages.append(AIMessage(content=a))
        logger.debug(f"   History Q: {q[:50]}... A: {a[:50]}...")
    
    # Add current question
    history_messages.append(HumanMessage(content=question))
    
    # Invoke graph
    inputs = {
        "question": question,
        "messages": history_messages,
        "context": []
    }
    
    logger.info(f"⚙️ [GRAPH EXEC] Invoking StateGraph with {len(history_messages)} messages...")
    
    try:
        start_invoke = time.time()
        result = app.invoke(inputs)
        invoke_time = time.time() - start_invoke
        
        logger.info(f"🎯 [GRAPH END] Answer length: {len(result['answer'])} chars, Context docs: {len(result['context'])}")
        logger.info(f"⏱️ [GRAPH END] Total invoke time: {invoke_time:.2f}s")
        
        # End tracing
        tracer.end({
            "answer_length": len(result["answer"]),
            "context_docs": len(result["context"]),
            "total_invoke_time": round(invoke_time, 3)
        })
        
        return result["answer"], result["context"]
    except Exception as e:
        logger.error(f"❌ [GRAPH ERROR] Exception during graph execution: {e}")
        import traceback
        logger.error(traceback.format_exc())
        tracer.end({"error": str(e)})
        raise
