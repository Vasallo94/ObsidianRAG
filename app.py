import os
from typing import Optional

import requests
import streamlit as st
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de la página con el ícono de Obsidian
st.set_page_config(page_title="Obsidian RAG", page_icon="assets/obsidian-icon.svg", layout="wide")

# Cargar el archivo CSS personalizado
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css("assets/styles.css")

def get_system_info() -> dict:
    """Obtiene información del sistema desde el backend"""
    info = {
        "llm_model": "...",
        "embedding": "...",
        "status": "🔴 Desconectado",
        "db_ready": False
    }
    try:
        response = requests.get("http://localhost:8000/health", timeout=3)
        if response.status_code == 200:
            data = response.json()
            info["llm_model"] = data.get("model", "gemma3")
            info["embedding"] = data.get("embedding_model", "multilingual").split("/")[-1][:20]
            info["status"] = "🟢 Conectado"
            info["db_ready"] = data.get("db_ready", False)
    except requests.exceptions.ConnectionError:
        info["status"] = "🔴 Servidor no iniciado"
    except Exception:
        info["status"] = "🟡 Error de conexión"
    return info

# Header principal
st.markdown("# 🧠 Obsidian RAG")

# Sidebar mejorada
with st.sidebar:
    # Estado del sistema
    sys_info = get_system_info()
    
    # Status badge
    st.markdown(f"### {sys_info['status']}")
    
    if sys_info["status"] == "🟢 Conectado":
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🤖 LLM**")
            st.code(sys_info["llm_model"], language=None)
        with col2:
            st.markdown("**📊 Embeddings**")
            st.code(sys_info["embedding"][:15], language=None)
        
        if sys_info["db_ready"]:
            st.success("Base de datos lista", icon="✅")
        else:
            st.warning("Indexando notas...", icon="⏳")
    else:
        st.error("Inicia el servidor: `uv run cerebro.py`")
    
    st.divider()
    
    # Acciones
    st.markdown("### 🔧 Acciones")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Reindexar", use_container_width=True):
            with st.spinner("Reindexando..."):
                try:
                    response = requests.post("http://localhost:8000/rebuild_db", timeout=300)
                    if response.status_code == 200:
                        st.success("✅ Listo")
                        st.rerun()
                    else:
                        st.error("Error")
                except Exception as e:
                    st.error(f"{e}")
    
    with col2:
        if st.button("🗑️ Limpiar", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = None
            st.rerun()
    
    st.divider()
    
    # Ayuda
    with st.expander("💡 Configuración", expanded=False):
        st.markdown("""
        **Cambiar modelo LLM:**
        ```
        # En .env
        LLM_MODEL=gemma3
        ```
        
        **Modelos recomendados:**
        - `gemma3` - Equilibrado
        - `qwen2.5` - Buen español
        - `llama3.2` - Rápido
        """)
    
    st.caption("v2.0 · [GitHub](https://github.com/Vasallo94/ObsidianRAG)")

# Inicializar historial de chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Inicializar session_id
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# Ruta base del vault de Obsidian (para acortar las rutas mostradas)
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_PATH", "")

def shorten_source_path(full_path: str) -> str:
    """Acorta la ruta completa a solo carpeta/archivo.md"""
    if not full_path or full_path == 'Desconocido':
        return 'Desconocido'
    
    # Quitar la ruta base del vault si existe
    if full_path.startswith(OBSIDIAN_VAULT_PATH):
        relative_path = full_path[len(OBSIDIAN_VAULT_PATH):].lstrip('/')
    else:
        relative_path = full_path
    
    # Obtener solo las últimas 2 partes (carpeta/archivo.md)
    parts = relative_path.split('/')
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    else:
        return parts[-1] if parts else relative_path

def format_source_display(source: dict) -> str:
    """Formatea una fuente para mostrar con score y tipo."""
    source_name = source.get('source', 'Desconocido')
    short_name = shorten_source_path(source_name)
    score = source.get('score', 0.0)
    retrieval_type = source.get('retrieval_type', 'retrieved')
    
    # Emoji basado en el tipo de recuperación
    if retrieval_type == 'graphrag_link':
        type_emoji = "🔗"
    else:
        type_emoji = "📄"
    
    # Color basado en score
    if score >= 0.6:
        relevance_color = "🟢"
    elif score >= 0.3:
        relevance_color = "🟡"
    else:
        relevance_color = "🔴"
    
    return f"{type_emoji} `{short_name}` {relevance_color} {score:.0%}"

def display_sources(sources: list, process_time: Optional[float] = None):
    """Muestra las fuentes con formato mejorado."""
    if sources:
        with st.expander("📚 Fuentes y Relevancia", expanded=False):
            st.markdown("##### Ordenadas por relevancia:")
            for source in sources:
                st.markdown(format_source_display(source))
            
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.caption("📄 directo | 🔗 enlace")
            with col2:
                if process_time:
                    st.caption(f"⏱️ {process_time:.2f}s")

# Mostrar mensajes de chat del historial
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message and message["sources"]:
            display_sources(message["sources"], message.get("process_time"))

# Entrada de chat
if prompt := st.chat_input("Haz una pregunta sobre tus notas..."):
    # Mostrar mensaje del usuario
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Preparar payload
    payload = {"text": prompt}
    if st.session_state.session_id:
        payload["session_id"] = st.session_state.session_id

    # Obtener respuesta
    with st.chat_message("assistant"):
        try:
            url = "http://localhost:8000/ask"
            with st.spinner("Pensando..."):
                response = requests.post(url, json=payload, timeout=120)
                
                if response.status_code == 200:
                    data = response.json()
                    result = data["result"]
                    sources = data.get("sources", [])
                    process_time = data.get("process_time", 0)
                    
                    # Actualizar session_id si es nuevo
                    if not st.session_state.session_id and "session_id" in data:
                        st.session_state.session_id = data["session_id"]

                    st.markdown(result)
                    
                    # Mostrar fuentes
                    display_sources(sources, process_time)
                    
                    # Guardar en historial
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
            error_msg = "❌ No se pudo conectar al servidor. Asegúrate de que `cerebro.py` está ejecutándose."
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
        except Exception as e:
            error_msg = f"Ocurrió un error: {e}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})