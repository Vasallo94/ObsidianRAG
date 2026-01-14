---
name: python-backend
description: >
  Usa esta skill para el desarrollo del backend en Python de ObsidianRAG,
  incluyendo FastAPI, estructura del proyecto, dependencias y logging.
tools: ['read', 'edit', 'run_command', 'grep_search']
---

# Python Backend Development

## Cuándo usar esta skill
- Cuando necesites modificar la API FastAPI (`backend/obsidianrag/api`).
- Cuando agregues nuevas dependencias o configures `pyproject.toml`.
- Cuando trabajes en la estructura core del paquete (`backend/obsidianrag`).

## Cómo usar esta skill

### 1. Estándares de Código
- **Version**: Python 3.11+
- **Linter/Formatter**: `ruff check` y `ruff format` (line length 88).
- **Type Hints**: Requeridos para todas las funciones públicas.
- **Docstrings**: Estilo Google.

### 2. Estructura del Proyecto
```text
backend/
├── obsidianrag/
│   ├── config.py           # Pydantic Settings
│   ├── api/                # FastAPI app
│   ├── core/               # RAG logic, DB service
│   └── utils/              # Logging, helpers
```

### 3. Patrones Clave

#### Configuración (Pydantic)
Usa `obsidianrag.config.settings` para acceder a la configuración global.
```python
from obsidianrag.config import settings

def my_func():
    db_path = settings.db_path
```

#### FastAPI Lifespan
La inicialización de recursos (DB, Agentes) ocurre en el `lifespan` en `api/server.py`.

#### Adding Dependencies
Usa `uv` para gestionar paquetes.
```bash
cd backend
uv add package-name
uv add --dev pytest-something
```

### 4. Antes de hacer Commit
Ejecuta siempre:
```bash
cd backend
uv run ruff format obsidianrag/ tests/
uv run ruff check obsidianrag/ tests/ --fix
uv run pytest tests/ -m "not slow"
```
