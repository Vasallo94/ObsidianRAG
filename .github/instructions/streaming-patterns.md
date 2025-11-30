# Streaming & Integration Patterns

> Production-tested patterns for SSE streaming, Ollama integration, and async UI updates in ObsidianRAG

## Ollama API Integration

### Fetching Available Models

Query Ollama's API to get installed models dynamically:

```typescript
interface OllamaModel {
  name: string;
  modified_at: string;
  size: number;
}

interface OllamaModelsResponse {
  models: OllamaModel[];
}

async function getOllamaModels(): Promise<string[]> {
  try {
    const response = await fetch("http://localhost:11434/api/tags", {
      method: "GET",
      signal: AbortSignal.timeout(5000),
    });
    
    if (!response.ok) {
      console.warn("Failed to fetch Ollama models");
      return [];
    }
    
    const data: OllamaModelsResponse = await response.json();
    // Remove :latest suffix for cleaner display
    return data.models.map(m => m.name.replace(":latest", ""));
  } catch (error) {
    console.warn("Ollama not available:", error);
    return [];
  }
}
```

### Dynamic Settings Dropdown

Populate dropdown with available models, with fallback to text input:

```typescript
async display(): Promise<void> {
  const models = await this.plugin.getOllamaModels();
  
  const modelSetting = new Setting(containerEl)
    .setName("LLM Model")
    .setDesc("Ollama model to use");

  if (models.length > 0) {
    modelSetting.addDropdown((dropdown) => {
      models.forEach(model => dropdown.addOption(model, model));
      
      // Handle case where saved model no longer exists
      const current = this.plugin.settings.llmModel;
      if (models.includes(current)) {
        dropdown.setValue(current);
      } else {
        dropdown.setValue(models[0]);
        this.plugin.settings.llmModel = models[0];
        new Notice(`Model '${current}' not found. Switched to '${models[0]}'`);
      }
      
      dropdown.onChange(async (value) => {
        this.plugin.settings.llmModel = value;
        await this.plugin.saveSettings();
      });
    });
  } else {
    // Fallback when Ollama is not running
    modelSetting
      .setDesc("⚠️ Ollama not detected. Enter model name manually.")
      .addText((text) => text
        .setValue(this.plugin.settings.llmModel)
        .onChange(async (value) => {
          this.plugin.settings.llmModel = value;
          await this.plugin.saveSettings();
        }));
  }
}
```

---

## SSE Streaming in Obsidian Plugin

### Event Types

Define all possible SSE event types:

```typescript
type StreamEventType = 
  | "phase"           // Current RAG phase (retrieve, rerank, generate)
  | "retrieval_info"  // Number of docs retrieved
  | "context_info"    // Context stats sent to LLM
  | "ttft"            // Time To First Token
  | "token"           // Individual LLM token
  | "sources"         // Source documents cited
  | "done"            // Stream complete
  | "error";          // Error occurred

interface StreamEvent {
  event: StreamEventType;
  data: string;  // JSON string to parse
}
```

### Parsing SSE Stream

```typescript
async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>
): AsyncGenerator<StreamEvent> {
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";  // Keep incomplete line in buffer

    let currentEvent = "message";
    let currentData = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        currentData = line.slice(6);
      } else if (line === "" && currentData) {
        yield { event: currentEvent as StreamEventType, data: currentData };
        currentEvent = "message";
        currentData = "";
      }
    }
  }
}
```

### Consuming the Stream

```typescript
async function askWithStreaming(question: string, onToken: (token: string) => void) {
  const response = await fetch(`${baseUrl}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  let fullAnswer = "";
  let sources: string[] = [];

  for await (const event of parseSSEStream(reader)) {
    switch (event.event) {
      case "token":
        const token = JSON.parse(event.data).token;
        fullAnswer += token;
        onToken(token);  // Update UI incrementally
        break;
        
      case "sources":
        sources = JSON.parse(event.data).sources;
        break;
        
      case "error":
        throw new Error(JSON.parse(event.data).message);
        
      case "done":
        return { answer: fullAnswer, sources };
    }
  }
}
```

---

## Multi-Platform Process Management

### Spawning Backend Server

Handle differences between Windows, macOS, and Linux:

```typescript
function startServer(): void {
  const platform = process.platform;
  const vaultPath = (this.app.vault.adapter as any).basePath;
  
  // Platform-specific spawn options
  const spawnOptions: SpawnOptions = {
    cwd: undefined,
    env: { ...process.env },
    detached: platform !== 'win32',  // Detached on Unix only
    shell: platform === 'win32',     // Shell on Windows only
    windowsHide: true,
  };

  // Build command and args
  let command: string;
  let args: string[];

  if (platform === 'win32') {
    command = this.settings.pythonPath;
    args = [
      "serve",
      "--vault", `"${vaultPath}"`,  // Quote paths on Windows
      "--port", String(this.settings.serverPort),
      "--model", this.settings.llmModel,
      this.settings.useReranker ? "--reranker" : "--no-reranker",
    ];
  } else {
    // macOS and Linux
    command = this.settings.pythonPath;
    args = [
      "serve",
      "--vault", vaultPath,
      "--port", String(this.settings.serverPort),
      "--model", this.settings.llmModel,
      this.settings.useReranker ? "--reranker" : "--no-reranker",
    ];
  }

  this.serverProcess = spawn(command, args, spawnOptions);
}
```

### Killing Process by Port

When the tracked process reference is lost (e.g., server started externally):

```typescript
async stopServer(): Promise<void> {
  // Kill tracked process if exists
  if (this.serverProcess) {
    this.serverProcess.kill();
    this.serverProcess = null;
  }
  
  // Also kill any process on the port
  const { exec } = require("child_process");
  const platform = process.platform;
  
  if (platform === 'win32') {
    exec(`for /f "tokens=5" %a in ('netstat -aon ^| find ":${port}" ^| find "LISTENING"') do taskkill /F /PID %a`);
  } else {
    exec(`lsof -ti:${this.settings.serverPort} | xargs kill -9 2>/dev/null`);
  }
}
```

---

## Auto-Refresh UI Patterns

### Settings Status with Interval

Update server status periodically in settings:

```typescript
class SettingsTab extends PluginSettingTab {
  private refreshInterval: number | null = null;

  async display(): Promise<void> {
    // ... render settings ...
    
    // Setup auto-refresh for status
    if (this.refreshInterval) {
      window.clearInterval(this.refreshInterval);
    }
    this.refreshInterval = window.setInterval(async () => {
      await this.updateStatusDisplay();
    }, 3000);  // Every 3 seconds
  }

  private async updateStatusDisplay(): Promise<void> {
    const statusEl = this.containerEl.querySelector(".status-display");
    if (!statusEl) return;
    
    const running = await this.plugin.isServerRunning();
    
    statusEl.empty();
    statusEl.removeClass("status-online", "status-offline");
    
    if (running) {
      statusEl.addClass("status-online");
      statusEl.createSpan({ text: "● Server is running" });
    } else {
      statusEl.addClass("status-offline");
      statusEl.createSpan({ text: "● Server is offline" });
    }
  }

  hide(): void {
    // Cleanup on tab close
    if (this.refreshInterval) {
      window.clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }
}
```

### Status Bar Updates

```typescript
updateStatusBar(): void {
  if (!this.statusBarItem) return;
  
  this.isServerRunning().then(running => {
    if (running) {
      this.statusBarItem.setText("🤖 RAG ●");
      this.statusBarItem.addClass("status-online");
    } else {
      this.statusBarItem.setText("🤖 RAG ○");
      this.statusBarItem.addClass("status-offline");
    }
  });
}
```

---

## Backend CLI Integration

### Adding CLI Arguments

When plugin settings need to be passed to the backend:

```python
# cli/main.py
@app.command()
def serve(
    vault: Optional[str] = typer.Option(None, "--vault", "-v"),
    port: int = typer.Option(8000, "--port", "-p"),
    model: Optional[str] = typer.Option(None, "--model", "-m", 
        help="LLM model to use (e.g., gemma3, llama3.2)"),
    reranker: Optional[bool] = typer.Option(None, "--reranker/--no-reranker",
        help="Enable/disable reranker"),
):
    """Start the ObsidianRAG API server."""
    configure_from_vault(vault_path)
    
    # Override settings from CLI
    settings = get_settings()
    if model:
        settings.llm_model = model
    if reranker is not None:
        settings.use_reranker = reranker
    
    # Start server with configured settings
    run_server(host=host, port=port)
```

### Environment vs CLI Args

Priority order (highest to lowest):
1. CLI arguments (`--model llama3.2`)
2. Environment variables (`OBSIDIANRAG_LLM_MODEL`)
3. Config file (`.env` or `config.toml`)
4. Default values

---

## Error Handling Patterns

### Graceful Degradation

```typescript
async function fetchWithFallback<T>(
  primary: () => Promise<T>,
  fallback: T,
  errorMessage: string
): Promise<T> {
  try {
    return await primary();
  } catch (error) {
    console.warn(errorMessage, error);
    return fallback;
  }
}

// Usage
const models = await fetchWithFallback(
  () => this.getOllamaModels(),
  [],  // Empty array as fallback
  "Could not fetch Ollama models"
);
```

### Retry with Exponential Backoff

```typescript
async function fetchWithRetry<T>(
  fn: () => Promise<T>,
  maxAttempts: number = 3,
  baseDelay: number = 1000
): Promise<T> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt === maxAttempts) throw error;
      
      const delay = baseDelay * attempt;
      await new Promise(r => setTimeout(r, delay));
    }
  }
  throw new Error("Max attempts reached");
}
```

---

## Reset to Defaults Pattern

```typescript
async resetToDefaults(): Promise<void> {
  const keepSetupComplete = this.settings.hasCompletedSetup;
  
  this.settings = {
    pythonPath: "/usr/local/bin/obsidianrag-server",
    serverPort: 8000,
    llmModel: "gemma3",
    autoStartServer: true,
    showSourceLinks: true,
    useReranker: true,
    hasCompletedSetup: keepSetupComplete,  // Don't show wizard again
  };
  
  await this.saveSettings();
  new Notice("Settings reset to defaults");
}
```
