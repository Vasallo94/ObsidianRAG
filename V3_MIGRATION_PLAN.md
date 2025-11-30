# 🚀 ObsidianRAG v3 - Plan de Migración a Plugin de Obsidian

> **Documento de Planificación del Proyecto**  
> **Versión**: 1.0  
> **Fecha de inicio**: 29 de noviembre de 2025  
> **Autores**: Enrique Vasallo + GitHub Copilot  
> **Rama**: `v3-plugin`

---

## 📋 Tabla de Contenidos

1. [Resumen Ejecutivo](#-resumen-ejecutivo)
2. [Visión del Proyecto](#-visión-del-proyecto)
3. [Arquitectura Actual vs Nueva](#-arquitectura-actual-vs-nueva)
4. [Investigación Técnica](#-investigación-técnica)
5. [Estructura del Monorepo](#-estructura-del-monorepo)
6. [Plan de Migración por Fases](#-plan-de-migración-por-fases)
7. [Checklist Detallado del Proyecto](#-checklist-detallado-del-proyecto)
8. [Especificaciones Técnicas](#-especificaciones-técnicas)
9. [Testing y Calidad](#-testing-y-calidad)
10. [Consideraciones para el Usuario](#-consideraciones-para-el-usuario)
11. [Distribución y Publicación](#-distribución-y-publicación)
12. [Riesgos y Mitigaciones](#-riesgos-y-mitigaciones)
13. [Cronograma Estimado](#-cronograma-estimado)
14. [Notas y Decisiones](#-notas-y-decisiones)

---

## 🎯 Resumen Ejecutivo

### ¿Qué es ObsidianRAG v3?

ObsidianRAG v3 transforma el proyecto actual (una aplicación Python standalone con interfaz Streamlit) en un **plugin nativo de Obsidian** que cualquier usuario puede instalar directamente desde el Community Plugins Store.

### El Problema que Resolvemos

Actualmente, para usar ObsidianRAG los usuarios deben:
1. Clonar el repositorio
2. Instalar Python y dependencias manualmente
3. Configurar variables de entorno
4. Ejecutar scripts desde terminal
5. Abrir Streamlit en el navegador

Esto limita la adopción a usuarios técnicos.

### La Solución v3

Un plugin de Obsidian que:
1. Se instala con un clic desde Community Plugins
2. Gestiona automáticamente el backend Python
3. Proporciona una interfaz nativa dentro de Obsidian
4. Funciona "out of the box" para usuarios con Python y Ollama instalados

### Viabilidad Técnica

✅ **CONFIRMADO**: Los plugins de Obsidian pueden ejecutar procesos del sistema usando Node.js `child_process.spawn()`. El plugin [Shell Commands](https://github.com/Taitava/obsidian-shellcommands) (473 estrellas) demuestra esta capacidad.

---

## 🔭 Visión del Proyecto

### Objetivo Principal

> Convertir ObsidianRAG en el plugin RAG de referencia para Obsidian, permitiendo a cualquier usuario hacer preguntas sobre su vault usando LLMs locales.

### Principios Guía

1. **Local-first**: Todo corre en la máquina del usuario, sin enviar datos a la nube
2. **Simplicidad**: Instalación y uso lo más simple posible
3. **Robustez**: Manejo elegante de errores y estados
4. **Modularidad**: Backend y plugin como componentes independientes
5. **Mantenibilidad**: Código limpio, testeable y documentado

### Métricas de Éxito

- [ ] Plugin publicado en Obsidian Community Plugins
- [ ] Backend publicado en PyPI (`pip install obsidianrag`)
- [ ] Documentación completa para usuarios y desarrolladores
- [ ] >90% de cobertura de tests en componentes críticos
- [ ] Tiempo de setup para usuario nuevo < 5 minutos

---

## 🏗️ Arquitectura Actual vs Nueva

### Arquitectura Actual (v2)

```
┌─────────────────────────────────────────────────────────────┐
│                    APLICACIÓN MONOLÍTICA                     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Streamlit  │  │   FastAPI    │  │   LangGraph  │       │
│  │   (UI Web)   │  │   (API)      │  │   (RAG)      │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   ChromaDB   │  │  Reranker    │  │   Ollama     │       │
│  │   (Vectors)  │  │  (BAAI)      │  │   (LLM)      │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘

Usuario → Terminal → `uv run main.py` + `uv run streamlit run streamlit_app.py`
```

**Problemas**:
- Requiere conocimientos técnicos
- Dos procesos separados (API + Streamlit)
- No hay integración con Obsidian
- Configuración manual de paths

### Arquitectura Nueva (v3)

```
┌─────────────────────────────────────────────────────────────────┐
│                          OBSIDIAN                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              PLUGIN OBSIDIANRAG (TypeScript)               │  │
│  │                                                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │  │
│  │  │ ChatView    │  │ Settings    │  │ Server      │        │  │
│  │  │ (UI nativa) │  │ (Config)    │  │ Manager     │        │  │
│  │  └─────────────┘  └─────────────┘  └──────┬──────┘        │  │
│  │                                           │                │  │
│  │            requestUrl()                   │ child_process  │  │
│  │                 │                         │ .spawn()       │  │
│  └─────────────────┼─────────────────────────┼───────────────┘  │
└────────────────────┼─────────────────────────┼──────────────────┘
                     │                         │
                     │ HTTP :8000              │ Ejecuta
                     ▼                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                 BACKEND PYTHON (PyPI Package)                    │
│                                                                  │
│  $ obsidianrag serve --vault /path/to/vault --port 8000         │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   FastAPI    │  │   LangGraph  │  │   ChromaDB   │           │
│  │   (API)      │  │   (RAG)      │  │   (Vectors)  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │  Reranker    │  │  Embeddings  │                             │
│  │  (BAAI)      │  │  (HF/Ollama) │                             │
│  └──────────────┘  └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │      OLLAMA      │
                    │   (LLM Local)    │
                    └──────────────────┘
```

**Ventajas**:
- Instalación con un clic
- UI integrada en Obsidian
- Gestión automática del servidor
- Path del vault detectado automáticamente
- Un solo punto de entrada para el usuario

---

## 🔬 Investigación Técnica

### Plugins de Obsidian: Capacidades Clave

#### 1. Ejecución de Procesos del Sistema

Los plugins de Obsidian tienen acceso completo a Node.js, incluyendo `child_process`:

```typescript
// Esto es posible en un plugin de Obsidian
const { spawn } = require('child_process');

const serverProcess = spawn('obsidianrag', ['serve', '--vault', vaultPath], {
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe']
});
```

**Fuente**: [Obsidian API](https://github.com/obsidianmd/obsidian-api) - Los plugins pueden usar `require('fs')`, `require('electron')`, y cualquier módulo de Node.js cuando `isDesktopOnly: true`.

#### 2. Comunicación HTTP

Los plugins pueden hacer requests HTTP sin restricciones CORS:

```typescript
import { requestUrl } from 'obsidian';

const response = await requestUrl({
    url: 'http://localhost:8000/ask',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: question })
});
```

#### 3. Plugins de Referencia Estudiados

| Plugin | Relevancia | Lo que aprendimos |
|--------|------------|-------------------|
| [Shell Commands](https://github.com/Taitava/obsidian-shellcommands) | ⭐⭐⭐ | Ejecución de procesos con `child_process.spawn()` |
| [Obsidian Copilot](https://github.com/logancyang/obsidian-copilot) | ⭐⭐⭐ | Integración con Ollama via HTTP, UI de chat |
| [Smart Connections](https://github.com/brianpetro/obsidian-smart-connections) | ⭐⭐ | Embeddings locales con Transformers.js |
| [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) | ⭐⭐ | Servidor HTTP embebido en plugin |

#### 4. Publicación en Community Plugins

Requisitos para publicar:
- Repositorio GitHub público
- `manifest.json` con metadata correcta
- `main.js` compilado (no TypeScript)
- Licencia open source
- Pull Request a [obsidian-releases](https://github.com/obsidianmd/obsidian-releases)
- Validación automática + revisión humana

### Backend Python: Distribución

#### PyPI Package

El backend se distribuirá como paquete PyPI:

```bash
pip install obsidianrag
# o mejor
pipx install obsidianrag
```

#### Entry Points (CLI)

```toml
# pyproject.toml
[project.scripts]
obsidianrag = "obsidianrag.cli:main"
```

Comandos disponibles:
```bash
obsidianrag serve --vault /path --port 8000
obsidianrag index --vault /path --force
obsidianrag status
obsidianrag config --show
```

---

## 📁 Estructura del Monorepo

### Estructura Propuesta

```
obsidianrag/
│
├── 📁 backend/                          # Backend Python (PyPI)
│   ├── 📁 obsidianrag/                  # Paquete Python
│   │   ├── __init__.py                  # Versión y exports
│   │   ├── __main__.py                  # python -m obsidianrag
│   │   ├── cli.py                       # CLI con Typer/Click
│   │   ├── server.py                    # FastAPI app
│   │   │
│   │   ├── 📁 config/
│   │   │   ├── __init__.py
│   │   │   └── settings.py              # Pydantic Settings
│   │   │
│   │   ├── 📁 services/
│   │   │   ├── __init__.py
│   │   │   ├── db_service.py            # ChromaDB
│   │   │   ├── qa_agent.py              # LangGraph
│   │   │   ├── qa_service.py            # Retriever + Reranker
│   │   │   └── metadata_tracker.py      # File tracking
│   │   │
│   │   └── 📁 utils/
│   │       ├── __init__.py
│   │       └── logger.py
│   │
│   ├── 📁 tests/                        # Tests del backend
│   │   ├── __init__.py
│   │   ├── conftest.py                  # Fixtures pytest
│   │   ├── test_cli.py
│   │   ├── test_server.py
│   │   ├── test_qa_agent.py
│   │   └── test_integration.py
│   │
│   ├── pyproject.toml                   # Configuración del paquete
│   ├── README.md                        # Docs del backend
│   └── .env.example
│
├── 📁 plugin/                           # Plugin Obsidian (TypeScript)
│   ├── 📁 src/
│   │   ├── main.ts                      # Entry point del plugin
│   │   ├── settings.ts                  # Interfaz y defaults
│   │   │
│   │   ├── 📁 services/
│   │   │   ├── server-manager.ts        # Gestión proceso Python
│   │   │   ├── api-client.ts            # Cliente HTTP
│   │   │   └── health-checker.ts        # Verificación de estado
│   │   │
│   │   ├── 📁 ui/
│   │   │   ├── chat-view.ts             # Vista lateral de chat
│   │   │   ├── settings-tab.ts          # Pestaña de settings
│   │   │   ├── status-bar.ts            # Indicador de estado
│   │   │   └── modals/
│   │   │       ├── ask-modal.ts         # Modal para preguntas
│   │   │       ├── setup-modal.ts       # Modal de instalación
│   │   │       └── error-modal.ts       # Modal de errores
│   │   │
│   │   └── 📁 utils/
│   │       ├── platform.ts              # Detección de OS
│   │       └── constants.ts
│   │
│   ├── 📁 tests/                        # Tests del plugin
│   │   └── ...
│   │
│   ├── manifest.json                    # Metadata del plugin
│   ├── package.json
│   ├── tsconfig.json
│   ├── esbuild.config.mjs
│   ├── styles.css
│   └── README.md
│
├── 📁 docs/                             # Documentación
│   ├── 📁 user-guide/
│   │   ├── installation.md
│   │   ├── configuration.md
│   │   ├── usage.md
│   │   └── troubleshooting.md
│   │
│   ├── 📁 developer-guide/
│   │   ├── architecture.md
│   │   ├── contributing.md
│   │   └── api-reference.md
│   │
│   └── index.md
│
├── 📁 .github/
│   ├── 📁 workflows/
│   │   ├── test-backend.yml             # CI tests Python
│   │   ├── test-plugin.yml              # CI tests TypeScript
│   │   ├── release-backend.yml          # Publicar en PyPI
│   │   └── release-plugin.yml           # Build plugin
│   │
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
│
├── 📁 scripts/                          # Scripts de desarrollo
│   ├── dev-setup.sh                     # Setup entorno dev
│   └── build-all.sh                     # Build completo
│
├── .gitignore
├── LICENSE
├── README.md                            # README principal
├── CHANGELOG.md
└── V3_MIGRATION_PLAN.md                 # Este documento
```

### Mapeo de Archivos: Actual → Nuevo

| Archivo Actual | Destino | Notas |
|----------------|---------|-------|
| `main.py` | `backend/obsidianrag/server.py` | Refactorizar como módulo |
| `streamlit_app.py` | ❌ ELIMINAR | Reemplazado por plugin |
| `config/settings.py` | `backend/obsidianrag/config/settings.py` | Sin cambios mayores |
| `services/db_service.py` | `backend/obsidianrag/services/db_service.py` | Sin cambios |
| `services/qa_agent.py` | `backend/obsidianrag/services/qa_agent.py` | Sin cambios |
| `services/qa_service.py` | `backend/obsidianrag/services/qa_service.py` | Sin cambios |
| `services/metadata_tracker.py` | `backend/obsidianrag/services/metadata_tracker.py` | Sin cambios |
| `utils/logger.py` | `backend/obsidianrag/utils/logger.py` | Sin cambios |
| `assets/styles.css` | ❌ ELIMINAR | Era para Streamlit |
| `scripts/` | `backend/scripts/` o eliminar | Evaluar utilidad |
| `pyproject.toml` | `backend/pyproject.toml` | Actualizar significativamente |

---

## 📅 Plan de Migración por Fases

### Fase 0: Preparación ✅ COMPLETADA
> **Estado**: ✅ Completada  
> **Duración**: 29 de noviembre de 2025

- [x] Crear rama `v3-plugin`
- [x] Documentar plan de migración (este documento)
- [x] Revisar y aprobar plan
- [x] Crear issues en GitHub para tracking
  - Epic: #21
  - Phase 1: #20
  - Phase 2: #22
  - Phase 3: #23
  - Phase 4: #24
  - Phase 5: #25
  - Phase 6: #26
  - Phase 7: #27
  - Phase 8: #28

### Fase 1: Reestructuración del Backend
> **Estado**: ✅ Completada  
> **Completada**: 14 de enero de 2025  
> **Issue**: #20 (cerrado)

**Objetivo**: Convertir el código actual en un paquete Python instalable con CLI.

#### 1.1 Reorganización de Archivos
- [x] Crear estructura `backend/obsidianrag/`
- [x] Mover archivos según mapeo
- [x] Actualizar todos los imports
- [x] Verificar que todo funciona

#### 1.2 Eliminar Streamlit
- [x] Eliminar `streamlit_app.py`
- [x] Eliminar `assets/styles.css`
- [x] Eliminar dependencia de `streamlit` en `pyproject.toml`
- [x] Eliminar cualquier código relacionado con Streamlit

#### 1.3 Crear CLI
- [x] Instalar Typer o Click como dependencia
- [x] Crear `cli.py` con comandos:
  - [x] `obsidianrag serve [--vault PATH] [--port PORT] [--host HOST]`
  - [x] `obsidianrag index [--vault PATH] [--force]`
  - [x] `obsidianrag status`
  - [x] `obsidianrag config [--show] [--set KEY VALUE]`
- [x] Crear `__main__.py` para `python -m obsidianrag`
- [x] Agregar entry points en `pyproject.toml`
- [x] **🆕 Añadir `--model` arg** para especificar modelo LLM
- [x] **🆕 Añadir `--reranker/--no-reranker` flag** para activar/desactivar reranker

#### 1.4 Mejorar Configuración
- [x] Hacer que `--vault` sea obligatorio si no hay `.env`
- [ ] Soportar archivo de configuración `~/.config/obsidianrag/config.toml` *(diferido)*
- [x] Mejorar mensajes de error cuando falta configuración
- [ ] Agregar comando `obsidianrag init` para setup interactivo *(diferido)*

#### 1.5 Actualizar pyproject.toml
- [x] Actualizar metadata del proyecto
- [x] Configurar entry points
- [x] Definir extras opcionales (`[dev]`, `[test]`)
- [x] Configurar build backend (hatchling)

### Fase 2: Testing del Backend
> **Estado**: ✅ Completada  
> **Completada**: 14 de enero de 2025  
> **Issue**: #22 (cerrado)

**Objetivo**: Asegurar calidad y robustez del backend antes de continuar.

#### 2.1 Setup de Testing
- [x] Configurar pytest
- [x] Crear fixtures en `conftest.py`
- [x] Configurar pytest-cov para cobertura
- [x] Crear vault de prueba con notas mock

#### 2.2 Tests Unitarios
- [x] Tests para `cli.py`
  - [x] Test de cada comando (14 tests)
  - [x] Test de argumentos inválidos
  - [x] Test de configuración faltante
- [x] Tests para `server.py`
  - [x] Test de endpoints (14 tests)
  - [x] Test de error handling
- [x] Tests para `qa_agent.py`
  - [x] Test del grafo LangGraph (17 tests)
  - [x] Test de nodos individuales
- [x] Tests para `qa_service.py`
  - [x] Test del retriever híbrido *(cubierto en qa_agent)*
  - [x] Test del reranker *(cubierto en qa_agent)*
- [x] Tests para `db_service.py`
  - [x] Test de creación de DB (16 tests)
  - [x] Test de indexación incremental

#### 2.3 Tests de Integración
- [x] Test E2E: iniciar servidor → hacer pregunta → verificar respuesta (test_integration.py)
- [x] Test de indexación completa de un vault
- [x] Test de reinicio del servidor
- [x] Test de manejo de errores (Ollama no disponible, etc.)

#### 2.4 CI/CD para Backend
- [x] Crear `.github/workflows/test-backend.yml`
- [x] Ejecutar tests en push/PR
- [x] Reportar cobertura
- [x] Lint con ruff (284 errores corregidos)

### Fase 3: Publicación del Backend en PyPI
> **Estado**: ✅ Completada  
> **Completada**: 29 de noviembre de 2025

**Objetivo**: Hacer el backend instalable via `pip install obsidianrag`.

#### 3.1 Preparación
- [x] Verificar que el nombre `obsidianrag` está disponible en PyPI
- [x] Crear cuenta en PyPI (si no existe)
- [x] Crear cuenta en TestPyPI para pruebas
- [x] Configurar tokens de autenticación

#### 3.2 Build y Test Local
- [x] `pip install build`
- [x] `python -m build`
- [x] Instalar localmente y probar
- [x] Verificar que CLI funciona después de `pip install`

#### 3.3 Publicación
- [x] Publicar en TestPyPI primero
- [x] Instalar desde TestPyPI y probar
- [x] Publicar en PyPI
- [x] Verificar instalación desde PyPI

#### 3.4 GitHub Actions para Releases
- [ ] Crear `.github/workflows/release-backend.yml` *(Pendiente CI/CD)*
- [ ] Trigger en tags `backend-v*`
- [ ] Build y publicación automática

### Fase 4: Desarrollo del Plugin de Obsidian
> **Estado**: ✅ Completada  
> **Completada**: 30 de noviembre de 2025  
> **Issue**: #24 (cerrado)

**Objetivo**: Crear el plugin TypeScript que gestiona el backend y proporciona UI.

#### 4.1 Setup del Proyecto
- [x] Crear estructura `plugin/`
- [x] Inicializar con template propio (no sample plugin)
- [x] Configurar TypeScript, esbuild
- [x] Configurar `manifest.json`

#### 4.2 Server Manager
- [x] Implementar servidor externo vía wrapper script `/usr/local/bin/obsidianrag-server`
  - [x] Detección del path del vault
  - [x] Configuración de puerto
  - [x] Start/Stop desde terminal
- [x] Spawn automático desde plugin (child_process)
- [x] Restart automático si el proceso muere (con exponential backoff)
- [x] Soporte multi-plataforma (Windows, macOS, Linux)
- [x] **🆕 Stop mejorado** - Mata proceso por puerto (`lsof -ti:PORT | xargs kill`)
- [x] **🆕 CLI args pasados correctamente** (`--model`, `--reranker/--no-reranker`)

#### 4.3 API Client
- [x] Implementar cliente HTTP integrado en `main.ts`
  - [x] Método `health(): Promise<boolean>` 
  - [x] **SSE Streaming** via `fetch()` para `/ask/stream`
  - [x] Método `stats(): Promise<VaultStats>`
  - [x] Método `reindexVault(): Promise<void>`
  - [x] Timeout handling (30s stream timeout)
  - [x] Retry logic (3 attempts con exponential backoff)

#### 4.4 Health Checker
- [x] Implementar health check integrado
  - [x] Polling periódico cada 5-10 segundos (`setInterval`)
  - [x] Eventos para cambio de estado (Online/Offline)
  - [x] Status bar item actualizado dinámicamente

#### 4.5 UI: Chat View
- [x] Implementar `ChatView` (vista lateral derecha)
  - [x] Input de texto para preguntas (textarea + botón)
  - [x] Historial de mensajes (user/assistant)
  - [x] Mostrar fuentes/referencias con links clickeables
  - [x] Indicador de loading (con spinner animado)
  - [x] Manejo de errores en UI
  - [x] Scroll automático al nuevo contenido
  - [x] Markdown rendering con `MarkdownRenderer.render()`
  - [x] **🆕 Streaming en tiempo real** (tokens aparecen progresivamente)
  - [x] **🆕 Indicador de fases** del grafo RAG (retrieve, rerank, generate)
  - [x] **🆕 TTFT badge** (Time To First Token)
  - [x] **🆕 Verificación de existencia de fuentes** (oculta no encontradas)
  - [x] **🆕 Botón para limpiar historial**

#### 4.6 UI: Settings Tab
- [x] Implementar `SettingsTab`
  - [x] Configuración del modelo LLM desde UI (dropdown **dinámico desde Ollama**)
  - [x] Configuración del puerto del servidor
  - [x] Toggle para auto-start del servidor
  - [x] Botón para reindexar vault
  - [x] Mostrar estado del servidor (indicador visual live, **auto-refresh cada 3s**)
  - [x] Mostrar estadísticas del vault (tabla con métricas)
  - [x] Toggle para usar/deshabilitar reranker
  - [x] Reset Setup Wizard
  - [x] **🆕 Reset to Defaults** - Restaurar todas las configuraciones
  - [x] **🆕 Modelos dinámicos desde Ollama** - Solo muestra modelos instalados

#### 4.7 UI: Status Bar
- [x] Implementar status bar item (separado)
  - [x] Indicador visual del estado: "🤖 RAG ●" / "🤖 RAG ○"
  - [x] Actualización en tiempo real (cada 10s)
  - [x] Click para abrir chat (online) o iniciar server (offline)

#### 4.8 UI: Modals
- [x] Setup Modal - Guía de primera instalación (3 pasos, **modelos dinámicos**)
- [x] Ask Modal - Modal rápido para preguntas (Cmd+P)
- [x] Error Modal - Errores amigables con sugerencias

#### 4.9 Commands
- [x] `ObsidianRAG: Open Chat` - Abre la vista de chat
- [x] `ObsidianRAG: Ask a question` (modal)
- [x] `ObsidianRAG: Reindex vault`
- [x] `ObsidianRAG: Start server`
- [x] `ObsidianRAG: Stop server`
- [x] `ObsidianRAG: Check server status`

#### 4.10 Ribbon Icon
- [x] Agregar icono en el ribbon (barra lateral izquierda)
- [x] Click para abrir chat view

#### 4.11 🆕 Streaming Backend (No planificado originalmente)
> Implementación completa de streaming SSE para mejorar UX

- [x] **Endpoint `/ask/stream`** - Server-Sent Events
- [x] **TRUE async streaming** con `httpx.AsyncClient` (no buffered)
- [x] **Eventos SSE**:
  - [x] `phase` - Fase actual del grafo (retrieve, rerank, generate)
  - [x] `retrieval_info` - Estadísticas de retrieval
  - [x] `context_info` - Info del contexto enviado al LLM
  - [x] `ttft` - Time To First Token
  - [x] `token` - Tokens individuales del LLM
  - [x] `sources` - Fuentes citadas
  - [x] `done` - Fin del stream
  - [x] `error` - Errores
- [x] **Score filtering** - Filtrado de documentos con score < 0.3
- [x] **Logging detallado** con timestamps (HH:MM:SS.mmm)

#### 4.12 🆕 Source Links Enhancement (No planificado originalmente)
- [x] Links a notas funcionan correctamente (rutas relativas)
- [x] Verificación de existencia de archivos antes de mostrar
- [x] Búsqueda fallback por nombre de archivo
- [x] Ocultar fuentes que no existen en el vault

#### 4.13 🆕 Ollama Integration (No planificado originalmente)
- [x] **Fetch de modelos disponibles** desde API de Ollama (`/api/tags`)
- [x] **Dropdown dinámico** solo muestra modelos instalados por el usuario
- [x] **Fallback a text input** si Ollama no está corriendo
- [x] **Auto-switch de modelo** si el seleccionado ya no existe

### Fase 5: Testing del Plugin
> **Estado**: 🔄 En progreso  
> **Duración estimada**: 2-3 días

#### 5.1 Tests Manuales
- [x] Test en macOS ✅
- [ ] Test en Windows
- [ ] Test en Linux
- [x] Test de instalación limpia (symlink a vault)
- [ ] Test de upgrade
- [ ] Test de desinstalación

#### 5.2 Edge Cases
- [ ] Python no instalado
- [ ] pip no disponible
- [x] Ollama no corriendo → Muestra error apropiado
- [ ] Puerto ocupado
- [ ] Vault vacío
- [ ] Vault muy grande (>1000 notas)
- [x] Conexión a servidor perdida → Status se actualiza a Offline
- [ ] Múltiples instancias de Obsidian

#### 5.3 CI/CD para Plugin
- [x] Crear `.github/workflows/test-plugin.yml` *(diferido - no crítico)*
- [x] Lint TypeScript *(eslint configurado)*
- [x] Build verification (esbuild funciona)
- [x] **Unit Tests con Jest**
  - [x] Setup Jest + ts-jest
  - [x] Mock de Obsidian API
  - [x] Tests de API/HTTP (14 tests)
  - [x] Tests de parsing de paths/sources (11 tests)
  - [x] Tests de settings (3 tests)
  - [x] **28/28 tests passing** ✅
  - [ ] E2E tests con Obsidian real *(diferido - requiere setup complejo)*

### Fase 6: Documentación
> **Estado**: ⏳ Pendiente  
> **Duración estimada**: 2-3 días

#### 6.1 Documentación de Usuario
- [ ] `docs/user-guide/installation.md`
  - [ ] Prerequisitos
  - [ ] Instalación del plugin
  - [ ] Primera configuración
- [ ] `docs/user-guide/usage.md`
  - [ ] Cómo hacer preguntas
  - [ ] Interpretar respuestas
  - [ ] Usar el chat view
- [ ] `docs/user-guide/configuration.md`
  - [ ] Todas las opciones de settings
  - [ ] Modelos disponibles
- [ ] `docs/user-guide/troubleshooting.md`
  - [ ] Problemas comunes
  - [ ] FAQs

#### 6.2 Documentación de Desarrollador
- [ ] `docs/developer-guide/architecture.md`
- [ ] `docs/developer-guide/contributing.md`
- [ ] `docs/developer-guide/api-reference.md`

#### 6.3 README Principal
- [ ] Actualizar `README.md` principal
- [ ] Badges actualizados
- [ ] GIFs/screenshots del plugin
- [ ] Quick start guide

### Fase 7: Publicación del Plugin
> **Estado**: ⏳ Pendiente  
> **Duración estimada**: 3-5 días (incluye tiempo de review)

#### 7.1 Preparación
- [ ] Verificar que el nombre `obsidianrag` está disponible
- [ ] Revisar [Plugin Guidelines](https://docs.obsidian.md/Plugins/Releasing/Plugin+guidelines)
- [ ] Revisar [Developer Policies](https://docs.obsidian.md/Developer+policies)

#### 7.2 Release
- [ ] Crear release en GitHub con:
  - [ ] `main.js`
  - [ ] `manifest.json`
  - [ ] `styles.css`
- [ ] Tag con versión semántica

#### 7.3 Publicación en Community Plugins
- [ ] Fork de `obsidianmd/obsidian-releases`
- [ ] Agregar entrada en `community-plugins.json`
- [ ] Crear Pull Request
- [ ] Responder a feedback de revisores
- [ ] Esperar aprobación

#### 7.4 GitHub Actions para Plugin Releases
- [ ] Crear `.github/workflows/release-plugin.yml`
- [ ] Trigger en tags `plugin-v*`
- [ ] Build automático
- [ ] Crear GitHub Release con assets

### Fase 8: Post-Lanzamiento
> **Estado**: ⏳ Pendiente  
> **Duración estimada**: Continuo

- [ ] Monitorear issues de usuarios
- [ ] Preparar hotfixes si es necesario
- [ ] Anunciar en:
  - [ ] Obsidian Discord
  - [ ] Obsidian Forum
  - [ ] r/ObsidianMD
  - [ ] Twitter/X
- [ ] Recopilar feedback
- [ ] Planificar v3.1

---

## ✅ Checklist Detallado del Proyecto

### Backend Python

#### Estructura y Organización
- [x] Crear directorio `backend/`
- [x] Crear directorio `backend/obsidianrag/`
- [x] Crear `backend/obsidianrag/__init__.py`
- [x] Crear `backend/obsidianrag/__main__.py`
- [x] Mover `config/` a `backend/obsidianrag/config/`
- [x] Mover `services/` a `backend/obsidianrag/core/`
- [x] Mover `utils/` a `backend/obsidianrag/utils/`
- [x] Actualizar imports en todos los archivos

#### CLI
- [x] Instalar Typer: `uv add typer[all]`
- [x] Crear `backend/obsidianrag/cli/main.py`
- [x] Implementar comando `serve`
- [x] Implementar comando `index`
- [x] Implementar comando `status`
- [x] Implementar comando `ask`
- [x] Agregar `--help` descriptivo a cada comando
- [x] Agregar colores y formato bonito (rich)

#### Configuración del Paquete
- [x] Actualizar `backend/pyproject.toml`
- [x] Verificar build: `uv build`
- [x] Verificar instalación local: `uv pip install -e .`

#### Limpieza
- [x] Eliminar `streamlit_app.py` *(mantener como legacy por ahora)*
- [x] Eliminar `assets/styles.css` *(mantener como legacy por ahora)*
- [x] Eliminar dependencia `streamlit` de pyproject.toml *(en backend/)*
- [x] Eliminar scripts obsoletos

#### Tests
- [x] Configurar pytest en `backend/pyproject.toml`
- [x] Crear `backend/tests/conftest.py`
- [x] Crear `backend/tests/test_cli.py` (14 tests)
- [x] Crear `backend/tests/test_server.py` (14 tests)
- [x] Crear `backend/tests/test_qa_agent.py` (17 tests)
- [x] Crear `backend/tests/test_db_service.py` (16 tests)
- [x] Crear `backend/tests/test_integration.py` (18 tests)
- [ ] Alcanzar >80% de cobertura *(actualmente 33%)*

### Plugin Obsidian

#### Setup
- [x] Crear directorio `plugin/`
- [x] Inicializar proyecto desde cero
- [x] Configurar `manifest.json`
- [x] Configurar `package.json`
- [x] Configurar `tsconfig.json`
- [x] Configurar `esbuild.config.mjs`
- [x] Verificar build: `node esbuild.config.mjs production`

#### Core
- [x] Implementar clase principal `ObsidianRAGPlugin`
- [x] Implementar `onload()`
- [x] Implementar `onunload()`
- [x] Implementar `loadSettings()`
- [x] Implementar `saveSettings()`

#### Server Manager
- [ ] Detectar si Python está instalado *(diferido)*
- [ ] Detectar si obsidianrag está instalado *(diferido)*
- [ ] Instalar obsidianrag si es necesario *(diferido)*
- [ ] Iniciar servidor con spawn *(usando wrapper script)*
- [ ] Manejar logs del servidor *(diferido)*
- [ ] Detener servidor limpiamente *(diferido)*
- [ ] Reiniciar servidor si falla *(diferido)*
- [ ] Soporte Windows *(pendiente testing)*
- [x] Soporte macOS ✅
- [ ] Soporte Linux *(pendiente testing)*

#### API Client
- [x] Implementar health check
- [x] Implementar ask con SSE streaming
- [ ] Implementar stats *(diferido)*
- [ ] Implementar reindex *(diferido)*
- [x] Manejo de errores
- [x] Timeouts (30s para streaming)
- [ ] Retries *(diferido)*

#### UI
- [x] Chat View (ItemView) ✅
- [x] Settings Tab (PluginSettingTab) ✅
- [x] Status Bar Item ✅
- [ ] Setup Modal *(diferido v3.1)*
- [ ] Error Modal *(diferido v3.1)*
- [ ] Quick Ask Modal *(diferido v3.1)*

#### Commands
- [x] `ObsidianRAG: Open Chat`
- [ ] Otros comandos *(diferidos)*

#### Estilos
- [x] Crear `styles.css`
- [x] Estilos para chat view
- [x] Estilos responsive
- [x] Soporte para temas claro/oscuro (usa variables CSS de Obsidian)

#### 🆕 Streaming Features (Implementación adicional)
- [x] SSE event handling en frontend
- [x] TRUE async streaming con httpx en backend
- [x] Mostrar fases del grafo RAG
- [x] TTFT (Time To First Token) badge
- [x] Token-by-token rendering
- [x] Score filtering (MIN_SCORE = 0.3)
- [x] Logging con timestamps detallado

### Documentación

- [x] Actualizar README principal *(badge tests, aviso v3)*
- [ ] Crear docs/user-guide/installation.md
- [ ] Crear docs/user-guide/usage.md
- [ ] Crear docs/user-guide/troubleshooting.md
- [ ] Crear docs/developer-guide/architecture.md
- [ ] Crear docs/developer-guide/contributing.md
- [ ] Agregar screenshots/GIFs

### CI/CD

- [x] `.github/workflows/test-backend.yml`
- [ ] `.github/workflows/test-plugin.yml`
- [ ] `.github/workflows/release-backend.yml`
- [ ] `.github/workflows/release-plugin.yml`

### Publicación

#### PyPI
- [ ] Cuenta en PyPI
- [ ] Cuenta en TestPyPI
- [ ] Tokens configurados
- [ ] Primera publicación
- [ ] Verificar `pip install obsidianrag`

#### Obsidian Community Plugins
- [ ] Cumplir todas las guidelines
- [ ] Crear release en GitHub
- [ ] PR a obsidian-releases
- [ ] Responder a review
- [ ] Publicación aprobada

---

## 🔧 Especificaciones Técnicas

### Backend: API Endpoints

| Endpoint | Método | Descripción | Request | Response |
|----------|--------|-------------|---------|----------|
| `/health` | GET | Health check | - | `{ status: "ok", model: "...", version: "..." }` |
| `/ask` | POST | Hacer pregunta (sync) | `{ text: string }` | `{ result: string, sources: Source[], ... }` |
| `/ask/stream` | POST | 🆕 Hacer pregunta (SSE streaming) | `{ text: string }` | SSE events (ver abajo) |
| `/stats` | GET | Estadísticas del vault | - | `{ notes: number, chunks: number, ... }` |
| `/rebuild_db` | POST | Reindexar vault | - | `{ status: "ok", indexed: number }` |

#### 🆕 SSE Events del endpoint `/ask/stream`

| Event Type | Data | Descripción |
|------------|------|-------------|
| `phase` | `{ phase: string, message: string }` | Fase actual: retrieve, rerank, generate |
| `retrieval_info` | `{ total_found: int, after_filter: int }` | Docs encontrados vs filtrados |
| `context_info` | `{ num_docs: int, total_chars: int }` | Tamaño del contexto |
| `ttft` | `{ ttft: float }` | Time To First Token en segundos |
| `token` | `{ token: string }` | Token individual del LLM |
| `sources` | `{ sources: [...] }` | Array de fuentes citadas |
| `done` | `{ done: true }` | Fin del stream |
| `error` | `{ error: string }` | Error durante procesamiento |

### Backend: CLI Commands

```bash
# Iniciar servidor
obsidianrag serve --vault /path/to/vault --port 8000 --host 0.0.0.0

# Indexar vault
obsidianrag index --vault /path/to/vault --force

# Ver estado
obsidianrag status

# Ver/modificar configuración
obsidianrag config --show
obsidianrag config --set llm_model gemma3
```

### Plugin: Settings Interface

```typescript
interface ObsidianRAGSettings {
    // Server
    autoStartServer: boolean;
    serverPort: number;
    
    // Model
    llmModel: string;
    embeddingProvider: 'huggingface' | 'ollama';
    
    // Retrieval
    useReranker: boolean;
    rerankerTopN: number;
    
    // UI
    showStatusBar: boolean;
    chatViewPosition: 'left' | 'right';
}
```

### Plugin: Comunicación con Backend

```typescript
// Ejemplo de flujo
async function askQuestion(question: string): Promise<Answer> {
    // 1. Verificar que el servidor está corriendo
    if (!await this.healthChecker.isHealthy()) {
        await this.serverManager.start();
        await this.waitForServer();
    }
    
    // 2. Hacer la pregunta
    const response = await this.apiClient.ask(question);
    
    // 3. Procesar respuesta
    return {
        answer: response.result,
        sources: response.sources.map(s => ({
            file: s.source,
            score: s.score
        }))
    };
}
```

---

## 🧪 Testing y Calidad

### Estrategia de Testing

#### Backend (Python)

| Tipo | Herramienta | Cobertura Objetivo |
|------|-------------|-------------------|
| Unit Tests | pytest | >80% |
| Integration Tests | pytest + httpx | Endpoints críticos |
| E2E Tests | pytest | Flujo completo |

#### Plugin (TypeScript)

| Tipo | Herramienta | Cobertura Objetivo |
|------|-------------|-------------------|
| Manual Testing | - | Todas las plataformas |
| Build Verification | esbuild | Sin errores |

### Escenarios de Test Críticos

#### Backend
1. **Servidor inicia correctamente**
2. **Endpoint /ask responde con respuesta válida**
3. **Reranker mejora relevancia de resultados**
4. **Indexación incremental funciona**
5. **Manejo de Ollama no disponible**

#### Plugin
1. **Instalación en vault vacío**
2. **Servidor se inicia automáticamente**
3. **Chat view muestra respuestas**
4. **Settings se guardan correctamente**
5. **Servidor se detiene al desactivar plugin**
6. **Funciona en Windows, macOS, Linux**

### Linting y Formato

#### Python
```toml
# pyproject.toml
[tool.ruff]
line-length = 88
select = ["E", "F", "I", "N", "W"]

[tool.black]
line-length = 88
```

#### TypeScript
```json
// .eslintrc
{
  "extends": ["eslint:recommended", "plugin:@typescript-eslint/recommended"]
}
```

---

## 👤 Consideraciones para el Usuario

### Prerequisitos del Usuario

| Requisito | Obligatorio | Notas |
|-----------|-------------|-------|
| Python 3.11+ | ✅ Sí | Necesario para el backend |
| pip/pipx | ✅ Sí | Para instalar el backend |
| Ollama | ✅ Sí | Para el LLM local |
| Modelo LLM | ✅ Sí | `ollama pull gemma3` o similar |
| 8GB RAM | ⚠️ Recomendado | Para embeddings y LLM |
| GPU | ❌ Opcional | Acelera inferencia |

### Flujo de Primera Instalación

```
Usuario instala plugin desde Community Plugins
              │
              ▼
    Plugin detecta prerequisitos
              │
    ┌─────────┴─────────┐
    │                   │
    ▼                   ▼
Python OK?          Python NO
    │                   │
    ▼                   ▼
Backend instalado?  Modal: "Instala Python"
    │                   │
    ▼                   │
  Sí/No                 │
    │                   │
    ▼                   │
Instalar/Iniciar    ◄───┘
    │
    ▼
Ollama corriendo?
    │
    ▼
Modelo descargado?
    │
    ▼
✅ Listo para usar
```

### Mensajes de Error Amigables

| Error | Mensaje al Usuario | Sugerencia |
|-------|-------------------|------------|
| Python no encontrado | "Python 3.11+ no detectado" | "Instala Python desde python.org" |
| Ollama no corriendo | "No se puede conectar a Ollama" | "Ejecuta 'ollama serve' en terminal" |
| Modelo no existe | "Modelo 'x' no encontrado" | "Ejecuta 'ollama pull x'" |
| Puerto ocupado | "Puerto 8000 en uso" | "Cambia el puerto en settings" |
| Sin notas | "Vault vacío" | "Añade notas markdown a tu vault" |

### Accesibilidad

- [ ] Soporte para screen readers
- [ ] Atajos de teclado para todas las acciones
- [ ] Contraste adecuado en UI
- [ ] Mensajes claros y concisos

---

## 📦 Distribución y Publicación

### PyPI (Backend)

**URL esperada**: `https://pypi.org/project/obsidianrag/`

**Instalación**:
```bash
pip install obsidianrag
# o
pipx install obsidianrag
```

**Release Process**:
1. Actualizar versión en `pyproject.toml`
2. Crear tag `backend-v3.0.0`
3. GitHub Action publica automáticamente

### Obsidian Community Plugins

**Entrada en community-plugins.json**:
```json
{
    "id": "obsidianrag",
    "name": "ObsidianRAG",
    "author": "Enrique Vasallo",
    "description": "RAG system for querying your notes using local LLMs with Ollama",
    "repo": "Vasallo94/ObsidianRAG"
}
```

**Release Process**:
1. Actualizar versión en `manifest.json`
2. Crear tag `plugin-v1.0.0`
3. GitHub Action crea release con assets
4. (Primera vez) PR a obsidian-releases

---

## ⚠️ Riesgos y Mitigaciones

### Riesgos Técnicos

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| child_process no funciona en algún OS | Baja | Alto | Testing extensivo en todas las plataformas |
| Instalación de pip falla | Media | Alto | Proveer instrucciones manuales, detectar pipx |
| Puerto siempre ocupado | Baja | Medio | Permitir configurar puerto, retry con puertos alternativos |
| Proceso zombie | Media | Medio | Cleanup agresivo en onunload, PID tracking |
| Ollama cambia API | Baja | Alto | Abstraer integración, versioning |

### Riesgos de Usuario

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Usuario no tiene Python | Alta | Alto | Modal claro con instrucciones |
| Usuario no sabe usar terminal | Media | Medio | Automatizar todo lo posible |
| Vault muy grande | Media | Medio | Indexación incremental, progress bar |
| Errores crípticos | Media | Alto | Mensajes de error amigables |

### Riesgos de Proyecto

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Scope creep | Alta | Alto | Mantener MVP, iterar |
| Rechazo en Community Plugins | Baja | Alto | Seguir guidelines al pie de la letra |
| Dependencias deprecadas | Baja | Medio | Mantenimiento activo |

---

## 📆 Cronograma Estimado

### Timeline Visual

```
Semana 1 (Dic 1-7)
├── Fase 0: Preparación ✓
└── Fase 1: Reestructuración Backend
    ├── Reorganización archivos
    ├── Eliminar Streamlit
    └── Crear CLI

Semana 2 (Dic 8-14)
├── Fase 1: Completar CLI
├── Fase 2: Testing Backend
│   ├── Setup pytest
│   └── Tests unitarios
└── Fase 3: PyPI (inicio)

Semana 3 (Dic 15-21)
├── Fase 3: Publicar en PyPI
└── Fase 4: Plugin (inicio)
    ├── Setup proyecto
    ├── Server Manager
    └── API Client

Semana 4 (Dic 22-28)
└── Fase 4: Plugin (continuación)
    ├── Chat View
    ├── Settings Tab
    └── Modals

Semana 5 (Dic 29 - Ene 4)
├── Fase 4: Plugin (finalizar)
├── Fase 5: Testing Plugin
└── Fase 6: Documentación

Semana 6 (Ene 5-11)
├── Fase 6: Documentación (completar)
└── Fase 7: Publicación
    ├── Release GitHub
    └── PR a obsidian-releases

Semana 7+ 
└── Fase 8: Post-lanzamiento
    ├── Monitorear issues
    └── Iterar
```

### Hitos Clave

| Hito | Fecha Objetivo | Criterio de Éxito |
|------|----------------|-------------------|
| Backend reestructurado | Semana 1 | CLI funciona, tests pasan |
| Backend en PyPI | Semana 3 | `pip install obsidianrag` funciona |
| Plugin MVP funcional | Semana 4 | Preguntas funcionan desde Obsidian |
| Plugin publicado | Semana 6-7 | Disponible en Community Plugins |

---

## 📝 Notas y Decisiones

### Decisiones de Diseño

| Decisión | Opción Elegida | Alternativas Consideradas | Razón |
|----------|----------------|---------------------------|-------|
| Estructura | Monorepo | Repos separados | Más fácil de mantener, releases coordinados |
| CLI Framework | Typer | Click, argparse | Mejor DX, auto-completado, colores |
| Plugin UI | ItemView lateral | Modal only | Mejor UX para conversaciones |
| Comunicación | HTTP localhost | WebSocket | Más simple, suficiente para request/response |
| Instalación backend | pip install | Bundled binary | Más simple, aprovecha Python del usuario |
| **🆕 Streaming** | SSE (Server-Sent Events) | WebSocket, Long polling | Simple, unidireccional, compatible con fetch |
| **🆕 Async HTTP** | httpx.AsyncClient | aiohttp, OllamaLLM.stream() | TRUE async, no bloquea event loop |
| **🆕 Token rendering** | Append incremental | Rerender full | Mejor performance, no re-parses markdown |

### 🆕 Lecciones Aprendidas (Fase 4)

| Problema | Solución | Impacto |
|----------|----------|---------|
| `OllamaLLM.stream()` es síncrono | Usar `httpx.AsyncClient.stream()` directo a Ollama API | TRUE async streaming funciona |
| TTFT alto (22-32s) | Score filtering (MIN_SCORE=0.3) | Reducción de contexto 77% |
| Fuentes con rutas absolutas | Convertir a rutas relativas | Links funcionan en Obsidian |
| Fuentes inexistentes aparecían | Verificar con `vault.getAbstractFileByPath()` + fallback | UX limpia, solo fuentes reales |
| Status no se actualizaba | `setInterval` cada 10s | Status siempre actualizado |
| Markdown cells en SSE | Usar `fetch()` nativo con `ReadableStream` | Streaming real en browser |

### Preguntas Abiertas

- [ ] ¿Soporte para múltiples vaults simultáneos?
- [ ] ¿Guardar historial de conversaciones?
- [ ] ¿Exportar conversaciones?
- [ ] ¿Modo offline sin Ollama (solo búsqueda)?
- [ ] ¿Integración con otros LLM providers (OpenAI, Anthropic)?

### Notas de Reuniones

#### 29 de noviembre de 2025
- Decisión: Proceder con arquitectura cliente-servidor
- Decisión: Plugin gestiona instalación del backend
- Decisión: Documentar todo antes de codificar
- Próximo paso: Revisar este documento y comenzar Fase 1

---

## 🔗 Referencias

### Documentación Oficial
- [Obsidian Plugin API](https://github.com/obsidianmd/obsidian-api)
- [Obsidian Sample Plugin](https://github.com/obsidianmd/obsidian-sample-plugin)
- [Plugin Guidelines](https://docs.obsidian.md/Plugins/Releasing/Plugin+guidelines)
- [Developer Policies](https://docs.obsidian.md/Developer+policies)

### Plugins de Referencia
- [Shell Commands](https://github.com/Taitava/obsidian-shellcommands) - Ejecución de procesos
- [Obsidian Copilot](https://github.com/logancyang/obsidian-copilot) - Integración LLM
- [Smart Connections](https://github.com/brianpetro/obsidian-smart-connections) - RAG nativo

### Herramientas
- [PyPI](https://pypi.org/)
- [Typer](https://typer.tiangolo.com/)
- [esbuild](https://esbuild.github.io/)

---

## 🎁 Características Implementadas No Planificadas

> Estas características se añadieron durante la Fase 4 basándose en necesidades reales de UX que surgieron durante el desarrollo.

### 1. Streaming SSE Completo
**¿Por qué?**: El usuario quería ver el progreso mientras el agente procesaba la pregunta.

- **Endpoint `/ask/stream`**: Server-Sent Events con múltiples tipos de eventos
- **TRUE async streaming**: Usando `httpx.AsyncClient` en lugar de LangChain (que bloqueaba)
- **Fases visibles**: El usuario ve en qué fase está el grafo (retrieve → rerank → generate)
- **TTFT Badge**: Muestra cuánto tardó el primer token

### 2. Score Filtering
**¿Por qué?**: El TTFT era muy alto (22-32s) por contexto excesivo.

- **MIN_SCORE_THRESHOLD = 0.3**: Documentos con score < 0.3 se filtran
- **Reducción 77%**: De ~16k caracteres a ~4k caracteres de contexto
- **Logging detallado**: Se reporta cuántos docs se filtran

### 3. Verificación de Fuentes
**¿Por qué?**: Las fuentes mostraban archivos que no existían en el vault.

- **Verificación de existencia**: `vault.getAbstractFileByPath()`
- **Búsqueda fallback**: Si no encuentra por path, busca por nombre
- **Filtrado en UI**: Solo se muestran fuentes que existen

### 4. Status Polling
**¿Por qué?**: El indicador Online/Offline no se actualizaba.

- **Polling cada 10s**: `setInterval` que verifica `/health`
- **Actualización visual**: El status bar refleja el estado real

### 5. Logging con Timestamps
**¿Por qué?**: Para debuggear el streaming necesitábamos saber cuándo ocurría cada cosa.

- **Formato**: `HH:MM:SS.mmm - LEVEL - message`
- **Events logged**: Cada fase, cada 10 tokens, TTFT, errores

---

## 📊 Métricas de Progreso

### Progreso General

```
Fase 0: Preparación          [██████████] 100% ✅
Fase 1: Backend              [██████████] 100% ✅
Fase 2: Testing Backend      [██████████] 100% ✅
Fase 3: PyPI                 [██████████] 100% ✅
Fase 4: Plugin               [██████████] 100% ✅
Fase 5: Testing Plugin       [██░░░░░░░░]  20% 🔄
Fase 6: Documentación        [█░░░░░░░░░]  10%
Fase 7: Publicación          [░░░░░░░░░░]   0%
─────────────────────────────────────────────
TOTAL                        [███████░░░]  ~70%
```

### Últimas Actualizaciones

| Fecha | Actualización |
|-------|---------------|
| 2025-11-29 | ✅ Fase 4 completada: Plugin funcional con streaming SSE, chat view, source links (#24 cerrado) |
| 2025-11-29 | 🆕 Implementado TRUE async streaming con httpx (no estaba planificado) |
| 2025-11-29 | 🆕 Implementado score filtering para reducir contexto (MIN_SCORE=0.3) |
| 2025-11-29 | 🆕 Implementada verificación de existencia de fuentes |
| 2025-11-29 | 🆕 Implementado status polling cada 10 segundos |
| 2025-11-29 | 🔄 Fase 5 en progreso: Testing del plugin en macOS |
| 2025-11-29 | 🔄 Fase 4 en progreso: Scaffolding del plugin creado, compilando con esbuild |
| 2025-11-29 | ✅ Fase 3 completada: PyPI publicado v3.0.1, Trusted Publishers, workflow automático (#23 cerrado) |
| 2025-01-14 | ✅ Fase 2 completada: 59 tests, CI/CD configurado, ruff aplicado (#22 cerrado) |
| 2025-01-14 | ✅ Fase 1 completada: Backend reestructurado como paquete PyPI (#20 cerrado) |
| 2025-11-29 | ✅ Fase 0 completada: Issues creados (#20-#28), Epic #21 activo |
| 2025-11-29 | Creada rama v3-plugin, documento de planificación inicial |

---

## 🔮 Roadmap Futuro (Post v3.0)

> Mejoras planificadas para versiones futuras, enfocadas en mejorar la experiencia de usuarios no técnicos.

### v3.1 - Mejoras de UX

- [ ] **Setup Wizard**: Modal interactivo que detecta prerequisitos (Python, Ollama) y guía la instalación
- [ ] **Status Dashboard**: Vista del estado del sistema (servidor, modelo cargado, notas indexadas)
- [ ] **Progress Indicators**: Barras de progreso para indexación ~~y generación de respuestas~~ *(streaming ya implementado en v3.0)*
- [ ] **Auto-start server**: Spawn del servidor Python directamente desde el plugin
- [ ] **Server lifecycle management**: Start/Stop/Restart desde comandos del plugin

### v3.2 - Instalación Simplificada

- [ ] **Detección automática de Python**: Buscar Python en ubicaciones comunes
- [ ] **Verificación de Ollama**: Detectar si Ollama está corriendo y qué modelos hay disponibles
- [ ] **Links directos de instalación**: Botones que abren las páginas de descarga de Ollama y Python
- [ ] **Verificación pre-start**: Antes de iniciar el servidor, verificar que todo está listo

### v3.3 - Instalador Automático (Avanzado)

- [ ] **Descarga automática de Ollama**: Script que descarga e instala Ollama si no existe
- [ ] **Gestión de modelos**: Descargar modelos LLM desde el plugin
- [ ] **Python embebido**: Explorar bundlear un Python mínimo con el plugin (pyinstaller/nuitka)
- [ ] **Actualizaciones automáticas del backend**: Detectar nuevas versiones en PyPI

### v4.0 - Alternativas Cloud (Opcional)

- [ ] **Soporte OpenAI API**: Opción para usar GPT-4 en lugar de Ollama local
- [ ] **Soporte Anthropic API**: Opción para usar Claude
- [ ] **Soporte Azure OpenAI**: Para usuarios enterprise
- [ ] **Toggle local/cloud**: El usuario elige según privacidad vs conveniencia

### Consideraciones de Diseño

| Versión | Target Audience | Conocimientos Requeridos |
|---------|-----------------|--------------------------|
| v3.0 | Desarrolladores, Power Users | Terminal, Python básico |
| v3.1-v3.2 | Usuarios técnicos | Instalar apps, seguir instrucciones |
| v3.3+ | Usuarios generales | Solo usar Obsidian |
| v4.0 | Cualquier usuario | Solo tener API key |

---

> **Nota**: Este documento es una guía viva. Actualízalo conforme avance el proyecto.
> 
> **Próxima Acción**: Completar Fase 5 (testing en Windows/Linux) y Fase 6 (documentación).

---

*Documento generado el 29 de noviembre de 2025*  
*Última actualización: 29 de noviembre de 2025*
