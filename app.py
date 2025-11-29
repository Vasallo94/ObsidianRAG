import time
import requests
import streamlit as st

# Configuración de la página con el ícono de Obsidian
st.set_page_config(page_title="Obsidian RAG", page_icon="assets/obsidian-icon.svg", layout="wide")

# Cargar el archivo CSS personalizado
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css("assets/styles.css")
st.markdown("# Obsidian RAG Chat")

# Sidebar para acciones administrativas
with st.sidebar:
    st.header("Administración")
    if st.button("Reindexar Base de Datos"):
        with st.spinner("Reconstruyendo base de datos... Esto puede tardar unos minutos."):
            try:
                response = requests.post("http://localhost:8000/rebuild_db")
                if response.status_code == 200:
                    st.success("Base de datos reindexada correctamente.")
                else:
                    st.error(f"Error al reindexar: {response.text}")
            except Exception as e:
                st.error(f"Error de conexión: {e}")

# Inicializar historial de chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Inicializar session_id
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# Mostrar mensajes de chat del historial
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message:
            with st.expander("Fuentes y Detalles"):
                for source in message["sources"]:
                    st.markdown(f"- {source['source']}")
                if "process_time" in message:
                    st.caption(f"Tiempo de procesamiento: {message['process_time']:.2f}s")

# Entrada de chat
if prompt := st.chat_input("Haz una pregunta sobre tus notas..."):
    # Mostrar mensaje del usuario
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Preparar payload
    url = "http://localhost:8000/ask"
    payload = {"text": prompt}
    if st.session_state.session_id:
        payload["session_id"] = st.session_state.session_id

    # Obtener respuesta
    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:
                start_time = time.time()
                response = requests.post(url, json=payload)
                end_time = time.time()
                
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
                    if sources:
                        with st.expander("Fuentes y Detalles"):
                            for source in sources:
                                st.markdown(f"- {source['source']}")
                            st.caption(f"Tiempo de procesamiento API: {process_time:.2f}s")
                    
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
            except Exception as e:
                error_msg = f"Ocurrió un error: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})