# ObsidianRAG - Copilot Instructions

## Architecture Overview

ObsidianRAG is a RAG (Retrieval-Augmented Generation) system for querying Obsidian notes using LangGraph and local LLMs (Ollama).

### Core Components
```
main.py                → FastAPI server, lifespan-managed startup
├── services/
│   ├── qa_agent.py        → LangGraph StateGraph (retrieve→generate nodes)
│   ├── qa_service.py      → Hybrid retriever (BM25 + Vector + Reranker)
│   ├── db_service.py      → ChromaDB management, incremental indexing
│   └── metadata_tracker.py → File change detection via hashes
├── config/settings.py     → Pydantic BaseSettings (.env support)
└── streamlit_app.py       → Streamlit UI with vault stats
```

### Data Flow
1. Question → `qa_agent.retrieve_node` (hybrid search) → documents
2. Documents → GraphRAG link expansion via `[[wikilinks]]` → enriched context
3. Context → `qa_agent.generate_node` (Ollama LLM) → answer

## Key Patterns

### Configuration
All settings in `config/settings.py` using Pydantic `BaseSettings`. Access: `from config.settings import settings`.

### Imports (LangChain 1.x)
```python
# Use langchain_classic for deprecated modules
from langchain_classic.chains import ConversationalRetrievalChain
from langchain_classic.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
```

### LangGraph Agent Pattern
```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: List[Document]
    question: str
    answer: str

# Nodes return partial state updates
def retrieve_node(state: AgentState, retriever, db) -> dict:
    return {"context": docs}
```

### FastAPI Lifespan (not @app.on_event)
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load db, create agent
    yield
    # Shutdown: cleanup
```

## Developer Commands

```bash
# Run API server
uv run main.py

# Run Streamlit UI  
uv run streamlit run streamlit_app.py

# Force database rebuild
rm -rf db/ && uv run main.py

# Update dependencies
uv lock --upgrade && uv sync
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ask` | POST | Ask question, returns answer + sources |
| `/health` | GET | System status, model info |
| `/stats` | GET | Vault statistics (notes, chunks, links) |
| `/rebuild_db` | POST | Force reindex all notes |

## Critical Settings (config/settings.py)

| Setting | Purpose | Default |
|---------|---------|---------|
| `reranker_top_n` | Final docs after reranking | 6 |
| `retrieval_k` | Docs before reranking | 12 |
| `chunk_size` | Text chunk size | 1500 |
| `use_reranker` | Enable CrossEncoder | True |
| `bm25_weight` / `vector_weight` | Hybrid search weights | 0.4 / 0.6 |

## Common Issues

- **Import errors after upgrade**: Use `langchain_classic` for chains/retrievers
- **Empty links metadata**: DB predates link extraction → `rm -rf db/`
- **Ollama not available**: Run `ollama serve` first
- **Fragmented context**: `read_full_document()` in qa_agent.py reconstitutes docs

## File Locations

- **Debug scripts**: `scripts/debug/` (check_db.py, debug_retrieval.py)
- **Test scripts**: `scripts/tests/` (test_links.py, test_migration.py)
- **Logs**: `logs/` (gitignored)
- **Vector DB**: `db/` (gitignored, delete to force rebuild)
