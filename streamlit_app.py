import os
from typing import Optional

import requests
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration with Obsidian icon
st.set_page_config(page_title="Obsidian RAG", page_icon="assets/obsidian-icon.svg", layout="wide")

# Load custom CSS
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css("assets/styles.css")

def get_system_info() -> dict:
    """Get system information from the backend"""
    info = {
        "llm_model": "...",
        "embedding": "...",
        "status": "🔴 Disconnected",
        "db_ready": False
    }
    try:
        response = requests.get("http://localhost:8000/health", timeout=3)
        if response.status_code == 200:
            data = response.json()
            info["llm_model"] = data.get("model", "gemma3")
            info["embedding"] = data.get("embedding_model", "multilingual").split("/")[-1][:20]
            info["status"] = "🟢 Connected"
            info["db_ready"] = data.get("db_ready", False)
    except requests.exceptions.ConnectionError:
        info["status"] = "🔴 Server not started"
    except Exception:
        info["status"] = "🟡 Connection error"
    return info


def get_vault_stats() -> dict:
    """Get vault statistics from the backend"""
    try:
        response = requests.get("http://localhost:8000/stats", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

# Main header
st.markdown("# 🧠 Obsidian RAG")

# Improved sidebar
with st.sidebar:
    # System status
    sys_info = get_system_info()
    
    # Status badge
    st.markdown(f"### {sys_info['status']}")
    
    if sys_info["status"] == "🟢 Connected":
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🤖 LLM**")
            st.code(sys_info["llm_model"], language=None)
        with col2:
            st.markdown("**📊 Embeddings**")
            st.code(sys_info["embedding"][:15], language=None)
        
        if sys_info["db_ready"]:
            st.success("Database ready", icon="✅")
        else:
            st.warning("Indexing notes...", icon="⏳")
    else:
        st.error("Start server: `uv run main.py`")
    
    st.divider()
    
    # Actions
    st.markdown("### 🔧 Actions")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Reindex", use_container_width=True):
            with st.spinner("Reindexing..."):
                try:
                    response = requests.post("http://localhost:8000/rebuild_db", timeout=300)
                    if response.status_code == 200:
                        st.success("✅ Done")
                        st.rerun()
                    else:
                        st.error("Error")
                except Exception as e:
                    st.error(f"{e}")
    
    with col2:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = None
            st.rerun()
    
    st.divider()
    
    # Vault Statistics
    if sys_info["status"] == "🟢 Connected" and sys_info["db_ready"]:
        stats = get_vault_stats()
        if stats and "error" not in stats:
            st.markdown("### 📊 Vault Info")
            
            # Main metrics in columns
            c1, c2 = st.columns(2)
            with c1:
                st.metric("📝 Notes", stats.get("total_notes", 0))
                st.metric("🔗 Links", stats.get("internal_links", 0))
            with c2:
                st.metric("📦 Chunks", stats.get("total_chunks", 0))
                st.metric("📁 Folders", stats.get("folders", 0))
            
            # Word count with formatting
            total_words = stats.get("total_words", 0)
            if total_words > 1000:
                word_display = f"{total_words/1000:.1f}K"
            else:
                word_display = str(total_words)
            
            st.caption(f"💬 {word_display} words indexed · ~{stats.get('avg_words_per_chunk', 0)} words/chunk")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Initialize session_id
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# Base path to Obsidian vault (for shortening displayed paths)
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_PATH", "")

def shorten_source_path(full_path: str) -> str:
    """Shorten full path to just folder/file.md"""
    if not full_path or full_path == 'Unknown':
        return 'Unknown'
    
    # Remove vault base path if it exists
    if full_path.startswith(OBSIDIAN_VAULT_PATH):
        relative_path = full_path[len(OBSIDIAN_VAULT_PATH):].lstrip('/')
    else:
        relative_path = full_path
    
    # Get only the last 2 parts (folder/file.md)
    parts = relative_path.split('/')
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    else:
        return parts[-1] if parts else relative_path

def format_source_display(source: dict) -> str:
    """Format a source for display with score and type."""
    source_name = source.get('source', 'Unknown')
    short_name = shorten_source_path(source_name)
    score = source.get('score', 0.0)
    retrieval_type = source.get('retrieval_type', 'retrieved')
    
    # Emoji based on retrieval type
    if retrieval_type == 'graphrag_link':
        type_emoji = "🔗"
    else:
        type_emoji = "📄"
    
    # Color based on score
    if score >= 0.6:
        relevance_color = "🟢"
    elif score >= 0.3:
        relevance_color = "🟡"
    else:
        relevance_color = "🔴"
    
    return f"{type_emoji} `{short_name}` {relevance_color} {score:.0%}"

def display_sources(sources: list, process_time: Optional[float] = None):
    """Display sources with improved formatting."""
    if sources:
        with st.expander("📚 Sources & Relevance", expanded=False):
            st.markdown("##### Ordered by relevance:")
            for source in sources:
                st.markdown(format_source_display(source))
            
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.caption("📄 direct | 🔗 link")
            with col2:
                if process_time:
                    st.caption(f"⏱️ {process_time:.2f}s")

# Display chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message and message["sources"]:
            display_sources(message["sources"], message.get("process_time"))

# Chat input
if prompt := st.chat_input("Ask a question about your notes..."):
    # Display user message
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Prepare payload
    payload = {"text": prompt}
    if st.session_state.session_id:
        payload["session_id"] = st.session_state.session_id

    # Get response
    with st.chat_message("assistant"):
        try:
            url = "http://localhost:8000/ask"
            with st.spinner("Thinking..."):
                response = requests.post(url, json=payload, timeout=120)
                
                if response.status_code == 200:
                    data = response.json()
                    result = data["result"]
                    sources = data.get("sources", [])
                    process_time = data.get("process_time", 0)
                    
                    # Update session_id if new
                    if not st.session_state.session_id and "session_id" in data:
                        st.session_state.session_id = data["session_id"]

                    st.markdown(result)
                    
                    # Display sources
                    display_sources(sources, process_time)
                    
                    # Save to history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": result,
                        "sources": sources,
                        "process_time": process_time
                    })
                else:
                    error_msg = f"Error: {response.status_code} - {response.text}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
        
        except requests.exceptions.ConnectionError:
            error_msg = "❌ Could not connect to server. Make sure `main.py` is running."
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
        except Exception as e:
            error_msg = f"An error occurred: {e}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})