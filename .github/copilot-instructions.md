# ObsidianRAG - Copilot Instructions

## Architecture Overview

ObsidianRAG is a RAG (Retrieval-Augmented Generation) system for querying Obsidian notes using LangGraph and local LLMs (Ollama).

### Core Components
```
main.py             → FastAPI server, main entry point
├── services/
│   ├── qa_agent.py      → LangGraph StateGraph with retrieve→generate nodes
│   ├── qa_service.py    → Retriever setup (BM25 + Vector + Reranker)
│   ├── db_service.py    → ChromaDB management, incremental indexing
│   └── metadata_tracker.py → File change detection
├── config/settings.py   → Centralized Pydantic settings (.env support)
└── streamlit_app.py     → Streamlit UI (optional)
```

### Data Flow
1. Question → `qa_agent.retrieve_node` (hybrid search) → documents
2. Documents → GraphRAG link expansion → enriched context
3. Context → `qa_agent.generate_node` (Ollama LLM) → answer

## Key Patterns

### Configuration
All settings centralized in `config/settings.py` using Pydantic `BaseSettings`. Access via `from config.settings import settings`.

### Obsidian Link Extraction
Use `extract_obsidian_links(content)` from `db_service.py` to parse `[[wikilinks]]`. Links stored in document metadata as comma-separated string.

### LangGraph Agent Pattern
```python
# State definition with TypedDict
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: List[Document]
    question: str
    answer: str

# Nodes are functions: (state, deps) -> partial state update
def retrieve_node(state: AgentState, retriever, db) -> dict:
    return {"context": docs}
```

### Logging Convention
Use `GraphTracer` class in `qa_agent.py` for detailed execution tracing. Log format: emoji prefix + `[NODE_NAME]` + JSON data.

## Developer Commands

```bash
# Run the API server
uv run main.py

# Force database rebuild (delete db/ folder)
rm -rf db/ && uv run main.py

# Run Streamlit UI
uv run streamlit run streamlit_app.py
```

## Critical Configuration (settings.py)

| Setting | Purpose | Default |
|---------|---------|---------|
| `reranker_top_n` | Final docs returned | 6 |
| `retrieval_k` | Docs before reranking | 12 |
| `chunk_size` | Text chunk size | 1500 |
| `use_reranker` | Enable CrossEncoder | True |

## Common Issues

- **Empty links metadata**: DB was created before link extraction was added → `rm -rf db/`
- **Fragmented context**: Multiple chunks from same doc → `read_full_document()` in qa_agent.py handles this
- **Ollama not available**: Run `ollama serve` before starting

## Testing Scripts

Located in `scripts/`:
- `scripts/debug/` - Database inspection utilities
- `scripts/tests/` - Integration tests for links and migration
