# User Guide

## Installation

Requirements:

- Obsidian 1.5 or newer
- Python 3.11 or newer
- ObsidianRAG backend 4.0.0
- Vault RAG plugin 4.0.0
- An Ollama, LM Studio, or compatible generation server

Install the backend:

```bash
uv tool install obsidianrag==4.0.0
```

Install `main.js`, `manifest.json`, and `styles.css` from the plugin GitHub release into `<vault>/.obsidian/plugins/vault-rag/`, then enable the plugin.

## Configuration

In Vault RAG settings configure:

- **Backend executable**: `obsidianrag`, or `obsidianrag.exe` on Windows
- **Server port**: `8000` by default
- **Model provider** and endpoint
- **Model**
- **Auto-start server**
- **Show source links**

The executable field is a path or command name, not a compound shell command.

## Index lifecycle

The server does not index automatically.

- **Build index** creates the first revision.
- **Refresh index** incrementally applies added, modified, and deleted notes.
- **Full rebuild** appears after incompatible embedding or chunk settings.
- **Prune** removes inactive revisions after their readers close.

## Chat

1. Start the server.
2. Build or refresh the index when prompted.
3. Open the chat from the ribbon or command palette.
4. Ask a question.
5. Follow the source links shown with the grounded answer.

A stale index can remain query-ready while a previous revision is serving. Refresh it to make the latest validated revision active for new questions.

## Commands

The command palette includes:

- Open chat
- Ask a question
- Start server
- Stop server
- Check status
- Refresh index

API 3 backends are intentionally rejected by plugin 4.0.0.
