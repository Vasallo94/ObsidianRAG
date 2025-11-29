import logging
from typing import List, Tuple

from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.retrievers import (
    ContextualCompressionRetriever,
    EnsembleRetriever,
)
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaLLM

from config.settings import settings

logger = logging.getLogger(__name__)


# Custom exceptions for better error handling
class RAGError(Exception):
    """Base exception for RAG-related errors"""
    pass


class ModelNotAvailableError(RAGError):
    """Ollama model is not available"""
    pass


class NoDocumentsFoundError(RAGError):
    """No documents found in database or retrieval"""
    pass


# System prompt
system_prompt = """You are a personal assistant that answers questions based on the user's Obsidian notes provided below in the CONTEXT section.

RULES:
1. **USE THE CONTEXT**: The notes below contain the information you need. READ THEM CAREFULLY before answering.
2. **Exact Quotes**: If asked for specific text, quote it EXACTLY as it appears.
3. **Honesty**: ONLY if the context is completely empty or truly irrelevant, say "I couldn't find this in the provided notes".
4. **Format**: Use Markdown. For literal quotes from notes, use quote blocks (>) or code blocks if needed.
5. **Direct**: Get to the point. No introductions like "Based on your notes...". Just answer.
6. **Language**: ALWAYS respond in the dominant language of the CONTEXT notes. If notes are in Spanish, respond in Spanish.

Your goal is to be an intelligent semantic search engine for the user's digital brain."""

# Prompt to condense question with history
condense_question_prompt = PromptTemplate.from_template(
    """Given the following conversation and a follow-up question, rewrite the follow-up question to be a standalone question, in its original language.
    
    Chat History:
    {chat_history}
    Follow Up Input: {question}
    Standalone question:"""
)

# Prompt for final response (QA)
qa_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=system_prompt + "\n\nContext:\n{context}\n\nQuestion: {question}\nAnswer:"
)


def verify_ollama_available():
    """Verify that Ollama is running and accessible"""
    try:
        import requests
        response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
        response.raise_for_status()
        logger.info("Ollama is available")
    except Exception as e:
        logger.error(f"Ollama is not available: {e}")
        raise ModelNotAvailableError(
            f"Ollama is not running at {settings.ollama_base_url}. "
            "Run: ollama serve"
        )


def create_retriever_with_reranker(db):
    """
    Create a retriever with optional reranking
    
    Args:
        db: ChromaDB instance
    
    Returns:
        Configured retriever (with or without reranker)
    """
    logger.info("=" * 50)
    logger.info("📦 Configurando Hybrid Search (BM25 + Vector)")
    logger.info("=" * 50)
    
    # Obtener documentos de la DB para BM25
    try:
        db_data = db.get()
        texts = db_data['documents']
        metadatas = db_data['metadatas']
        
        if not texts:
            logger.warning("No se encontraron documentos en la DB")
            raise NoDocumentsFoundError("Base de datos vacía")
        
        # Log stats about links in metadata
        docs_with_links = sum(1 for m in metadatas if m.get('links', ''))
        total_links = sum(len(m.get('links', '').split(',')) for m in metadatas if m.get('links', ''))
        logger.info(f"📊 DB Stats: {len(texts)} chunks, {docs_with_links} con enlaces, {total_links} enlaces totales")
        
        # Create BM25 retriever
        docs = [Document(page_content=t, metadata=m) for t, m in zip(texts, metadatas)]
        bm25_retriever = BM25Retriever.from_documents(docs)
        bm25_retriever.k = settings.bm25_k
        logger.info(f"   BM25 k={settings.bm25_k}")
        
        # Create vector retriever
        chroma_retriever = db.as_retriever(search_kwargs={"k": settings.retrieval_k})
        logger.info(f"   Vector k={settings.retrieval_k}")
        
        # Combine with ensemble
        ensemble_retriever = EnsembleRetriever(
            retrievers=[bm25_retriever, chroma_retriever],
            weights=[settings.bm25_weight, settings.vector_weight]
        )
        logger.info(f"   Ensemble weights: BM25={settings.bm25_weight}, Vector={settings.vector_weight}")
        
        logger.info("✅ EnsembleRetriever created successfully")
        
        # Add reranker if enabled
        if settings.use_reranker:
            logger.info(f"🔄 Adding reranker: {settings.reranker_model}")
            logger.info(f"   Reranker top_n={settings.reranker_top_n}")
            try:
                model = HuggingFaceCrossEncoder(model_name=settings.reranker_model)
                compressor = CrossEncoderReranker(model=model, top_n=settings.reranker_top_n)
                
                retriever = ContextualCompressionRetriever(
                    base_compressor=compressor,
                    base_retriever=ensemble_retriever
                )
                logger.info("✅ Reranker configured successfully")
                logger.info("=" * 50)
                return retriever
            except Exception as e:
                logger.warning(f"⚠️ Could not configure reranker: {e}. Using ensemble without reranker")
                return ensemble_retriever
        else:
            logger.info("ℹ️ Reranker disabled in configuration")
            return ensemble_retriever
            
    except NoDocumentsFoundError:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating retriever: {e}. Using only Vector Search")
        return db.as_retriever(search_kwargs={"k": settings.retrieval_k})


def create_qa_chain(db):
    """
    Create conversational QA chain with hybrid search and optional reranking
    
    Args:
        db: ChromaDB instance
    
    Returns:
        ConversationalRetrievalChain instance
    """
    # Verify Ollama is available
    verify_ollama_available()
    
    logger.info(f"Initializing Ollama model ({settings.llm_model})")
    llm = OllamaLLM(
        model=settings.llm_model,
        base_url=settings.ollama_base_url
    )
    
    # Create retriever (with or without reranker)
    retriever = create_retriever_with_reranker(db)
    
    logger.info("Creating ConversationalRetrievalChain")
    qa_chain_instance = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        condense_question_prompt=condense_question_prompt,
        combine_docs_chain_kwargs={"prompt": qa_prompt},
        verbose=True
    )
    logger.info("ConversationalRetrievalChain configured successfully")
    return qa_chain_instance



def retrieve_with_links(retriever, query: str) -> List[Document]:
    """Retrieve documents and their linked references (GraphRAG)"""
    # 1. Base retrieval
    docs = retriever.invoke(query)
    
    # 2. Extract links
    linked_sources = set()
    for doc in docs:
        links_str = doc.metadata.get('links', '')
        if links_str:
            for link in links_str.split(','):
                if link.strip():
                    linked_sources.add(link.strip())
    
    # 3. Fetch linked docs if any
    if linked_sources:
        logger.info(f"GraphRAG: Found {len(linked_sources)} linked notes")
        # We need access to the vectorstore to fetch by source
        # This is a bit tricky since we only have the retriever interface here
        # We'll assume the retriever has a 'vectorstore' attribute or similar
        # For now, we'll skip the actual fetching implementation until we have direct DB access
        # or we can modify the retriever to support this.
        pass
        
    return docs

def ask_question(qa_chain, question: str, chat_history: List[Tuple[str, str]] = []) -> Tuple[str, List[Document]]:
    """
    Ask a question using the QA chain
    """
    logger.info(f"Processing question: {question}")
    
    try:
        # Get retriever from chain
        retriever = qa_chain.retriever
        
        # Retrieve docs (including GraphRAG logic)
        # Note: ConversationalRetrievalChain does retrieval internally, 
        # so we can't easily inject the link retrieval step without subclassing 
        # or using a custom chain.
        
        # Workaround: We will rely on the standard retrieval for now
        # and implement the full GraphRAG logic in a future iteration 
        # where we rebuild the chain structure.
        
        response = qa_chain.invoke({
            "question": question, 
            "chat_history": chat_history
        })
        
        answer = response['answer']
        source_documents = response.get("source_documents", [])
        
        logger.info(f"Response generated with {len(source_documents)} sources")
        
        return answer, source_documents
        
    except ModelNotAvailableError:
        raise
    except NoDocumentsFoundError:
        raise
    except Exception as e:
        logger.error(f"Error executing ConversationalRetrievalChain: {e}", exc_info=True)
        raise RAGError(f"Error processing question: {str(e)}")

