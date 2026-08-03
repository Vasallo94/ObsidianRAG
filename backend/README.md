# ObsidianRAG Backend 4

Python 3.11+ backend for the ObsidianRAG API, CLI, revisioned SQLite FTS5 catalog, and embedded LanceDB vector index.

## Install

```bash
pip install obsidianrag==4.0.1
# or
uv tool install obsidianrag==4.0.1
```

LanceDB is a standard dependency in 4.0.1; no extra is required.

## Commands

```bash
obsidianrag serve --vault /path/to/vault
obsidianrag index --vault /path/to/vault
obsidianrag index --vault /path/to/vault --full-rebuild
obsidianrag status --vault /path/to/vault
obsidianrag prune --vault /path/to/vault
obsidianrag search "deployment rollback" --vault /path/to/vault
obsidianrag search "deployment rollback" --vault /path/to/vault --lexical-only
obsidianrag ask "How do I roll back a deployment?" --vault /path/to/vault
```

`index` is incremental by default. Use `--full-rebuild` only when status reports incompatible schema, embedding, or chunk settings, or when recovering a malformed active manifest.

## API 4

Start the server:

```bash
obsidianrag serve --vault /path/to/vault --host 127.0.0.1 --port 8000
```

Endpoints:

- `GET /capabilities`
- `GET /health`
- `GET /models`
- `POST /ask`
- `POST /ask/stream`
- `GET /index/status`
- `POST /index/build`
- `POST /index/prune`

A fresh server is healthy but not query-ready. It does not build automatically. `GET /health` reports `query_ready`, `active_revision`, and `serving_revision` so clients can present the correct lifecycle action.

Build request:

```json
{
  "full_rebuild": false
}
```

Status states:

- `missing`: build the first index.
- `current`: active content and configuration match the vault.
- `stale`: refresh incrementally; an older revision may remain available to current readers.
- `rebuild_required`: perform an explicit full rebuild.

## Storage and safety

Indexes live under `.obsidianrag/v4`. Builds:

- scan regular Markdown without following symlinks or junctions;
- create isolated copy-on-write revisions;
- copy unchanged vectors in bounded batches;
- fingerprint actual synthetic embedding outputs;
- validate SQLite integrity, foreign keys, FTS semantics, deterministic IDs, paths, dimensions, and finite vectors;
- fsync the candidate before atomically replacing `active.json`;
- keep the previous serving revision available until all checked-out readers finish.

`prune` removes inactive revisions only when no reader lease exists.

Legacy `.obsidianrag/db` data from 3.x is ignored and never removed automatically.

## Providers

Generation supports Ollama, LM Studio, and custom Ollama/chat-completions-compatible endpoints. Embeddings support Ollama and HuggingFace.

```bash
obsidianrag serve --vault /path/to/vault --provider ollama --model gemma3

obsidianrag serve --vault /path/to/vault \
  --provider lmstudio --model local-model \
  --base-url http://localhost:1234/v1
```

Environment variables use the `OBSIDIANRAG_` prefix.

## Evaluation

```bash
obsidianrag evaluate evaluation.json --vault /path/to/vault --k 10
obsidianrag evaluate evaluation.json --vault /path/to/vault --lexical-only
obsidianrag compare-evaluations baseline.json candidate.json
```

External-agent evaluation requires explicit private-data consent:

```bash
obsidianrag evaluate-agent private.json \
  --vault /path/to/vault \
  --generator-command "python -m obsidianrag.pi_agent_adapter" \
  --judge-command "python -m obsidianrag.pi_agent_adapter" \
  --allow-private-data
```

## Development

```bash
uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv build
```

Normal tests use temporary/sample vaults and mocked providers.
