import requests
import streamlit as st

# Configuración de la página con el ícono de Obsidian
st.set_page_config(page_title="Obsidian RAG", page_icon="obsidian-icon.svg")

# Cargar el archivo CSS personalizado
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css("styles.css")

# Colocar el título y el ícono 
col1, col2 = st.columns([1, 9])

with col1:
    st.image("obsidian-icon.svg", width=100)

with col2:
    st.markdown("<h1 style='text-align: left; margin-bottom: -20px;'>RAG</h1>", unsafe_allow_html=True)

# Añadir algo de espacio arriba para evitar que el campo de entrada quede demasiado cerca de la parte superior
st.write("")

# Campo de entrada para la pregunta
question = st.text_input("Haz una pregunta:")

# Botón para enviar la pregunta
if st.button("Enviar"):
    if question:
        # Mostrar el spinner mientras se realiza la llamada a la API
        with st.spinner("Cargando..."):
            # Llamada a la API
            response = requests.post(
                "http://localhost:8000/ask",
                json={"text": question}
            )

        if response.status_code == 200:
            data = response.json()

            # Crear dos columnas con una distribución 70/30
            col1, col2 = st.columns([7, 3])

            # Columna 1: Respuesta
            with col1:
                st.subheader("Respuesta:")
                st.write(data["result"])

            # Columna 2: Fuentes y Bloques de Texto
            with col2:
                st.subheader("Fuentes:")
                for source in data["sources"]:
                    st.write(f"- {source['source']}")

                st.subheader("Bloques de texto:")
                for i, block in enumerate(data["text_blocks"], 1):
                    with st.expander(f"Bloque de texto {i}"):
                        st.write(block)
        else:
            st.error("Error al procesar la pregunta. Inténtalo de nuevo.")
    else:
        st.warning("Por favor, ingresa una pregunta.")
