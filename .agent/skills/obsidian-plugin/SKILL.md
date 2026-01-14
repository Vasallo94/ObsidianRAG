---
name: obsidian-plugin
description: >
  Usa esta skill para el desarrollo del plugin de Obsidian (Frontend),
  incluyendo TypeScript, vistas, settings y comunicación con el backend.
tools: ['read', 'edit', 'run_command']
---

# Obsidian Plugin Development

## Cuándo usar esta skill
- Cuando modifiques la interfaz de usuario en Obsidian (`plugin/src`).
- Cuando cambies la lógica de comunicación con el servidor Python.
- Cuando actualices estilos CSS (`styles.css`).

## Cómo usar esta skill

### 1. Estructura (TypeScript)
- `main.ts`: Entry point, carga settings y registra vistas.
- `chat-view.ts`: Vista del chat (UI).
- `server-manager.ts`: Gestiona el subproceso del servidor Python (`spawn`).
- `api-client.ts`: Cliente HTTP para hablar con `http://localhost:port`.

### 2. Streaming (SSE)
El plugin soporta Server-Sent Events para respuestas progresivas.
- Usa `parseSSEStream` en el cliente para manejar eventos como `token`, `sources`, `done`.

### 3. Desarrollo
```bash
cd plugin
npm install
npm run dev  # Watch mode
```

### 4. Mejores Prácticas
- **UI**: Usa componentes nativos de Obsidian donde sea posible.
- **Estilos**: Usa variables CSS de Obsidian (`--background-primary`, etc.) para soporte de temas.
- **Procesos**: Asegúrate de matar el proceso de Python al descargar el plugin (`onunload`).
