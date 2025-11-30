# User Guide

## Installation

### Prerequisites
- **Obsidian**: v1.5.0 or higher
- **Python**: v3.11 or higher
- **Ollama**: Installed and running (get it from [ollama.ai](https://ollama.ai))

### Installing the Plugin
1. Open Obsidian Settings > Community Plugins
2. Turn off "Safe Mode"
3. Click "Browse" and search for "ObsidianRAG"
4. Click "Install" and then "Enable"

### Installing the Backend
The plugin requires a companion Python backend.
1. Open your terminal
2. Run: `pip install obsidianrag`
3. Verify installation: `obsidianrag --version`

## Configuration

### Initial Setup
When you first enable the plugin, a Setup Wizard will guide you through:
1. Verifying Python installation
2. Connecting to Ollama
3. Selecting your LLM model (e.g., `gemma3`)

### Settings
Go to Settings > ObsidianRAG to configure:
- **Backend Command**: Path to the `obsidianrag` executable (usually auto-detected)
- **Server Port**: Default is 8000
- **LLM Model**: Select from available Ollama models
- **Auto-start**: Automatically start the backend when Obsidian opens

## Usage

### Chat Interface
1. Click the 🤖 icon in the ribbon (left sidebar)
2. Type your question in the chat box
3. The AI will search your notes and provide an answer with citations

### Commands
Press `Cmd/Ctrl + P` and search for "ObsidianRAG":
- **Open Chat**: Opens the sidebar chat
- **Ask a Question**: Opens a quick question modal
- **Reindex Vault**: Forces a re-scan of your notes
- **Start/Stop Server**: Manually control the backend

## Tips
- **First Run**: The first time you ask a question, the system needs to index your vault. This may take a few minutes depending on the size of your vault.
- **Citations**: Click on any citation [Note Name] to open that note.
- **Streaming**: You'll see the answer being generated in real-time.
