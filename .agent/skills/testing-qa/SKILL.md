---
name: testing-qa
description: >
  Usa esta skill para escribir y ejecutar tests (unitarios, integración, e2e)
  en el backend de ObsidianRAG usando pytest y mocks.
tools: ['read', 'edit', 'run_command']
---

# Testing & QA

## Cuándo usar esta skill
- Cuando escribas código nuevo y necesites verificarlo.
- Cuando reportes o arregles bugs.
- Para asegurar la calidad antes de una release.

## Cómo usar esta skill

### 1. Ejecutar Tests
```bash
cd backend
uv run pytest tests/ -v
# Solo integración
uv run pytest tests/ -m "integration"
```

### 2. Estructura de Tests
- `tests/conftest.py`: Fixtures compartidas (mock_vault, mock_settings).
- `tests/test_server.py`: Tests de API FastAPI.
- `tests/test_qa_agent.py`: Tests de lógica RAG (mockear LLM).

### 3. Guías de Mocking
- **Ollama/LLM**: SIEMPRE mockear en tests unitarios. Usa `mock_ollama` fixture.
- **ChromaDB**: Mockear para unitarios, usar instance real en `tmp_path` para integración.
- **File System**: Usa `tmp_path` fixture de pytest.

### 4. Cobertura
El objetivo es >80% en módulos core.
```bash
uv run pytest tests/ --cov=obsidianrag
```
