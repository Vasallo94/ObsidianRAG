# ObsidianRAG Plugin

Native Obsidian plugin for querying your notes using local AI.

[![Obsidian](https://img.shields.io/badge/Obsidian-Plugin-purple)](https://obsidian.md)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4+-blue)](https://www.typescriptlang.org/)
[![Tests](https://img.shields.io/badge/Tests-28%20passing-brightgreen)](https://github.com/Vasallo94/ObsidianRAG)

---

## 📦 Installation

### From Community Plugins (Recommended)

1. Open Obsidian → Settings → Community Plugins
2. Disable Safe Mode if needed
3. Browse → Search for "ObsidianRAG"
4. Click Install → Enable

### Manual Installation

1. Download latest release from [GitHub Releases](https://github.com/Vasallo94/ObsidianRAG/releases)
2. Extract files to `.obsidian/plugins/obsidianrag/`
3. Reload Obsidian
4. Enable plugin in Settings → Community Plugins

---

## 🚀 Quick Start

### Prerequisites

Before using the plugin, install the backend:

```bash
pip install obsidianrag
```

And install Ollama:
```bash
# macOS
brew install ollama

# Download LLM model
ollama pull gemma3
```

### First Use

1. **Enable the plugin**: Settings → Community Plugins → ObsidianRAG → Enable

2. **Configure settings** (optional):
   - Server Port (default: 8000)
   - LLM Model (default: gemma3)
   - Auto-start Server (default: true)

3. **Open chat**: Click the 🧠 icon in ribbon or use Command Palette → "ObsidianRAG: Open Chat"

4. **Ask questions**:
   ```
   What notes do I have about machine learning?
   Summarize my project ideas
   What did I write about last week?
   ```

---

## ⚙️ Settings

Access via Settings → ObsidianRAG:

### Basic Settings

| Setting | Default | Description |
|---------|---------|-------------|
| **ObsidianRAG Command** | `/usr/local/bin/obsidianrag-server` | Path to backend executable |
| **Server Port** | `8000` | Port for backend API |
| **LLM Model** | `gemma3` | Ollama model to use |
| **Auto-start Server** | `true` | Start backend when Obsidian opens |
| **Show Source Links** | `true` | Display source notes in answers |

### Available Models

Select from dropdown:
- **gemma3** (recommended) - Balanced, good for everything
- **qwen2.5** - Excellent for Spanish
- **llama3.2** - Smaller, faster
- **mistral** - Alternative option
- **phi3** - Very small, fast

---

## 🎨 Features

### Chat Interface

- **Real-time streaming**: See answers as they're generated
- **Source attribution**: Each answer shows relevant notes with:
  - 🟢 High relevance (>80%)
  - 🟡 Medium relevance (60-80%)
  - 🟠 Low relevance (40-60%)
- **Clickable links**: Jump directly to source notes
- **Status indicator**: Shows server Online/Offline status

### Server Management

Commands available in Command Palette:

- `ObsidianRAG: Open Chat` - Open chat view
- `ObsidianRAG: Start Backend Server` - Start server manually
- `ObsidianRAG: Stop Backend Server` - Stop server
- `ObsidianRAG: Check Server Status` - Check if server is running

---

## 🔧 Troubleshooting

### ❌ Server shows "Offline"

**Check backend installation**:
```bash
# Verify installed
pip show obsidianrag

# If not installed
pip install obsidianrag
```

**Start server manually**:
```bash
obsidianrag serve --vault /path/to/vault
```

**Check server port**:
- Settings → ObsidianRAG → Server Port (default: 8000)
- Make sure no other app is using this port

### ❌ "Ollama not running"

```bash
# Make sure Ollama is running
ollama serve

# Verify
curl http://localhost:11434/api/tags

# Download model if needed
ollama pull gemma3
```

### ❌ No answers / "No documents found"

1. Wait for initial indexing (first run can take 1-2 minutes)
2. Check vault has `.md` files
3. Restart server: Command Palette → "ObsidianRAG: Stop Backend Server" → "Start Backend Server"

### ❌ Responses in wrong language

The plugin responds in the dominant language between your question and notes.

Try a different model:
```bash
ollama pull qwen2.5  # Better for Spanish
```

Then in Settings → ObsidianRAG → LLM Model → select `qwen2.5`

---

## 🏗️ Architecture

```
Plugin (TypeScript)
├── main.ts              # Plugin entry point
├── ChatView             # Chat interface
├── ObsidianRAGSettingTab  # Settings UI
└── Server Manager       # Backend control

↓ HTTP (localhost:8000)

Backend (Python)
├── FastAPI Server
├── LangGraph RAG Agent
└── ChromaDB
```

### Data Flow

1. User asks question in chat
2. Plugin → POST `/ask/stream` → Backend
3. Backend:
   - Retrieves relevant notes (hybrid search)
   - Reranks with CrossEncoder
   - Expands context via `[[wikilinks]]`
   - Generates answer with LLM (streaming)
4. Plugin receives SSE events:
   - `status` - Progress updates
   - `retrieve_complete` - Sources found
   - `token` - Answer text (streamed)
   - `answer` - Final answer
5. Displays answer + clickable source links

---

## 🧪 Development

### Setup

```bash
git clone https://github.com/Vasallo94/ObsidianRAG.git
cd ObsidianRAG/plugin

# Install dependencies
pnpm install

# Build for development (watch mode)
pnpm run dev

# Build for production
pnpm run build
```

### Testing

```bash
# Run unit tests
pnpm test

# Watch mode
pnpm test:watch

# Coverage
pnpm test:coverage
```

**Test Coverage**:
- `tests/api-client.test.ts` - HTTP/SSE logic (14 tests)
- `tests/source-parser.test.ts` - Path parsing (11 tests)
- `tests/settings.test.ts` - Settings validation (3 tests)

**Total**: 28 tests

### Project Structure

```
plugin/
├── src/
│   └── main.ts          # Plugin code
├── tests/
│   ├── __mocks__/
│   │   └── obsidian.ts  # Obsidian API mock
│   ├── api-client.test.ts
│   ├── source-parser.test.ts
│   └── settings.test.ts
├── main.js              # Compiled output
├── manifest.json        # Plugin manifest
├── styles.css           # UI styles
├── package.json
├── tsconfig.json
└── esbuild.config.mjs
```

### Releases

```bash
# Version bump
npm version patch  # or minor, major

# Build
pnpm run build

# Create release on GitHub with:
# - main.js
# - manifest.json
# - styles.css
```

---

## 📄 License

MIT License - see [LICENSE](../LICENSE)

---

## 🤝 Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md)
