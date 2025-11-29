# Release v2.0.0 🚀

**Release Date:** November 29, 2025

This is a major release that completely overhauls the architecture from the original v1.0 (August 2024). The project has been rewritten from scratch with a focus on better retrieval quality, modern tooling, and developer experience.

---

## 🎯 Highlights

- **LangGraph Agent Architecture**: Replaced simple chain with a stateful graph-based agent
- **Hybrid Search**: BM25 + Vector search with ensemble retrieval
- **CrossEncoder Reranker**: Relevance reordering with BAAI/bge-reranker-v2-m3
- **GraphRAG**: Context expansion following Obsidian `[[wikilinks]]`
- **Modern Python Tooling**: Migrated from pip/requirements.txt to `uv` + `pyproject.toml`
- **One-Command Installation**: `./install.sh` handles everything

---

## ✨ New Features

### 🔍 Advanced Retrieval Pipeline
- **Hybrid Search**: Combines semantic (vector) and lexical (BM25) search
- **Ensemble Retriever**: Configurable weights between BM25 and vector search
- **CrossEncoder Reranker**: Re-scores documents using `BAAI/bge-reranker-v2-m3`
- **GraphRAG Link Expansion**: Automatically fetches linked notes via `[[wikilinks]]`
- **Relevance Scores**: Each source displays its reranker score (0-100%)

### 🤖 LangGraph Agent
- **StateGraph Architecture**: Proper agent with `retrieve → generate` nodes
- **Streaming Support**: Real-time token streaming (disabled by default for stability)
- **Detailed Tracing**: `GraphTracer` class for execution debugging
- **Smart Prompting**: Context-aware system prompt that adapts to note language

### 📊 Incremental Indexing
- **File Change Detection**: Only re-indexes modified/new notes
- **Metadata Tracking**: `metadata.json` stores file hashes and timestamps
- **Force Rebuild**: Delete `db/` folder to force complete reindex

### ⚙️ Centralized Configuration
- **Pydantic Settings**: All config in `config/settings.py`
- **Environment Variables**: `.env` file support
- **Sensible Defaults**: Works out of the box with minimal config

### 🎨 Improved UI
- **Cleaner Streamlit Interface**: Simplified sidebar, removed clutter
- **Source Display**: Shows retrieved documents with scores
- **Chat History**: Maintains conversation context

---

## 🔧 Technical Changes

### Architecture Refactor
| Component | v1.0 (2024) | v2.0 (2025) |
|-----------|-------------|-------------|
| Entry Point | `cerebro.py` | `main.py` |
| UI | `app.py` | `streamlit_app.py` |
| Agent | Simple chain | LangGraph StateGraph |
| Retrieval | Vector only | Hybrid (BM25 + Vector + Reranker) |
| Config | Scattered | `config/settings.py` |
| Indexing | Full rebuild | Incremental |

### New Files
- `services/qa_agent.py` - LangGraph agent implementation
- `services/metadata_tracker.py` - File change detection
- `config/settings.py` - Centralized Pydantic settings
- `utils/logger.py` - Logging configuration
- `install.sh` - One-command installer
- `pyproject.toml` - Modern Python project config

### Dependency Updates
- **LangChain**: 0.2.x → 1.1.0 (with `langchain-classic` for deprecated modules)
- **LangGraph**: New dependency (0.5.4 → 1.0.4)
- **ChromaDB**: 0.4.x → 1.3.5
- **FastAPI**: 0.100.x → 0.122.0
- **Streamlit**: 1.30.x → 1.51.0
- **Pydantic**: 1.x → 2.x

### Package Manager
- Migrated from `pip` + `requirements.txt` to `uv` + `pyproject.toml`
- Much faster dependency resolution and installation
- Reproducible builds with `uv.lock`

---

## 🛠️ Breaking Changes

1. **File Renames**:
   - `cerebro.py` → `main.py`
   - `app.py` → `streamlit_app.py`

2. **Configuration**:
   - All settings now in `config/settings.py`
   - `.env` file required for `OBSIDIAN_PATH`

3. **Database**:
   - New metadata format - delete `db/` folder on first run

4. **Dependencies**:
   - Must use `uv` for installation (`pip` may work but not recommended)

---

## 📦 Installation

```bash
# Clone and install
git clone https://github.com/Vasallo94/ObsidianRAG.git
cd ObsidianRAG
./install.sh

# Or manually
uv sync
cp .env.example .env
# Edit .env with your Obsidian vault path
```



## 🙏 Acknowledgments

Built with:
- [LangChain](https://langchain.com/) & [LangGraph](https://langchain-ai.github.io/langgraph/)
- [Ollama](https://ollama.ai/) for local LLMs
- [ChromaDB](https://www.trychroma.com/) for vector storage
- [HuggingFace](https://huggingface.co/) for embeddings and rerankers

---

**Full Changelog**: https://github.com/Vasallo94/ObsidianRAG/compare/47828f3...v2.0.0
