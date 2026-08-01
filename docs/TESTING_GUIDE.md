# ObsidianRAG 4 Testing Guide

## Automated checks

Backend:

```bash
cd backend
uv sync --locked --dev
uv run pytest -m "not integration and not slow"
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv build
```

Plugin:

```bash
cd plugin
pnpm install --frozen-lockfile
pnpm test
pnpm run lint
pnpm run build
```

Automated tests must use temporary/sample vaults and mocked providers.

## Manual desktop matrix

Exercise macOS, Linux, and Windows before release.

1. Install backend 4.0.0 and plugin 4.0.0.
2. Configure the backend executable (`obsidianrag.exe` on Windows).
3. Verify process startup uses no shell and accepts vault paths containing spaces.
4. Start with a test vault that has no index.
5. Confirm health is online while chat reports the index is not ready.
6. Build the index from the plugin.
7. Ask a question and open its source link.
8. Modify, add, and delete test notes; confirm status becomes stale.
9. Refresh and verify the incremental counters.
10. Keep one query active while refreshing; verify the old request completes.
11. Prune inactive revisions after readers finish.
12. Change an embedding or chunk setting; confirm Full rebuild is offered.
13. Corrupt a copied test manifest and confirm explicit full rebuild recovery.

Never use a personal vault for release validation.

## Release artifacts

Backend:

- wheel and source distribution report version 4.0.0;
- normal installation includes LanceDB;
- `obsidianrag.__version__` reports 4.0.0.

Plugin:

- `package.json` and `manifest.json` report 4.0.0;
- `main.js`, `manifest.json`, and `styles.css` are present;
- API 3 backends are rejected.
