---
name: rag-architect
description: >
  Usa esta skill para diseñar y modificar el pipeline de RAG, incluyendo
  LangGraph, retrieval híbrido, GraphRAG y prompts de LLM.
tools: ['read', 'edit', 'run_command']
---

# RAG & LangGraph Architect

## Cuándo usar esta skill
- Cuando necesites modificar el flujo de preguntas y respuestas.
- Cuando quieras cambiar la lógica de retrieval (BM25, Vector, Reranker).
- Cuando ajustes los prompts del sistema o del LLM.
- Cuando implementes nuevos nodos en el grafo de LangGraph.

## Cómo usar esta skill

### 1. Arquitectura del Grafo
El agente usa `LangGraph` con el estado `AgentState`.
**Flujo**: `START` -> `retrieve` -> `generate` -> `END`

### 2. Implementación de Nodos

#### Retrieve Node
Usa búsqueda híbrida (EnsembleRetriever) + Reranker opcional + Expansión de GraphRAG (wikilinks).
- Ubicación: `obsidianrag/core/qa_agent.py` y `qa_service.py` (si existe split).

#### Generate Node
Construye el prompt con contexto formateado y llama a Ollama via `ChatOllama`.

### 3. GraphRAG Link Expansion
La función clave es `expand_linked_documents`. Busca notas enlazadas mediante `[[wikilinks]]` en los documentos recuperados y las añade al contexto.

### 4. Prompt Engineering
Los prompts están definidos como `ChatPromptTemplate`.
- Sé explícito sobre el rol.
- Pide citas de las notas fuente.
- Maneja el caso "No lo sé".

### 5. Debugging
Para ver qué documentos se recuperan, puedes ajustar el nivel de log a DEBUG en `utils/logger.py` o inspeccionar el estado intermedio del grafo.
