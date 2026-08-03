# Troubleshooting ObsidianRAG 4

## Server does not start

Run the configured executable directly:

```bash
obsidianrag serve --vault /path/to/test-vault
```

The plugin setting must contain an executable path or name, not a compound shell command. On Windows, use the installed `obsidianrag.exe` console script.

Check that port 8000 is free or configure another port.

## Plugin reports an incompatible backend

Plugin 4.0.1 accepts only `api_version: 4`.

```bash
curl http://127.0.0.1:8000/capabilities
```

Upgrade backend and plugin together.

## Server is online but chat is unavailable

This is expected when no query pipeline is loaded:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/index/status
```

Use Build index, Refresh index, or Full rebuild according to the returned state.

## Incremental refresh requires a full rebuild

Embedding provider/model, actual embedding output, vector dimension, schema, chunk size, or chunk overlap changed. Use:

```bash
obsidianrag index --vault /path/to/test-vault --full-rebuild
```

## Refresh succeeded on disk but the old revision is serving

Candidate model or pipeline construction failed after disk activation. Existing readers remain safe. `/index/status` reports active and serving revisions as different and state `stale`. Fix the provider error and refresh again; a no-op build reconciles the runtime with the active revision.

## Prune reports a revision in use

An active or recently retired request still leases the revision. Wait for normal and streaming requests to finish, then retry:

```bash
obsidianrag prune --vault /path/to/test-vault
```

## Provider unavailable

For Ollama:

```bash
curl http://localhost:11434/api/tags
```

For LM Studio or compatible chat-completions servers:

```bash
curl http://localhost:1234/v1/models
```

Confirm the configured model exists and the backend URL is correct.

## Legacy 3.x data

ObsidianRAG 4 ignores `.obsidianrag/db`. It never imports or deletes it automatically. Remove legacy data manually only after validating the v4 index.

## Safe diagnostic bundle

Use a temporary/test vault and collect:

```bash
obsidianrag version
obsidianrag status --vault /path/to/test-vault
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/index/status
```

Do not include API keys, private note contents, or absolute personal paths in bug reports.
