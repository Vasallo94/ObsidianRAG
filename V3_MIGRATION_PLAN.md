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
> **Estado**: ⏳ Pendiente  
> **Duración estimada**: 1-2 días

**Objetivo**: Hacer el backend instalable via `pip install obsidianrag`.

#### 3.1 Preparación
- [ ] Verificar que el nombre `obsidianrag` está disponible en PyPI
- [ ] Crear cuenta en PyPI (si no existe)
- [ ] Crear cuenta en TestPyPI para pruebas
- [ ] Configurar tokens de autenticación

#### 3.2 Build y Test Local
- [ ] `pip install build`
- [ ] `python -m build`
- [ ] Instalar localmente y probar
- [ ] Verificar que CLI funciona después de `pip install`

#### 3.3 Publicación
- [ ] Publicar en TestPyPI primero
- [ ] Instalar desde TestPyPI y probar
- [ ] Publicar en PyPI
- [ ] Verificar instalación desde PyPI

#### 3.4 GitHub Actions para Releases
- [ ] Crear `.github/workflows/release-backend.yml`
- [ ] Trigger en tags `backend-v*`
- [ ] Build y publicación automática

### Fase 4: Desarrollo del Plugin de Obsidian
> **Estado**: ⏳ Pendiente  
> **Duración estimada**: 7-10 días

**Objetivo**: Crear el plugin TypeScript que gestiona el backend y proporciona UI.

#### 4.1 Setup del Proyecto
- [ ] Crear estructura `plugin/`
- [ ] Inicializar con `obsidian-sample-plugin` como base
- [ ] Configurar TypeScript, ESLint, esbuild
- [ ] Configurar `manifest.json`

#### 4.2 Server Manager
- [ ] Implementar `server-manager.ts`
  - [ ] Detección de Python (`which python3`)
  - [ ] Detección de pip/pipx
  - [ ] Instalación de obsidianrag si no existe
  - [ ] Spawn del proceso servidor
  - [ ] Manejo de stdout/stderr
  - [ ] Kill del proceso en onunload
  - [ ] Restart automático si el proceso muere
- [ ] Manejar diferentes plataformas (Windows, macOS, Linux)

#### 4.3 API Client
- [ ] Implementar `api-client.ts`
  - [ ] Método `ask(question: string): Promise<Answer>`
  - [ ] Método `health(): Promise<boolean>`
  - [ ] Método `stats(): Promise<VaultStats>`
  - [ ] Método `reindex(): Promise<void>`
  - [ ] Timeout handling
  - [ ] Retry logic

#### 4.4 Health Checker
- [ ] Implementar `health-checker.ts`
  - [ ] Polling periódico al endpoint `/health`
  - [ ] Eventos para cambio de estado
  - [ ] Detección de servidor caído

#### 4.5 UI: Chat View
- [ ] Implementar `chat-view.ts` (vista lateral)
  - [ ] Input de texto para preguntas
  - [ ] Historial de mensajes
  - [ ] Mostrar fuentes/referencias
  - [ ] Indicador de loading
  - [ ] Manejo de errores en UI
  - [ ] Scroll automático
  - [ ] Markdown rendering

#### 4.6 UI: Settings Tab
- [ ] Implementar `settings-tab.ts`
  - [ ] Configuración del modelo LLM
  - [ ] Configuración del puerto
  - [ ] Toggle para auto-start del servidor
  - [ ] Botón para reindexar
  - [ ] Mostrar estado del servidor
  - [ ] Mostrar estadísticas del vault

#### 4.7 UI: Status Bar
- [ ] Implementar `status-bar.ts`
  - [ ] Indicador visual del estado del servidor
  - [ ] 🟢 Running / 🟡 Starting / 🔴 Stopped
  - [ ] Click para abrir settings

#### 4.8 UI: Modals
- [ ] Implementar `setup-modal.ts`
  - [ ] Guía de primera instalación
  - [ ] Verificación de prerequisitos
  - [ ] Instalación del backend
- [ ] Implementar `ask-modal.ts`
  - [ ] Modal rápido para preguntas (Command Palette)
- [ ] Implementar `error-modal.ts`
  - [ ] Mostrar errores de forma amigable
  - [ ] Sugerencias de solución

#### 4.9 Commands
- [ ] Registrar comandos en Obsidian:
  - [ ] `ObsidianRAG: Ask a question`
  - [ ] `ObsidianRAG: Open chat`
  - [ ] `ObsidianRAG: Reindex vault`
  - [ ] `ObsidianRAG: Start server`
  - [ ] `ObsidianRAG: Stop server`
  - [ ] `ObsidianRAG: Show status`

#### 4.10 Ribbon Icon
- [ ] Agregar icono en el ribbon (barra lateral izquierda)
- [ ] Click para abrir chat view

### Fase 5: Testing del Plugin
> **Estado**: ⏳ Pendiente  
> **Duración estimada**: 2-3 días

#### 5.1 Tests Manuales
- [ ] Test en macOS
- [ ] Test en Windows
- [ ] Test en Linux
- [ ] Test de instalación limpia
- [ ] Test de upgrade
- [ ] Test de desinstalación

#### 5.2 Edge Cases
- [ ] Python no instalado
- [ ] pip no disponible
- [ ] Ollama no corriendo
- [ ] Puerto ocupado
- [ ] Vault vacío
- [ ] Vault muy grande (>1000 notas)
- [ ] Conexión a servidor perdida
- [ ] Múltiples instancias de Obsidian

#### 5.3 CI/CD para Plugin
- [ ] Crear `.github/workflows/test-plugin.yml`
- [ ] Lint TypeScript
- [ ] Build verification

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
- [ ] Crear directorio `plugin/`
- [ ] Inicializar proyecto desde template
- [ ] Configurar `manifest.json`
- [ ] Configurar `package.json`
- [ ] Configurar `tsconfig.json`
- [ ] Configurar `esbuild.config.mjs`
- [ ] Verificar build: `npm run build`

#### Core
- [ ] Implementar clase principal `ObsidianRAGPlugin`
- [ ] Implementar `onload()`
- [ ] Implementar `onunload()`
- [ ] Implementar `loadSettings()`
- [ ] Implementar `saveSettings()`

#### Server Manager
- [ ] Detectar si Python está instalado
- [ ] Detectar si obsidianrag está instalado
- [ ] Instalar obsidianrag si es necesario
- [ ] Iniciar servidor con spawn
- [ ] Manejar logs del servidor
- [ ] Detener servidor limpiamente
- [ ] Reiniciar servidor si falla
- [ ] Soporte Windows
- [ ] Soporte macOS
- [ ] Soporte Linux

#### API Client
- [ ] Implementar health check
- [ ] Implementar ask
- [ ] Implementar stats
- [ ] Implementar reindex
- [ ] Manejo de errores
- [ ] Timeouts
- [ ] Retries

#### UI
- [ ] Chat View (ItemView)
- [ ] Settings Tab (PluginSettingTab)
- [ ] Status Bar Item
- [ ] Setup Modal
- [ ] Error Modal
- [ ] Quick Ask Modal

#### Commands
- [ ] Registrar todos los comandos
- [ ] Agregar hotkeys por defecto

#### Estilos
- [ ] Crear `styles.css`
- [ ] Estilos para chat view
- [ ] Estilos responsive
- [ ] Soporte para temas claro/oscuro

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
| `/ask` | POST | Hacer pregunta | `{ text: string, session_id?: string }` | `{ result: string, sources: Source[], ... }` |
| `/stats` | GET | Estadísticas del vault | - | `{ notes: number, chunks: number, ... }` |
| `/rebuild_db` | POST | Reindexar vault | - | `{ status: "ok", indexed: number }` |

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

## 📊 Métricas de Progreso

### Progreso General

```
Fase 0: Preparación          [██████████] 100% ✅
Fase 1: Backend              [██████████] 100% ✅
Fase 2: Testing Backend      [██████████] 100% ✅
Fase 3: PyPI                 [██████████] 100% ✅
Fase 4: Plugin               [░░░░░░░░░░]   0%
Fase 5: Testing Plugin       [░░░░░░░░░░]   0%
Fase 6: Documentación        [█░░░░░░░░░]  10%
Fase 7: Publicación          [░░░░░░░░░░]   0%
─────────────────────────────────────────────
TOTAL                        [████░░░░░░]  ~40%
```

### Últimas Actualizaciones

| Fecha | Actualización |
|-------|---------------|
| 2025-11-29 | ✅ Fase 3 completada: PyPI publicado v3.0.1, Trusted Publishers, workflow automático (#23 cerrado) |
| 2025-01-14 | ✅ Fase 2 completada: 59 tests, CI/CD configurado, ruff aplicado (#22 cerrado) |
| 2025-01-14 | ✅ Fase 1 completada: Backend reestructurado como paquete PyPI (#20 cerrado) |
| 2025-11-29 | ✅ Fase 0 completada: Issues creados (#20-#28), Epic #21 activo |
| 2025-11-29 | Creada rama v3-plugin, documento de planificación inicial |

---

> **Nota**: Este documento es una guía viva. Actualízalo conforme avance el proyecto.
> 
> **Próxima Acción**: Comenzar con la Fase 4 - Desarrollo del Plugin de Obsidian (Issue #24).

---

*Documento generado el 29 de noviembre de 2025*  
*Última actualización: 29 de noviembre de 2025*
