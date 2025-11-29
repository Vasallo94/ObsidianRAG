# RAG & LangGraph Patterns

> Instructions for implementing and modifying the RAG pipeline

## Architecture Overview

```
User Question
     │
     ▼
┌─────────────┐
│  Retrieve   │ ◄── Hybrid Search (BM25 + Vector)
│    Node     │ ◄── Reranker (CrossEncoder)
└─────────────┘ ◄── GraphRAG Link Expansion
     │
     ▼
┌─────────────┐
│  Generate   │ ◄── Ollama LLM
│    Node     │ ◄── Context + Prompt
└─────────────┘
     │
     ▼
   Answer + Sources
```

## LangGraph Agent State

```python
from typing import Annotated, Sequence, TypedDict
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """State that flows through the agent graph.
    
    Attributes:
        messages: Conversation history (append-only via add_messages)
        context: Retrieved documents for current question
        question: Current user question
        answer: Generated answer
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: list[Document]
    question: str
    answer: str
```

## Retrieve Node Implementation

```python
def retrieve_node(state: AgentState, db: DBService) -> dict:
    """Retrieve relevant documents using hybrid search.
    
    This node:
    1. Gets BM25 results (keyword matching)
    2. Gets vector similarity results (semantic matching)
    3. Combines with EnsembleRetriever
    4. Reranks with CrossEncoder
    5. Expands context via GraphRAG (wikilinks)
    
    Args:
        state: Current agent state with question
        db: Database service for retrieval
    
    Returns:
        Partial state update with context documents
    """
    question = state["question"]
    
    # 1. Hybrid search
    retriever = create_hybrid_retriever(db)
    docs = retriever.invoke(question)
    
    # 2. Rerank if enabled
    if settings.use_reranker:
        docs = rerank_documents(docs, question, top_n=settings.reranker_top_n)
    
    # 3. GraphRAG expansion
    expanded_docs = expand_linked_documents(docs, db)
    
    return {"context": expanded_docs}
```

### Hybrid Retriever Setup

```python
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

def create_hybrid_retriever(db: DBService) -> EnsembleRetriever:
    """Create hybrid BM25 + Vector retriever.
    
    BM25: Good for exact keyword matching, handles rare terms
    Vector: Good for semantic similarity, handles synonyms
    Combined: Best of both approaches
    """
    # Get all documents for BM25
    all_docs = db.get_all_documents()
    
    bm25_retriever = BM25Retriever.from_documents(
        all_docs,
        k=settings.bm25_k,
    )
    
    vector_retriever = db.vectorstore.as_retriever(
        search_kwargs={"k": settings.retrieval_k}
    )
    
    return EnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=[settings.bm25_weight, settings.vector_weight],  # 0.4, 0.6
    )
```

### Reranker Implementation

```python
from sentence_transformers import CrossEncoder

def rerank_documents(
    docs: list[Document],
    query: str,
    top_n: int = 6,
) -> list[Document]:
    """Rerank documents using CrossEncoder.
    
    CrossEncoder scores query-document pairs directly,
    providing more accurate relevance than bi-encoder similarity.
    
    Args:
        docs: Documents to rerank
        query: Original question
        top_n: Number of documents to keep
    
    Returns:
        Top-N documents after reranking
    """
    if not docs:
        return []
    
    model = CrossEncoder(settings.reranker_model)  # BAAI/bge-reranker-v2-m3
    
    # Create query-document pairs
    pairs = [(query, doc.page_content) for doc in docs]
    
    # Score all pairs
    scores = model.predict(pairs)
    
    # Sort by score and take top_n
    scored_docs = sorted(zip(scores, docs), reverse=True)
    return [doc for _, doc in scored_docs[:top_n]]
```

### GraphRAG Link Expansion

```python
import re

def expand_linked_documents(
    docs: list[Document],
    db: DBService,
    max_depth: int = 1,
) -> list[Document]:
    """Expand context by fetching documents linked via [[wikilinks]].
    
    This implements GraphRAG: treating notes as a graph where
    wikilinks are edges, and expanding retrieved context along
    those edges for richer context.
    
    Args:
        docs: Initially retrieved documents
        db: Database service
        max_depth: How many link hops to follow (1 = direct links only)
    
    Returns:
        Original docs plus linked documents
    """
    expanded = list(docs)
    seen_sources = {doc.metadata.get("source") for doc in docs}
    
    for doc in docs:
        # Extract [[wikilinks]] from content
        links = extract_wikilinks(doc.page_content)
        
        # Also check metadata if available
        if "links" in doc.metadata:
            links.update(doc.metadata["links"])
        
        for link in links:
            if link in seen_sources:
                continue
            
            # Fetch linked document
            linked_doc = db.get_document_by_name(link)
            if linked_doc:
                expanded.append(linked_doc)
                seen_sources.add(link)
    
    return expanded


def extract_wikilinks(content: str) -> set[str]:
    """Extract wikilink targets from markdown content.
    
    Handles:
    - [[simple-link]]
    - [[link|display text]]
    - [[folder/link]]
    """
    pattern = r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"
    matches = re.findall(pattern, content)
    return set(matches)
```

## Generate Node Implementation

```python
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

GENERATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful assistant that answers questions based on the user's Obsidian notes.

Use the following context from the notes to answer the question. 
If you cannot find the answer in the context, say so clearly.
Always cite which notes you used.

Context:
{context}
"""),
    ("human", "{question}"),
])


def generate_node(state: AgentState) -> dict:
    """Generate answer using LLM and retrieved context.
    
    Args:
        state: Agent state with question and context
    
    Returns:
        Partial state update with answer
    """
    question = state["question"]
    context = state["context"]
    
    # Format context
    context_text = format_context(context)
    
    # Create LLM
    llm = ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0.1,  # Low for factual answers
    )
    
    # Generate
    chain = GENERATE_PROMPT | llm
    response = chain.invoke({
        "question": question,
        "context": context_text,
    })
    
    return {"answer": response.content}


def format_context(docs: list[Document]) -> str:
    """Format documents into context string for LLM."""
    parts = []
    for doc in docs:
        source = doc.metadata.get("source", "Unknown")
        parts.append(f"--- From: {source} ---\n{doc.page_content}")
    return "\n\n".join(parts)
```

## Building the Graph

```python
from langgraph.graph import StateGraph, END

def create_qa_agent(db: DBService) -> CompiledGraph:
    """Create the LangGraph QA agent.
    
    Graph structure:
    START → retrieve → generate → END
    
    Args:
        db: Database service for retrieval
    
    Returns:
        Compiled graph ready to invoke
    """
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("retrieve", lambda s: retrieve_node(s, db))
    graph.add_node("generate", generate_node)
    
    # Define flow
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    
    return graph.compile()


# Usage
agent = create_qa_agent(db)
result = agent.invoke({
    "question": "What is machine learning?",
    "messages": [],
    "context": [],
    "answer": "",
})
print(result["answer"])
```

## Adding New Nodes

### Example: Adding a Summarize Node

```python
def summarize_node(state: AgentState) -> dict:
    """Summarize long context before generation."""
    context = state["context"]
    
    if total_tokens(context) < 2000:
        return {}  # No change needed
    
    # Summarize each document
    summarized = []
    for doc in context:
        summary = summarize_document(doc)
        summarized.append(Document(
            page_content=summary,
            metadata=doc.metadata,
        ))
    
    return {"context": summarized}

# Add to graph
graph.add_node("summarize", summarize_node)
graph.add_edge("retrieve", "summarize")
graph.add_edge("summarize", "generate")
```

### Example: Adding Routing

```python
def should_search_web(state: AgentState) -> str:
    """Decide if web search is needed."""
    context = state["context"]
    
    if not context or all_low_confidence(context):
        return "web_search"
    return "generate"

# Add conditional edge
graph.add_conditional_edges(
    "retrieve",
    should_search_web,
    {
        "web_search": "web_search_node",
        "generate": "generate",
    }
)
```

## Prompt Engineering

### System Prompt Guidelines
- Be specific about the role
- Explain what context is available
- Set expectations for "I don't know" cases
- Request citations

### Example Prompts

```python
# For factual Q&A
FACTUAL_PROMPT = """Answer based only on the provided notes.
If the information isn't in the notes, say "I couldn't find this in your notes."
Cite the source note for each fact."""

# For creative synthesis
SYNTHESIS_PROMPT = """Synthesize information from multiple notes to answer.
Connect ideas across different notes.
Highlight interesting relationships you notice."""

# For code-related questions
CODE_PROMPT = """When answering about code:
- Include relevant code snippets from notes
- Explain the code's purpose
- Note any dependencies mentioned"""
```

## Performance Optimization

### Caching
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_embedding(text: str) -> list[float]:
    """Cache embeddings for repeated queries."""
    return embeddings.embed_query(text)
```

### Batch Processing
```python
def index_documents_batch(docs: list[Document], batch_size: int = 100):
    """Index documents in batches to avoid memory issues."""
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        db.add_documents(batch)
```

### Streaming Responses
```python
async def stream_answer(question: str):
    """Stream answer tokens for better UX."""
    async for chunk in llm.astream(prompt):
        yield chunk.content
```

## Debugging RAG Pipeline

```python
# Add logging to understand retrieval
import logging
logging.getLogger("obsidianrag.core.qa_agent").setLevel(logging.DEBUG)

# Inspect retrieved documents
def debug_retrieve(state: AgentState, db: DBService) -> dict:
    result = retrieve_node(state, db)
    
    logger.debug(f"Retrieved {len(result['context'])} documents")
    for doc in result["context"]:
        logger.debug(f"  - {doc.metadata['source']}: {doc.page_content[:100]}...")
    
    return result
```
