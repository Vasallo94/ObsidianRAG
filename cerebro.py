from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ObsidianLangchain import ask_question, logger

app = FastAPI(title="Obsidian RAG API", description="API para consultar notas de Obsidian usando RAG")

class Question(BaseModel):
    text: str

class Source(BaseModel):
    source: str

class Answer(BaseModel):
    result: str
    sources: List[Source]

@app.post("/ask", response_model=Answer)
async def ask(question: Question):
    try:
        logger.info(f"Recibida pregunta: {question.text}")
        result, sources = ask_question(question.text)
        logger.info("Respuesta generada exitosamente")
        return Answer(
            result=result,
            sources=[Source(source=source.metadata['source']) for source in sources]
        )
    except Exception as e:
        logger.error(f"Error al procesar la pregunta: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Bienvenido a la API de Obsidian RAG"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)