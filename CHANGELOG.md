# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [4.0.0] - 2026-08-01

### Added
- API 4 index lifecycle endpoints and matching plugin Build, Refresh, Full rebuild, and Prune controls
- Copy-on-write SQLite FTS5 and LanceDB revisions with reader leases
- Read-only missing/current/stale/rebuild-required status inspection
- Provider-neutral grounded query pipeline with numeric citations
- Retrieval and external-agent evaluation commands

### Changed
- Promoted SQLite FTS5 and LanceDB to the only production retrieval engine
- Made LanceDB a standard backend dependency
- Made backend and plugin versions `4.0.0` with exact API 4 compatibility
- Swapped serving pipelines atomically while preserving in-flight readers
- Made backend and plugin release installs lockfile-reproducible
- Simplified CLI commands to `index`, `status`, `ask`, `search`, and `prune`

### Fixed
- Empty-vault updates now activate a valid empty revision
- Malformed active manifests can be recovered with an explicit full rebuild
- Embedding fingerprints prevent vector reuse across incompatible vector spaces
- Bounded LanceDB copying and semantic cross-store validation prevent unsafe activation
- Cancellation no longer closes a retriever while its worker thread is still running
- Failed runtime swaps preserve the previous serving revision and expose the mismatch as stale
- Windows durability sync opens managed files with a writable descriptor as required by `_commit`
- Windows reader-lease liveness checks no longer send a console interrupt to the owning process
- External-agent commands preserve Windows executable paths without invoking a shell

### Security
- Managed paths and Markdown scans reject symlinks and junctions
- POSIX reads, activation, and cleanup use descriptor-relative operations
- Plugin backend startup uses `shell:false` on every platform
- API keys remain session-only and never appear in process arguments

### Removed
- API 3 and plugin/backend compatibility fallback
- Chroma, LangGraph, classic retriever, reranker, and v3 public library paths
- `/stats`, `/rebuild_db`, `v4-*` command aliases, and engine selectors
- Optional `obsidianrag[v4]` installation extra

## [3.0.3] - 2026-05-11

### Added
- Flexible LLM provider support: Ollama, LM Studio, and OpenAI-compatible servers
- Docker deployment with docker-compose (multi-stage build, CPU-only PyTorch)
- LLM timeout enforcement via `request_timeout` setting
- BM25 retriever caching (built once at startup, reused across requests)
- LRU session store with bounded memory (max 100 sessions, 20 messages each)
- Path traversal prevention in document reads and vault indexing
- Input length validation (5000 character limit on questions)
- `llm_provider.py` module for multi-provider LLM abstraction
- CLI flags: `--provider`, `--base-url`, `--api-format`, `--api-key`
- Plugin settings for provider, API format, base URL, and API key

### Changed
- Health endpoint returns 503 when system is not ready (was 200)
- CORS restricted to GET/POST with Content-Type header only
- Reranker and retriever errors use specific exception types instead of broad catch
- Pydantic settings use v2 ConfigDict API
- Streaming retrieval runs in thread executor (non-blocking event loop)
- API key excluded from startup logs
- Error responses use proper HTTP status codes (was 200 with error field)
- Source paths in API responses are relative (was absolute filesystem paths)
- CLI status command uses configured Ollama URL (was hardcoded)
- Metadata tracker avoids double filesystem scan
- Default embedding model changed to Ollama `qwen3-embedding`

### Removed
- Silent fallback for embedding provider (now raises on failure)
- Silent fallback for LLM model selection (now raises ModelNotAvailableError)
- Dead code: legacy `create_qa_chain` and `ask_question` functions

### Fixed
- SSE error events use actual newlines instead of literal `\\n\\n`
- Plugin click listeners no longer accumulate over time
- Plugin stopServer race condition (manual stop no longer triggers auto-restart)
- Plugin settings reset uses DEFAULT_SETTINGS spread
- Incremental indexing loads new version before deleting old (prevents data loss)
- Global GraphTracer replaced with request-scoped instances (thread safety)
- Lock restructured: inference runs outside lock (was serializing all requests)
- asyncio.Lock created inside lifespan (was at module level, broke with reload)

### Security
- Vault path boundary validation on all file reads
- Symlink traversal blocked (`followlinks=False` in `os.walk`)
- Docker: `no-new-privileges`, 4 GB memory limit, healthcheck, non-root user
- HuggingFace model cache persisted in named Docker volume
