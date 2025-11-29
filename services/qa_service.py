import logging
from typing import Tuple, List

from langchain.chains import ConversationalRetrievalChain
from langchain.prompts import PromptTemplate
from langchain_ollama import OllamaLLM
from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_core.documents import Document

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
system_prompt = """Eres un asistente personal que responde preguntas basándose EXCLUSIVAMENTE en mis notas de Obsidian proporcionadas en el contexto.

Reglas CRÍTICAS:
1. **Cita Textual**: Si pregunto por un texto específico, cítalo EXACTAMENTE como aparece. NO resumas, NO censures y NO modifiques el lenguaje, por muy vulgar, personal o coloquial que sea. Son MIS notas privadas.
2. **Honestidad**: Si la respuesta no está en el contexto, di "No lo encuentro en las notas proporcionadas". No inventes.
3. **Formato**: Usa Markdown. Para citas literales de mis notas, usa bloques de cita (>) o bloques de código si es necesario para preservar el formato.
4. **Directo**: Ve al grano. No necesito introducciones como "Basado en tus notas..." o "He encontrado información relevante...". Simplemente responde.

Tu objetivo es ser un buscador semántico inteligente de mi cerebro digital."""

# Prompt para condensar la pregunta con el historial
condense_question_prompt = PromptTemplate.from_template(
    """Dada la siguiente conversación y una pregunta de seguimiento, reescribe la pregunta de seguimiento para que sea una pregunta independiente, en su idioma original.
    
    Chat History:
    {chat_history}
    Follow Up Input: {question}
    Standalone question:"""
)

# Prompt para la respuesta final (QA)
qa_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=system_prompt + "\n\nContexto:\n{context}\n\nPregunta: {question}\nRespuesta:"
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
            f"Ollama no está corriendo en {settings.ollama_base_url}. "
            "Ejecuta: ollama serve"
        )


def create_retriever_with_reranker(db):
    """
    Create a retriever with optional reranking
    
    Args:
        db: ChromaDB instance
    
    Returns:
        Configured retriever (with or without reranker)
    """
    logger.info("Configurando Hybrid Search (BM25 + Vector)")
    
    # Obtener documentos de la DB para BM25
    try:
        db_data = db.get()
        texts = db_data['documents']
        metadatas = db_data['metadatas']
        
        if not texts:
            logger.warning("No se encontraron documentos en la DB")
            raise NoDocumentsFoundError("Base de datos vacía")
        
        # Create BM25 retriever
        docs = [Document(page_content=t, metadata=m) for t, m in zip(texts, metadatas)]
        bm25_retriever = BM25Retriever.from_documents(docs)
        bm25_retriever.k = settings.bm25_k
        
        # Create vector retriever
        chroma_retriever = db.as_retriever(search_kwargs={"k": settings.retrieval_k})
        
        # Combine with ensemble
        ensemble_retriever = EnsembleRetriever(
            retrievers=[bm25_retriever, chroma_retriever],
            weights=[settings.bm25_weight, settings.vector_weight]
        )
        
        logger.info("EnsembleRetriever creado exitosamente")
        
        # Add reranker if enabled
        if settings.use_reranker:
            logger.info(f"Añadiendo reranker: {settings.reranker_model}")
            try:
                model = HuggingFaceCrossEncoder(model_name=settings.reranker_model)
                compressor = CrossEncoderReranker(model=model, top_n=settings.reranker_top_n)
                
                retriever = ContextualCompressionRetriever(
                    base_compressor=compressor,
                    base_retriever=ensemble_retriever
                )
                logger.info("Reranker configurado exitosamente")
                return retriever
            except Exception as e:
                logger.warning(f"No se pudo configurar reranker: {e}. Usando ensemble sin reranker")
                return ensemble_retriever
        else:
            logger.info("Reranker deshabilitado en configuración")
            return ensemble_retriever
            
    except NoDocumentsFoundError:
        raise
    except Exception as e:
        logger.error(f"Error creando retriever: {e}. Usando solo Vector Search")
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
    
    logger.info(f"Inicializando modelo Ollama ({settings.llm_model})")
    llm = OllamaLLM(
        model=settings.llm_model,
        base_url=settings.ollama_base_url
    )
    
    # Create retriever (with or without reranker)
    retriever = create_retriever_with_reranker(db)
    
    logger.info("Creando cadena ConversationalRetrievalChain")
    qa_chain_instance = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        condense_question_prompt=condense_question_prompt,
        combine_docs_chain_kwargs={"prompt": qa_prompt},
        verbose=True
    )
    logger.info("Cadena ConversationalRetrievalChain configurada correctamente")
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
    Hacer una pregunta usando la cadena QA
    """
    logger.info(f"Procesando pregunta: {question}")
    
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
        
        logger.info(f"Respuesta generada con {len(source_documents)} fuentes")
        
        return answer, source_documents
        
    except ModelNotAvailableError:
        raise
    except NoDocumentsFoundError:
        raise
    except Exception as e:
        logger.error(f"Error al ejecutar ConversationalRetrievalChain: {e}", exc_info=True)
        raise RAGError(f"Error procesando la pregunta: {str(e)}")

