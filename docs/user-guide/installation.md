# Installation Guide

ObsidianRAG 4 requires matching backend and plugin releases. It does not index a vault automatically.

## Requirements

- Obsidian 1.5 or newer
- Python 3.11 or newer
- An Ollama, LM Studio, or compatible generation server with an available model

## Install the backend

Install the isolated command with uv:

```bash
uv tool install obsidianrag==4.0.1
```

Alternatively, use pipx:

```bash
pipx install obsidianrag==4.0.1
```

Verify the installed command and version:

```bash
obsidianrag version
```

## Install the plugin

Download these files from the `plugin-v4.0.1` GitHub release:

- `main.js`
- `manifest.json`
- `styles.css`

Place them in `<vault>/.obsidian/plugins/vault-rag/`, reload Obsidian, and enable **Vault RAG** under **Settings > Community plugins**.

## Configure the plugin

Open **Settings > Vault RAG** and configure:

1. **Backend executable**: `obsidianrag`, `obsidianrag.exe` on Windows, or its absolute path. Do not enter a compound shell command.
2. **Server port**: `8000` unless another process uses it.
3. **Model provider**: Ollama, LM Studio, or a compatible custom endpoint.
4. **Model** and provider URL.
5. **Auto-start server**, if desired.

Backend and plugin 4.0.1 use API 4 exclusively and reject API 3 counterparts.

## Build the first index

1. Start the backend from the plugin.
2. Confirm the server is online. It is normal for chat to remain unavailable before indexing.
3. Select **Build index**.
4. Wait until index status is current and query-ready.
5. Open chat and ask a question.

Indexing is always explicit. The first question does not trigger a build.

## Maintain the index

- Select **Refresh index** after adding, editing, or deleting notes. Compatible revisions update incrementally.
- Select **Full rebuild** when embedding, chunk, or schema settings are incompatible.
- Select **Prune** to remove inactive revisions after their readers finish.

Legacy `.obsidianrag/db` data from 3.x is ignored and never deleted automatically.

See the [troubleshooting guide](../TROUBLESHOOTING.md) for startup, provider, status, and recovery help.
