import requests
import streamlit as st

# Configuración de la página
st.set_page_config(page_title="Obsidian RAG", page_icon=":books:")

# Título de la aplicación
st.title("Obsidian RAG")

# Campo de entrada para la pregunta
question = st.text_input("Haz una pregunta:")

# Botón para enviar la pregunta
if st.button("Enviar"):
    if question:
        # Llamada a la API
        response = requests.post(
            "http://localhost:8000/ask",
            json={"text": question}
        )

        if response.status_code == 200:
            data = response.json()
            st.subheader("Respuesta:")
            st.write(data["result"])

            st.subheader("Fuentes:")
            for source in data["sources"]:
                st.write(f"- {source['source']}")
        else:
            st.error("Error al procesar la pregunta. Inténtalo de nuevo.")
    else:
        st.warning("Por favor, ingresa una pregunta.")