import time

import requests
import streamlit as st

# Configuración de la página con el ícono de Obsidian
st.set_page_config(page_title="Obsidian RAG", page_icon="obsidian-icon.svg")

# Cargar el archivo CSS personalizado
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css("styles.css")
st.markdown("# Obsidian RAG")

# Campo de entrada para la pregunta
question = st.text_input("Haz una pregunta:", key="question_input")

# Botón para enviar la pregunta
if st.button("Enviar"):
    if question:
        try:
            url = "http://localhost:8000/ask"  # Actualiza si estás usando una dirección diferente
            headers = {"Content-Type": "application/json"}
            payload = {"text": question}

            with st.spinner("Procesando..."):
                start_time = time.time()
                response = requests.post(url, json=payload, headers=headers)
                end_time = time.time()
                elapsed_time = end_time - start_time

            if response.status_code == 200:
                data = response.json()

                # Crear dos columnas con una distribución 70/30
                col1, col2 = st.columns([7, 3])

                # Columna 1: Respuesta
                with col1:
                    st.markdown("## Respuesta:")
                    st.markdown(data["result"])

                # Columna 2: Detalles
                with col2:
                    st.markdown("### Fuentes y Bloques de Texto:")
                    if data.get("sources"):
                        if data.get("text_blocks"):
                            for source, block in zip(data["sources"], data["text_blocks"]):
                                st.markdown(f"- {source['source']}")
                                with st.expander("Bloque de texto"):
                                    st.markdown(block)
                        else:
                            for source in data["sources"]:
                                st.markdown(f"- {source['source']}")
                            st.markdown("No se encontraron bloques de texto.")
                    else:
                        st.markdown("No se encontraron fuentes.")
                        
                    st.markdown("### Detalles de la solicitud:")
                    process_time = data.get("process_time", None)
                    if isinstance(process_time, (int, float)):
                        st.markdown(f"*Tiempo de procesamiento en la API:* {process_time:.2f} *segundos*")
                    else:
                        st.markdown(f"*Tiempo de procesamiento en la API:* {process_time}")

                    st.markdown(f"_Tiempo total de solicitud:_ {elapsed_time:.2f} *segundos*")
            else:
                st.error(f"Error en la solicitud: {response.status_code} - {response.text}")
        except Exception as e:
            st.error(f"Ocurrió un error: {e}")
    else:
        st.warning("Por favor, ingresa una pregunta.")