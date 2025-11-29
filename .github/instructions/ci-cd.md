# CI/CD & Deployment Guidelines

> Instructions for GitHub Actions, releases, and deployment

## GitHub Actions Workflows

### Backend Tests (`test-backend.yml`)
```yaml
name: Backend Tests

on:
  push:
    branches: [main, v3-plugin]
    paths: ['backend/**']
  pull_request:
    branches: [main, v3-plugin]
    paths: ['backend/**']

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    
    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --dev

      - name: Lint
        run: |
          uv run ruff check obsidianrag/ tests/
          uv run ruff format --check obsidianrag/ tests/

      - name: Test
        run: |
          uv run pytest tests/ -m "not slow" \
            --cov=obsidianrag \
            --cov-report=xml \
            --cov-fail-under=60

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: backend/coverage.xml
```

### Plugin Build (`build-plugin.yml`)
```yaml
name: Build Plugin

on:
  push:
    branches: [main, v3-plugin]
    paths: ['plugin/**']
  pull_request:
    branches: [main, v3-plugin]
    paths: ['plugin/**']

jobs:
  build:
    runs-on: ubuntu-latest
    
    defaults:
      run:
        working-directory: plugin

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'
          cache: 'npm'
          cache-dependency-path: plugin/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Build
        run: npm run build

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: plugin-build
          path: |
            plugin/main.js
            plugin/manifest.json
            plugin/styles.css
```

### Release Workflow (`release.yml`)
```yaml
name: Release

on:
  push:
    tags: ['v*']

jobs:
  release-backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Build package
        run: uv build

      - name: Publish to PyPI
        env:
          UV_PUBLISH_TOKEN: ${{ secrets.PYPI_TOKEN }}
        run: uv publish

  release-plugin:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: plugin
    
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '18'

      - run: npm ci
      - run: npm run build

      - name: Create release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            plugin/main.js
            plugin/manifest.json
            plugin/styles.css
```

## Release Process

### Version Bump Checklist

1. **Update versions**:
   ```bash
   # Backend version in backend/obsidianrag/__init__.py
   __version__ = "3.0.1"
   
   # Plugin version in plugin/manifest.json
   { "version": "3.0.1" }
   
   # Plugin version in plugin/package.json
   { "version": "3.0.1" }
   ```

2. **Update CHANGELOG.md**:
   ```markdown
   ## [3.0.1] - 2025-01-15
   
   ### Added
   - New feature X
   
   ### Fixed
   - Bug Y
   
   ### Changed
   - Improved Z
   ```

3. **Create release commit**:
   ```bash
   git add -A
   git commit -m "chore: release v3.0.1"
   git tag v3.0.1
   git push origin main --tags
   ```

### Semantic Versioning

- **MAJOR** (3.x.x): Breaking changes
- **MINOR** (x.1.x): New features, backward compatible
- **PATCH** (x.x.1): Bug fixes, backward compatible

## PyPI Publishing

### Setup (One-time)
1. Create account on [PyPI](https://pypi.org)
2. Generate API token with upload permissions
3. Add `PYPI_TOKEN` to GitHub repo secrets

### Manual Publish
```bash
cd backend
uv build
uv publish --token $PYPI_TOKEN
```

### Package Metadata (`pyproject.toml`)
```toml
[project]
name = "obsidianrag"
version = "3.0.0"
description = "RAG system for Obsidian notes with local LLMs"
authors = [{name = "Your Name", email = "you@example.com"}]
license = {text = "MIT"}
readme = "README.md"
requires-python = ">=3.11"
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Framework :: FastAPI",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]
keywords = ["obsidian", "rag", "llm", "langchain", "ollama"]

[project.urls]
Homepage = "https://github.com/Vasallo94/ObsidianRAG"
Documentation = "https://github.com/Vasallo94/ObsidianRAG#readme"
Repository = "https://github.com/Vasallo94/ObsidianRAG"
Issues = "https://github.com/Vasallo94/ObsidianRAG/issues"
```

## Obsidian Community Plugins

### Submission Requirements
1. Plugin must be open source
2. Must have `manifest.json` with correct format
3. Must have `README.md` with usage instructions
4. Must pass community review

### manifest.json
```json
{
    "id": "obsidianrag",
    "name": "ObsidianRAG",
    "version": "3.0.0",
    "minAppVersion": "1.0.0",
    "description": "Ask questions about your notes using local AI",
    "author": "Your Name",
    "authorUrl": "https://github.com/Vasallo94",
    "fundingUrl": "",
    "isDesktopOnly": true
}
```

### Submission Process
1. Fork [obsidian-releases](https://github.com/obsidianmd/obsidian-releases)
2. Add plugin to `community-plugins.json`
3. Submit PR with plugin info
4. Wait for review

## Environment Variables

### GitHub Secrets Needed
| Secret | Purpose |
|--------|---------|
| `PYPI_TOKEN` | PyPI publishing |
| `CODECOV_TOKEN` | Coverage reports |

### Local Development (.env)
```bash
# backend/.env (gitignored)
OBSIDIANRAG_LLM_MODEL=gemma3
OBSIDIANRAG_USE_RERANKER=true
```

## Branch Strategy

```
main (stable)
├── v3-plugin (development)
│   ├── feature/xxx
│   └── fix/yyy
└── releases (tags: v3.0.0, v3.0.1, ...)
```

### Branch Rules
- `main`: Protected, requires PR and passing CI
- `v3-plugin`: Development branch for v3
- Feature branches: `feature/description`
- Bug fixes: `fix/description`

## Deployment Checklist

### Before Release
- [ ] All tests pass
- [ ] Linting passes
- [ ] Version numbers updated
- [ ] CHANGELOG updated
- [ ] README updated if needed
- [ ] No debug code left

### After Release
- [ ] Tag created and pushed
- [ ] GitHub Release created
- [ ] PyPI package published
- [ ] Plugin release uploaded
- [ ] Announcement posted (if major)
