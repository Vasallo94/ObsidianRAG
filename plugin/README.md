# Vault RAG Plugin 4

Desktop Obsidian plugin for ObsidianRAG API 4.

## Install

1. Install backend 4.0.1: `uv tool install obsidianrag==4.0.1`.
2. Download `main.js`, `manifest.json`, and `styles.css` from the plugin GitHub release.
3. Place them in `<vault>/.obsidian/plugins/vault-rag/`.
4. Reload Obsidian and enable **Vault RAG**.

## Configure

- **Backend executable**: `obsidianrag`, or `obsidianrag.exe` on Windows
- **Server port**: `8000`
- **Model provider**: Ollama, LM Studio, or custom
- **Model and endpoint**
- **Auto-start server**
- **Show source links**

The backend field accepts an executable path or name, not a compound shell command. The plugin always launches it with `shell:false`.

## Use

1. Start the backend.
2. Select Build index on a fresh vault.
3. Refresh after notes change.
4. Use Full rebuild when embedding or chunk configuration becomes incompatible.
5. Prune inactive revisions after old readers finish.
6. Open chat and ask a question.

The plugin accepts only API 4 and deliberately rejects older backends. The server can be online while `query_ready` is false; this allows the plugin to offer the correct index lifecycle action without automatic indexing.

## Develop

```bash
pnpm install --frozen-lockfile
pnpm test
pnpm run lint
pnpm run build
```

Release assets are built in GitHub Actions from the frozen pnpm lockfile.
