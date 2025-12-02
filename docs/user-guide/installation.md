# Installation Guide

## Prerequisites

Before installing ObsidianRAG, ensure you have the following components ready:

1.  **Obsidian**: Version 1.5.0 or higher.
2.  **Python**: Version 3.11 or higher.
    -   Verify with `python --version` in your terminal.
    -   If not installed, download from [python.org](https://www.python.org/downloads/).
3.  **Ollama**: For running the local LLM.
    -   Download from [ollama.ai](https://ollama.ai).
    -   Start the Ollama server (usually runs in the background).
4.  **LLM Model**: Pull a model to use (e.g., `gemma3`).
    -   Run `ollama pull gemma3` in your terminal.

## Step 1: Install the Backend

The backend is a Python package that handles the heavy lifting (RAG, embeddings, LLM communication).

1.  Open your terminal.
2.  Install the package using pip:
    ```bash
    pip install obsidianrag
    ```
    *Note: We recommend using `pipx` for isolated installation: `pipx install obsidianrag`*

3.  Verify the installation:
    ```bash
    obsidianrag --version
    ```

## Step 2: Install the Plugin

1.  Open Obsidian.
2.  Go to **Settings** > **Community Plugins**.
3.  Ensure **Restricted mode** is **OFF**.
4.  Click **Browse** and search for `Vault RAG`.
5.  Click **Install**.
6.  Once installed, click **Enable**.

> **Note**: The plugin is currently pending approval for Community Plugins. For now, you can install manually by downloading from [GitHub Releases](https://github.com/Vasallo94/ObsidianRAG/releases) and placing the files in your `.obsidian/plugins/vault-rag/` folder.

## Step 3: Initial Configuration

Upon enabling the plugin, a **Setup Wizard** should appear. If not, you can access settings via **Settings** > **ObsidianRAG**.

1.  **Backend Command**: The plugin tries to detect your `obsidianrag` executable.
    -   If it fails, find the path with `which obsidianrag` (macOS/Linux) or `where obsidianrag` (Windows) and paste it here.
2.  **Server Port**: Default is `8000`. Change only if this port is occupied.
3.  **LLM Model**: Select the model you pulled earlier (e.g., `gemma3`).
    -   *Note: If the dropdown is empty, ensure Ollama is running.*

## Step 4: Verify Installation

1.  Check the status bar at the bottom right of Obsidian. It should show **🤖 RAG ●** (Online).
2.  Click the icon to open the chat view.
3.  Ask a simple question like "What is in my vault?".
4.  The first request will trigger an index of your vault. This might take a moment.

## Troubleshooting

If you encounter issues, please refer to the [Troubleshooting Guide](TROUBLESHOOTING.md).
