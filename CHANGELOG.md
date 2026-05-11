# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
