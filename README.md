# ObsidianRAG 🧠

Sistema RAG (Retrieval-Augmented Generation) para consultar notas de Obsidian usando **LangGraph** y **LLMs locales** con Ollama.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green)
![Ollama](https://img.shields.io/badge/Ollama-Local_LLMs-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

## ✨ Características

### 🔍 Búsqueda Híbrida Avanzada
- **Vectorial + BM25**: Combina embeddings semánticos con búsqueda léxica
- **CrossEncoder Reranker**: BAAI/bge-reranker-v2-m3 para reordenar por relevancia
- **GraphRAG**: Expansión de contexto siguiendo enlaces `[[wikilinks]]` de Obsidian

### 🤖 Integración LLM
- **Ollama Local**: Modelos seleccionables (qwen2.5, qwen3, gemma3, deepseek-r1)
- **Sin dependencias cloud**: Todo corre localmente
- **Streaming deshabilitado**: Respuestas completas para mayor estabilidad

### 📊 Análisis y Métricas
- **Scores de relevancia**: Cada fuente muestra su score de reranker (0-100%)
- **Logging detallado**: Trazabilidad completa de cada consulta
- **Indexación incremental**: Solo procesa notas modificadas

## 🏗️ Arquitectura

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Streamlit  │────▶│   FastAPI    │────▶│  LangGraph  │
│    (UI)     │◀────│   (API)      │◀────│   (Agent)   │
└─────────────┘     └──────────────┘     └─────────────┘
                           │                    │
                           ▼                    ▼
                    ┌──────────────┐     ┌─────────────┐
                    │   ChromaDB   │     │   Ollama    │
                    │  (Vectores)  │     │   (LLM)     │
                    └──────────────┘     └─────────────┘
```

### Componentes Principales

| Archivo | Descripción |
|---------|-------------|
| `cerebro.py` | Servidor FastAPI, punto de entrada principal |
| `app.py` | Interfaz Streamlit (opcional) |
| `services/qa_agent.py` | Agente LangGraph con nodos retrieve→generate |
| `services/qa_service.py` | Configuración del retriever híbrido |
| `services/db_service.py` | Gestión de ChromaDB e indexación |
| `config/settings.py` | Configuración centralizada (Pydantic) |

## 🚀 Instalación

### Requisitos Previos
- Python 3.11+
- [Ollama](https://ollama.ai/) instalado y corriendo
- UV (gestor de paquetes recomendado)

### Pasos

```bash
# Clonar repositorio
git clone https://github.com/tu-usuario/ObsidianRAG.git
cd ObsidianRAG

# Instalar dependencias
uv sync

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tu configuración
```

### Variables de Entorno (.env)

```env
# Ruta a tu vault de Obsidian
OBSIDIAN_PATH=/ruta/a/tu/vault

# Modelo LLM (Ollama)
LLM_MODEL=qwen2.5

# Modelo de embeddings
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2

# Reranker
USE_RERANKER=true
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RERANKER_TOP_N=6

# Chunking
CHUNK_SIZE=1500
CHUNK_OVERLAP=300

# Retrieval
RETRIEVAL_K=12
BM25_K=5
BM25_WEIGHT=0.4
VECTOR_WEIGHT=0.6
```

## 📖 Uso

### Iniciar el Servidor API

```bash
uv run cerebro.py
```

El servidor estará disponible en `http://localhost:8000`

### Iniciar la Interfaz Web (Opcional)

```bash
uv run streamlit run app.py
```

La UI estará en `http://localhost:8501`

### API Endpoints

#### POST /ask
Realiza una consulta al sistema RAG.

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Cuáles son mis notas sobre Python?"}'
```

**Respuesta:**
```json
{
  "answer": "Según tus notas...",
  "sources": [
    {
      "source": "Programación/Python Basics.md",
      "score": 0.92,
      "preview": "..."
    }
  ],
  "timing": {
    "total": 2.5,
    "retrieval": 0.8,
    "generation": 1.7
  }
}
```

#### GET /health
Verifica el estado del servidor.

#### GET /stats
Obtiene estadísticas de la base de datos.

## ⚙️ Configuración Avanzada

### Parámetros Clave (settings.py)

| Parámetro | Descripción | Default |
|-----------|-------------|---------|
| `reranker_top_n` | Documentos finales tras reranking | 6 |
| `retrieval_k` | Documentos antes del reranking | 12 |
| `chunk_size` | Tamaño de chunks de texto | 1500 |
| `chunk_overlap` | Solapamiento entre chunks | 300 |
| `bm25_weight` | Peso de búsqueda léxica | 0.4 |
| `vector_weight` | Peso de búsqueda vectorial | 0.6 |

### Modelos Disponibles

**LLM (Ollama):**
- `qwen2.5` - Recomendado para español
- `qwen3` - Nueva versión con mejor razonamiento
- `gemma3` - Modelo de Google
- `deepseek-r1` - Optimizado para razonamiento

**Embeddings:**
- `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` - Default multilingüe
- `embeddinggemma` (Ollama) - 300M params, 100+ idiomas

## 🔧 Solución de Problemas

### Ollama no disponible
```bash
# Verificar que Ollama esté corriendo
ollama serve

# Descargar modelo si es necesario
ollama pull qwen2.5
```

### Base de datos corrupta
```bash
# Eliminar y reconstruir
rm -rf db/
uv run cerebro.py
```

### Contexto fragmentado
El sistema detecta automáticamente documentos fragmentados y lee el contenido completo usando `read_full_document()`.

### Enlaces vacíos en metadata
Si la base de datos fue creada antes de la extracción de enlaces:
```bash
rm -rf db/
uv run cerebro.py
```

## 📂 Estructura del Proyecto

```
ObsidianRAG/
├── cerebro.py              # FastAPI server
├── app.py                  # Streamlit UI
├── config/
│   └── settings.py         # Configuración Pydantic
├── services/
│   ├── qa_agent.py         # LangGraph agent
│   ├── qa_service.py       # Retriever híbrido
│   ├── db_service.py       # ChromaDB + indexación
│   └── metadata_tracker.py # Detección de cambios
├── utils/
│   └── logger.py           # Configuración de logging
├── scripts/
│   ├── debug/              # Utilidades de debug
│   └── tests/              # Tests de integración
└── db/                     # Base de datos ChromaDB
```

## 🔮 Roadmap

- [ ] Selector de modelos en UI (qwen3, gemma3, deepseek)
- [ ] Integración de embeddinggemma desde Ollama
- [ ] Soporte para APIs externas (Google AI)
- [ ] Modo conversacional con memoria
- [ ] Dashboard de analytics

## 📄 Licencia

MIT License - ver [LICENSE](LICENSE)

## 🙏 Créditos

- [LangGraph](https://github.com/langchain-ai/langgraph) - Framework de agentes
- [Ollama](https://ollama.ai/) - LLMs locales
- [ChromaDB](https://www.trychroma.com/) - Base de datos vectorial
- [Streamlit](https://streamlit.io/) - Framework de UI
