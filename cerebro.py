from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ObsidianLangchain import ask_question, logger

app = FastAPI(
    title="Obsidian RAG API",
    description="API para consultar notas de Obsidian usando RAG",
    version="1.0.0"
)

class Question(BaseModel):
    text: str = Field(..., description="La pregunta que quieres hacer")

class Source(BaseModel):
    source: str = Field(..., description="La fuente de la información")

class Answer(BaseModel):
    question: str = Field(..., description="La pregunta que se hizo")
    result: str = Field(..., description="La respuesta generada")
    sources: List[Source] = Field(..., description="Las fuentes de la información")
    text_blocks: List[str] = Field(..., description="Los bloques de texto utilizados para construir la respuesta")

@app.post("/ask", response_model=Answer, summary="Haz una pregunta", description="Este endpoint permite hacer una pregunta y obtener una respuesta con contexto.")
async def ask(question: Question):
    """
    Endpoint para hacer una pregunta y obtener una respuesta con contexto.
    - **question**: La pregunta que quieres hacer.
    """
    try:
        logger.info(f"Recibida pregunta: {question.text}")
        result, sources = ask_question(question.text)
        logger.info("Respuesta generada exitosamente")
        text_blocks = [source.page_content for source in sources]
        return Answer(
            question=question.text,
            result=result,
            sources=[Source(source=source.metadata['source']) for source in sources],
            text_blocks=text_blocks
        )
    except Exception as e:
        logger.error(f"Error al procesar la pregunta: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", summary="Endpoint raíz", description="Endpoint de bienvenida a la API.")
async def root():
    """
    Endpoint de bienvenida a la API.
    """
    return {"message": "Bienvenido a la API de Obsidian RAG"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)