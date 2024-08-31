# Obsidian RAG Project
## Descripción
El proyecto Obsidian RAG (Retrieval-Augmented Generation) proporciona una solución para consultar notas almacenadas en Obsidian mediante un modelo de lenguaje (LLAMA3.1)

Utiliza un pipeline basado en LangChain para cargar, dividir y consultar documentos de Obsidian, y una API construida con FastAPI para interactuar con el modelo. Además, se ofrece una interfaz gráfica para realizar consultas y visualizar respuestas utilizando Streamlit.

## Componentes del Proyecto
- ObsidianLangchain.py: Script principal que gestiona la carga de documentos, creación de la base de datos vectorial, configuración del modelo de lenguaje y la cadena de recuperación y respuesta.
- cerebro.py: API construida con FastAPI que expone un endpoint para hacer preguntas y obtener respuestas con contexto, utilizando el modelo de lenguaje y la base de datos vectorial.
- app.py: Interfaz gráfica desarrollada con Streamlit para interactuar con la API y mostrar respuestas a las preguntas de los usuarios.


## Instalación
Clona el repositorio:
```sh
git clone <https://github.com/Vasallo94/ObsidianLangchain.git>
cd <DIRECTORIO_DEL_PROYECTO>
```
Crea un entorno virtual y actívalo:
```sh
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```
Instala las dependencias:
```sh
pip install -r requirements.txt
```
## Configuración
**ObsidianLangchain.py:**
- Modifica el path en ObsidianLoader para que apunte al directorio donde se almacenan tus notas de Obsidian.

**cerebro.py**: No requiere configuración adicional, pero asegúrate de que el script ObsidianLangchain.py esté disponible y correctamente configurado.
**app.py**: Asegúrate de que el archivo **styles.css** y el ícono obsidian-icon.svg estén en el mismo directorio que app.py.
## Uso
- **Ejecutar la API**
- Para iniciar la API, ejecuta el siguiente comando:
```sh
python cerebro.py
```
La API estará disponible en http://localhost:8000.
- **Ejecutar la Interfaz de Usuario**
- Para iniciar la interfaz gráfica, ejecuta el siguiente comando:
```sh
streamlit run app.py
```
La aplicación de Streamlit estará disponible en http://localhost:8501.
- **Hacer Preguntas**
- Desde la interfaz de usuario (Streamlit): Ingresa tu pregunta en el campo de texto y haz clic en "Enviar" para obtener una respuesta.
- Desde la API: Envía una solicitud POST a http://localhost:8000/ask con un JSON que contenga la pregunta:
```json
{
    "text": "¿Qué opinas sobre el infinito?"
}
```
La respuesta será un JSON con la respuesta generada, las fuentes de información y los bloques de texto utilizados.
- **Ejemplo de Uso**
- Ejecuta la API:
```sh
python cerebro.py
```
Ejecuta la interfaz gráfica:
```sh
streamlit run app.py
```
Haz una pregunta en la interfaz gráfica y visualiza la respuesta junto con las fuentes y los bloques de texto utilizados.

**Swagger**
La API FastAPI incluye una interfaz Swagger que puedes utilizar para probar los endpoints y ver la documentación. Visita http://localhost:8000/docs para acceder a Swagger.

**Contribuciones**
Si deseas contribuir al proyecto, por favor abre un issue o envía un pull request. Asegúrate de seguir las mejores prácticas y de proporcionar una descripción clara de los cambios realizados.


