import logging
from typing import List, Tuple, Dict, Any, Annotated, Sequence
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from langchain_ollama import OllamaLLM
from config.settings import settings
from services.qa_service import create_retriever_with_reranker, verify_ollama_available
from utils.logger import setup_logger

logger = setup_logger(__name__)

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
    logger.info(f"🔍 [RETRIEVE NODE] Starting retrieval for: '{question}'")
    
    # Retrieve docs
    docs = retriever.invoke(question)
    logger.info(f"📄 [RETRIEVE NODE] Retrieved {len(docs)} initial documents")
    
    # Log retrieved docs
    for i, doc in enumerate(docs):
        source = doc.metadata.get('source', 'Unknown')
        logger.info(f"   Doc {i+1}: {source}")
    
    # GraphRAG: Extract and follow links
    linked_sources = set()
    for doc in docs:
        links_str = doc.metadata.get('links', '')
        if links_str:
            links = [link.strip() for link in links_str.split(',') if link.strip()]
            if links:
                logger.info(f"🔗 [GRAPHRAG] Found {len(links)} links in {doc.metadata.get('source', 'Unknown')}: {links[:3]}...")
                linked_sources.update(links)
    
    # Fetch linked documents if any
    if linked_sources:
        logger.info(f"🕸️ [GRAPHRAG] Fetching {len(linked_sources)} linked notes...")
        
        # Get all documents from DB to search for linked ones
        try:
            db_data = db.get()
            all_metadatas = db_data['metadatas']
            all_docs_content = db_data['documents']
            
            linked_docs = []
            for idx, metadata in enumerate(all_metadatas):
                source_path = metadata.get('source', '')
                # Check if this doc matches any of our linked note names
                for link_name in linked_sources:
                    if link_name in source_path:
                        linked_doc = Document(
                            page_content=all_docs_content[idx],
                            metadata=metadata
                        )
                        linked_docs.append(linked_doc)
                        logger.info(f"   ✅ Found linked note: {source_path}")
                        break
            
            # Add linked docs to context (but don't duplicate)
            existing_sources = {d.metadata.get('source') for d in docs}
            new_linked_docs = [d for d in linked_docs if d.metadata.get('source') not in existing_sources]
            
            if new_linked_docs:
                docs.extend(new_linked_docs[:3])  # Limit to 3 additional linked docs
                logger.info(f"📚 [GRAPHRAG] Added {len(new_linked_docs[:3])} linked documents to context")
            else:
                logger.info(f"⚠️ [GRAPHRAG] No new linked documents found")
        except Exception as e:
            logger.error(f"❌ [GRAPHRAG] Error fetching linked docs: {e}")
    else:
        logger.info(f"⚪ [GRAPHRAG] No links found in retrieved documents")
    
    logger.info(f"✅ [RETRIEVE NODE] Final context: {len(docs)} documents")
    return {"context": docs}

def generate_node(state: AgentState, llm_chain):
    """Node to generate the answer using retrieved context"""
    question = state["question"]
    context = state["context"]
    messages = state["messages"]
    
    logger.info(f"🤖 [GENERATE NODE] Generating answer with {len(context)} docs")
    
    # Format context
    context_str = "\n\n".join([doc.page_content for doc in context])
    logger.info(f"📝 [GENERATE NODE] Context length: {len(context_str)} characters")
    
    # Generate
    logger.info(f"💭 [GENERATE NODE] Invoking LLM ({settings.llm_model})...")
    response = llm_chain.invoke({
        "context": context_str,
        "question": question,
        "chat_history": messages[:-1] # Exclude current question if it's in messages
    })
    
    logger.info(f"✅ [GENERATE NODE] Answer generated ({len(response)} chars)")
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
    logger.info(f"🚀 [GRAPH START] Question: '{question}'")
    logger.info(f"📚 [GRAPH START] Chat history: {len(chat_history)} messages")
    
    # Convert chat_history to Messages
    history_messages = []
    for q, a in chat_history:
        history_messages.append(HumanMessage(content=q))
        history_messages.append(AIMessage(content=a))
    
    # Add current question
    history_messages.append(HumanMessage(content=question))
    
    # Invoke graph
    inputs = {
        "question": question,
        "messages": history_messages,
        "context": []
    }
    
    logger.info(f"⚙️ [GRAPH EXEC] Invoking StateGraph...")
    result = app.invoke(inputs)
    
    logger.info(f"🎯 [GRAPH END] Answer length: {len(result['answer'])} chars, Context docs: {len(result['context'])}")
    return result["answer"], result["context"]
