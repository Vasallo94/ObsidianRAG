# ObsidianRAG 🧠

Sistema RAG (Retrieval-Augmented Generation) para consultar tus notas de Obsidian usando **LangGraph** y **LLMs locales** con Ollama. Pregunta en lenguaje natural y obtén respuestas basadas en tu conocimiento personal.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green)
![Ollama](https://img.shields.io/badge/Ollama-Local_LLMs-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

<p align="center">
  <img src="img/demo.gif" alt="Demo" width="600">
</p>

---

## 📋 Tabla de Contenidos

- [Características](#-características)
- [Requisitos Previos](#-requisitos-previos)
- [Instalación Rápida](#-instalación-rápida)
- [Configuración](#-configuración)
- [Uso](#-uso)
- [Arquitectura](#-arquitectura)
- [Modelos Disponibles](#-modelos-disponibles)
- [Solución de Problemas](#-solución-de-problemas)
- [Contribuir](#-contribuir)

---

## ✨ Características

### 🔍 Búsqueda Híbrida Avanzada
- **Vectorial + BM25**: Combina embeddings semánticos con búsqueda léxica
- **CrossEncoder Reranker**: BAAI/bge-reranker-v2-m3 para reordenar por relevancia
- **GraphRAG**: Expansión de contexto siguiendo enlaces `[[wikilinks]]` de Obsidian

### 🤖 Integración LLM
- **100% Local**: Todo corre en tu máquina, sin enviar datos a la nube
- **Múltiples modelos**: Selector en UI para cambiar entre gemma3, qwen2.5, qwen3, deepseek-r1
- **Fallback inteligente**: Si un modelo no está disponible, usa alternativas automáticamente

### 📊 Análisis y Métricas
- **Scores de relevancia**: Cada fuente muestra su score de reranker (0-100%)
- **Logging detallado**: Trazabilidad completa de cada consulta
- **Indexación incremental**: Solo procesa notas modificadas

---

## 📦 Requisitos Previos

### 1. Python 3.11+

```bash
# Verificar versión
python --version  # Debe ser 3.11 o superior
```

### 2. Ollama

Ollama es el motor de LLMs locales. Instálalo desde [ollama.ai](https://ollama.ai/):

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows
# Descarga desde https://ollama.com/download
```

Verifica que funcione:
```bash
ollama --version
```

### 3. UV (Gestor de paquetes recomendado)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# O con pip
pip install uv
```

---

## 🚀 Instalación Rápida

### Paso 1: Clonar el repositorio

```bash
git clone https://github.com/Vasallo94/ObsidianRAG.git
cd ObsidianRAG
```

### Paso 2: Instalar dependencias

```bash
uv sync
```

### Paso 3: Configurar variables de entorno

```bash
# Copiar plantilla
cp .env.example .env

# Editar con tu editor favorito
nano .env  # o code .env, vim .env, etc.
```

**Contenido mínimo de `.env`:**
```env
# OBLIGATORIO: Ruta a tu vault de Obsidian
OBSIDIAN_PATH=/Users/tu_usuario/Documents/ObsidianVault

# OPCIONAL: Modelo LLM (default: gemma3)
LLM_MODEL=gemma3
```

### Paso 4: Descargar modelos de Ollama

```bash
# Iniciar Ollama (si no está corriendo)
ollama serve &

# Descargar modelo LLM (elige uno)
ollama pull gemma3      # Recomendado, equilibrado
ollama pull qwen2.5     # Bueno para español
ollama pull qwen3       # Mejor razonamiento
ollama pull deepseek-r1 # Razonamiento avanzado

# OPCIONAL: Modelo de embeddings de Ollama
ollama pull embeddinggemma  # 622MB, multilingüe
```

> **Nota**: Si no descargas `embeddinggemma`, el sistema usará automáticamente HuggingFace embeddings (se descargan automáticamente la primera vez).

### Paso 5: Iniciar el servidor

```bash
uv run cerebro.py
```

Deberías ver:
```
INFO - ✅ Aplicación iniciada exitosamente
INFO - Uvicorn running on http://0.0.0.0:8000
```

### Paso 6: Abrir la interfaz web

```bash
# En otra terminal
uv run streamlit run app.py
```

Abre tu navegador en: **http://localhost:8501**

---

## ⚙️ Configuración

### Variables de Entorno Completas

Crea un archivo `.env` en la raíz del proyecto:

```env
# ============ OBLIGATORIO ============
OBSIDIAN_PATH=/ruta/a/tu/vault

# ============ MODELOS ============
# LLM (gemma3, qwen2.5, qwen3, deepseek-r1)
LLM_MODEL=gemma3

# Embeddings: 'ollama' o 'huggingface'
EMBEDDING_PROVIDER=ollama
OLLAMA_EMBEDDING_MODEL=embeddinggemma

# Si usas HuggingFace (fallback automático)
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2

# ============ RERANKER ============
USE_RERANKER=true
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RERANKER_TOP_N=6

# ============ RETRIEVAL ============
CHUNK_SIZE=1500
CHUNK_OVERLAP=300
RETRIEVAL_K=12
BM25_K=5
BM25_WEIGHT=0.4
VECTOR_WEIGHT=0.6

# ============ API ============
API_HOST=0.0.0.0
API_PORT=8000
```

### Archivo .env.example

El proyecto incluye un `.env.example` con todos los valores por defecto.

---

## 📖 Uso

### Interfaz Web (Recomendado)

1. Inicia el servidor: `uv run cerebro.py`
2. Inicia la UI: `uv run streamlit run app.py`
3. Abre http://localhost:8501
4. ¡Pregunta sobre tus notas!

**Características de la UI:**
- 🤖 Selector de modelo LLM en el sidebar
- 📚 Fuentes con scores de relevancia
- 🔄 Botón de reindexar base de datos
- 🗑️ Botón de limpiar chat

### API REST

```bash
# Hacer una pregunta
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"text": "¿Qué notas tengo sobre Python?", "model": "gemma3"}'

# Verificar estado
curl http://localhost:8000/health

# Obtener estadísticas
curl http://localhost:8000/stats

# Forzar reindexación
curl -X POST http://localhost:8000/rebuild_db
```

### Respuesta de la API

```json
{
  "question": "¿Qué notas tengo sobre Python?",
  "result": "Según tus notas, tienes documentación sobre...",
  "sources": [
    {
      "source": "Programación/Python Basics.md",
      "score": 0.92,
      "retrieval_type": "retrieved"
    },
    {
      "source": "Programación/Django Tutorial.md", 
      "score": 0.78,
      "retrieval_type": "graphrag_link"
    }
  ],
  "process_time": 2.5,
  "session_id": "abc123..."
}
```

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  ┌─────────────┐                                            │
│  │  Streamlit  │  ◄── Interfaz web interactiva              │
│  │    (UI)     │                                            │
│  └──────┬──────┘                                            │
└─────────┼───────────────────────────────────────────────────┘
          │ HTTP
          ▼
┌─────────────────────────────────────────────────────────────┐
│                        BACKEND                               │
│  ┌──────────────┐     ┌─────────────────────────────────┐   │
│  │   FastAPI    │────▶│         LangGraph Agent         │   │
│  │  (cerebro)   │     │  ┌─────────┐    ┌───────────┐   │   │
│  └──────────────┘     │  │Retrieve │───▶│ Generate  │   │   │
│                       │  │  Node   │    │   Node    │   │   │
│                       │  └────┬────┘    └─────┬─────┘   │   │
│                       └───────┼───────────────┼─────────┘   │
└───────────────────────────────┼───────────────┼─────────────┘
                                │               │
          ┌─────────────────────┘               └──────────────┐
          ▼                                                    ▼
┌──────────────────────┐                        ┌──────────────────────┐
│      RETRIEVAL       │                        │         LLM          │
│ ┌──────────────────┐ │                        │  ┌────────────────┐  │
│ │  EnsembleRetriever│ │                        │  │     Ollama     │  │
│ │ ┌──────┐ ┌─────┐ │ │                        │  │  (gemma3, etc) │  │
│ │ │Vector│ │BM25 │ │ │                        │  └────────────────┘  │
│ │ └──┬───┘ └──┬──┘ │ │                        └──────────────────────┘
│ │    └────┬───┘    │ │
│ │         ▼        │ │
│ │  ┌────────────┐  │ │
│ │  │  Reranker  │  │ │
│ │  └────────────┘  │ │
│ └──────────────────┘ │
│ ┌──────────────────┐ │
│ │    ChromaDB      │ │
│ │   (Vectores)     │ │
│ └──────────────────┘ │
└──────────────────────┘
```

### Flujo de Datos

1. **Usuario** hace pregunta → **Streamlit**
2. **Streamlit** → POST `/ask` → **FastAPI**
3. **FastAPI** → invoca → **LangGraph Agent**
4. **Retrieve Node**:
   - Búsqueda híbrida (Vector + BM25)
   - Reranking con CrossEncoder
   - Expansión GraphRAG (sigue [[links]])
5. **Generate Node**:
   - Construye prompt con contexto
   - Invoca LLM (Ollama)
6. **Respuesta** → FastAPI → Streamlit → Usuario

---

## 🤖 Modelos Disponibles

### LLMs (Ollama)

| Modelo | Tamaño | Descripción | Comando |
|--------|--------|-------------|---------|
| `gemma3` | 5GB | Equilibrado, bueno para todo | `ollama pull gemma3` |
| `qwen2.5` | 4.4GB | Excelente para español | `ollama pull qwen2.5` |
| `qwen3` | 5GB | Mejor razonamiento | `ollama pull qwen3` |
| `deepseek-r1` | 4.7GB | Razonamiento avanzado | `ollama pull deepseek-r1` |

### Embeddings

| Modelo | Provider | Tamaño | Descripción |
|--------|----------|--------|-------------|
| `embeddinggemma` | Ollama | 622MB | 100+ idiomas, rápido |
| `paraphrase-multilingual-mpnet` | HuggingFace | 420MB | Fallback automático |

> **Tip**: El sistema hace fallback automático a HuggingFace si el modelo de Ollama no está disponible.

---

## 🔧 Solución de Problemas

### ❌ "Ollama not available" / Connection refused

```bash
# 1. Verificar que Ollama está corriendo
ollama serve

# 2. Si usas macOS, puede estar como app
# Abre Ollama.app desde Aplicaciones

# 3. Verificar con
curl http://localhost:11434/api/tags
```

### ❌ "Model not found"

```bash
# Descargar el modelo que necesitas
ollama pull gemma3
ollama pull embeddinggemma  # Para embeddings
```

### ❌ "Collection does not exist" / DB corrupta

```bash
# Eliminar y reconstruir la base de datos
rm -rf db/
uv run cerebro.py
```

### ❌ Primera ejecución muy lenta

Es normal. La primera vez:
1. Descarga modelos de HuggingFace (reranker, embeddings)
2. Indexa todas tus notas de Obsidian
3. Crea la base de datos vectorial

Las siguientes ejecuciones son mucho más rápidas (indexación incremental).

### ❌ "No se encontraron resultados"

1. Verifica que `OBSIDIAN_PATH` apunta a tu vault
2. Asegúrate de tener archivos `.md` en el vault
3. Reindexar: `rm -rf db/ && uv run cerebro.py`

### ❌ Respuestas en inglés cuando pregunto en español

Prueba con `qwen2.5` que tiene mejor soporte para español:
```bash
ollama pull qwen2.5
# Luego selecciónalo en la UI
```

---

## 📂 Estructura del Proyecto

```
ObsidianRAG/
├── cerebro.py              # 🧠 Servidor FastAPI (punto de entrada)
├── app.py                  # 🖥️ Interfaz Streamlit
├── config/
│   └── settings.py         # ⚙️ Configuración Pydantic
├── services/
│   ├── qa_agent.py         # 🤖 Agente LangGraph (retrieve→generate)
│   ├── qa_service.py       # 🔍 Retriever híbrido + reranker
│   ├── db_service.py       # 💾 ChromaDB + indexación
│   └── metadata_tracker.py # 📊 Detección de cambios
├── utils/
│   └── logger.py           # 📝 Configuración de logging
├── scripts/
│   ├── debug/              # 🐛 Utilidades de debug
│   └── tests/              # 🧪 Tests de integración
├── assets/
│   └── styles.css          # 🎨 Estilos de la UI
├── db/                     # 💽 Base de datos ChromaDB (auto-generada)
├── logs/                   # 📋 Logs de ejecución
├── .env                    # 🔐 Variables de entorno (crear desde .env.example)
└── .env.example            # 📄 Plantilla de configuración
```

---

## 🔮 Roadmap

- [x] Selector de modelos en UI
- [x] Fallback automático de embeddings
- [x] Scores de relevancia en fuentes
- [ ] Modo conversacional con memoria persistente
- [ ] Dashboard de analytics
- [ ] Soporte para APIs externas (Google AI, OpenAI)
- [ ] Exportar conversaciones

---

## 🤝 Contribuir

¡Las contribuciones son bienvenidas!

1. Fork el repositorio
2. Crea una rama: `git checkout -b feature/nueva-caracteristica`
3. Commit: `git commit -m 'feat: añadir nueva característica'`
4. Push: `git push origin feature/nueva-caracteristica`
5. Abre un Pull Request

---

## 📄 Licencia

MIT License - ver [LICENSE](LICENSE)

---

## 🙏 Créditos

- [LangGraph](https://github.com/langchain-ai/langgraph) - Framework de agentes
- [Ollama](https://ollama.ai/) - LLMs locales
- [ChromaDB](https://www.trychroma.com/) - Base de datos vectorial
- [Streamlit](https://streamlit.io/) - Framework de UI
- [Obsidian](https://obsidian.md/) - Tu segundo cerebro

---

<p align="center">
  Hecho con ❤️ para la comunidad de Obsidian
</p>
