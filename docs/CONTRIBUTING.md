# Contributing to ObsidianRAG

Thank you for your interest in contributing to ObsidianRAG! 🎉

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Code Style](#code-style)
- [Testing](#testing)
- [Documentation](#documentation)

---

## Code of Conduct

Please be respectful and constructive in all interactions. We welcome contributors of all experience levels.

---

## Getting Started

### Prerequisites

- **Python 3.11+** for backend development
- **Node.js 18+** and **pnpm** for plugin development
- **Ollama** for testing with local LLMs
- **Git** for version control

### Repository Structure

```
ObsidianRAG/
├── backend/          # Python backend (PyPI package)
│   ├── obsidianrag/  # Main package
│   └── tests/        # Python tests
├── plugin/           # Obsidian plugin (TypeScript)
│   ├── src/          # Source code
│   └── tests/        # Plugin tests
└── docs/             # Documentation
```

---

## Development Setup

### Backend (Python)

```bash
# Clone the repo
git clone https://github.com/Vasallo94/ObsidianRAG.git
cd ObsidianRAG

# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup backend
cd backend
uv sync

# Run tests
uv run pytest

# Start development server
uv run obsidianrag serve --vault /path/to/test/vault --reload
```

### Plugin (TypeScript)

```bash
cd plugin

# Install dependencies
pnpm install

# Development build (with watch)
pnpm run dev

# Production build
pnpm run build

# Run tests
pnpm test

# Link to Obsidian vault for testing
ln -s $(pwd) /path/to/vault/.obsidian/plugins/obsidianrag
```

---

## Making Changes

### Branching Strategy

- `main` - Stable releases
- `v3-plugin` - Development branch for v3
- `feature/*` - New features
- `fix/*` - Bug fixes

### Creating a Branch

```bash
# Start from development branch
git checkout v3-plugin
git pull origin v3-plugin

# Create feature branch
git checkout -b feature/my-awesome-feature
```

---

## Submitting a Pull Request

1. **Ensure tests pass**:
   ```bash
   # Backend
   cd backend && uv run pytest
   
   # Plugin
   cd plugin && pnpm test
   ```

2. **Format code**:
   ```bash
   # Backend
   uv run ruff format obsidianrag/ tests/
   uv run ruff check obsidianrag/ tests/ --fix
   
   # Plugin
   pnpm run lint
   ```

3. **Write a clear PR description**:
   - What does this PR do?
   - Why is this change needed?
   - Any breaking changes?

4. **Keep PRs focused** - One feature or fix per PR

---

## Code Style

### Python (Backend)

- **Formatter**: `ruff format` (line length 88)
- **Linter**: `ruff check`
- **Type hints**: Required for public functions
- **Docstrings**: Google style

```python
def retrieve_documents(query: str, k: int = 10) -> list[Document]:
    """Retrieve relevant documents for a query.
    
    Args:
        query: The search query text.
        k: Maximum number of documents to return.
    
    Returns:
        List of Document objects sorted by relevance.
    """
    ...
```

### TypeScript (Plugin)

- **Formatter**: Prettier (via ESLint)
- **Linter**: ESLint
- **Types**: Strict TypeScript

```typescript
async function askQuestion(question: string): Promise<AskResponse> {
  // Implementation
}
```

---

## Testing

### Backend Tests

```bash
cd backend

# Run all tests
uv run pytest

# Run specific file
uv run pytest tests/test_cli.py -v

# Run with coverage
uv run pytest --cov=obsidianrag --cov-report=term-missing

# Skip slow tests
uv run pytest -m "not slow"
```

### Plugin Tests

```bash
cd plugin

# Run all tests
pnpm test

# Run with coverage
pnpm test -- --coverage

# Watch mode
pnpm test -- --watch
```

---

## Documentation

- Update `README.md` for user-facing changes
- Update `docs/TROUBLESHOOTING.md` for new error cases
- Add JSDoc/docstrings for new functions
- Update `V3_MIGRATION_PLAN.md` for architectural changes

---

## Questions?

Feel free to open an issue if you have questions or need help getting started!

---

<p align="center">
  Thank you for contributing! 🙏
</p>
