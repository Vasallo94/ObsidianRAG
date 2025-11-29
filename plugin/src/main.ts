/**
 * ObsidianRAG Plugin
 * 
 * Ask questions about your Obsidian notes using local AI.
 * Uses a Python backend (obsidianrag) with Ollama for LLM inference.
 */

import {
    App,
    ItemView,
    MarkdownRenderer,
    Notice,
    Plugin,
    PluginSettingTab,
    Setting,
    WorkspaceLeaf,
} from "obsidian";

// ============================================================================
// Constants
// ============================================================================

const VIEW_TYPE_CHAT = "obsidianrag-chat-view";
const DEFAULT_PORT = 8000;

// ============================================================================
// Interfaces
// ============================================================================

interface ObsidianRAGSettings {
  pythonPath: string;
  serverPort: number;
  llmModel: string;
  autoStartServer: boolean;
  showSourceLinks: boolean;
}

interface AskResponse {
  result: string;
  sources: Array<{ source: string; score: number; retrieval_type: string }>;
  question: string;
  process_time: number;
  session_id: string;
  error?: string;
}

interface HealthResponse {
  status: string;
  version: string;
  model: string;
}

interface SourceInfo {
  path: string;
  displayName: string;
  score: number;
  exists?: boolean;  // Whether the file exists in vault
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: SourceInfo[];
  timestamp: Date;
}

// Streaming event types
interface StreamEventStart {
  type: "start";
  session_id: string;
}

interface StreamEventStatus {
  type: "status";
  message: string;
}

interface StreamEventRetrieve {
  type: "retrieve_complete";
  docs_count: number;
  sources: Array<{ source: string; score: number }>;
}

interface StreamEventToken {
  type: "token";
  content: string;
}

interface StreamEventGenerate {
  type: "generate_complete";
  answer_preview: string;
}

interface StreamEventTTFT {
  type: "ttft";
  seconds: number;
}

interface StreamEventAnswer {
  type: "answer";
  question: string;
  answer: string;
  sources: Array<{ source: string; score: number; retrieval_type: string }>;
  process_time: number;
}

interface StreamEventError {
  type: "error";
  message: string;
}

interface StreamEventDone {
  type: "done";
}

type StreamEvent =
  | StreamEventStart
  | StreamEventStatus
  | StreamEventRetrieve
  | StreamEventToken
  | StreamEventTTFT
  | StreamEventGenerate
  | StreamEventAnswer
  | StreamEventError
  | StreamEventDone;

// ============================================================================
// Default Settings
// ============================================================================

const DEFAULT_SETTINGS: ObsidianRAGSettings = {
  pythonPath: "/usr/local/bin/obsidianrag-server",
  serverPort: DEFAULT_PORT,
  llmModel: "gemma3",
  autoStartServer: true,
  showSourceLinks: true,
};

// ============================================================================
// Main Plugin Class
// ============================================================================

export default class ObsidianRAGPlugin extends Plugin {
  settings: ObsidianRAGSettings;
  private serverProcess: any = null;
  private apiBaseUrl: string = "";

  async onload() {
    console.log("Loading ObsidianRAG plugin");

    await this.loadSettings();
    this.apiBaseUrl = `http://127.0.0.1:${this.settings.serverPort}`;

    // Register the chat view
    this.registerView(VIEW_TYPE_CHAT, (leaf) => new ChatView(leaf, this));

    // Add ribbon icon
    this.addRibbonIcon("message-circle", "ObsidianRAG Chat", () => {
      this.activateChatView();
    });

    // Add commands
    this.addCommand({
      id: "open-chat",
      name: "Open Chat",
      callback: () => this.activateChatView(),
    });

    this.addCommand({
      id: "start-server",
      name: "Start Backend Server",
      callback: () => this.startServer(),
    });

    this.addCommand({
      id: "stop-server",
      name: "Stop Backend Server",
      callback: () => this.stopServer(),
    });

    this.addCommand({
      id: "check-status",
      name: "Check Server Status",
      callback: () => this.checkServerStatus(),
    });

    // Add settings tab
    this.addSettingTab(new ObsidianRAGSettingTab(this.app, this));

    // Auto-start server if enabled
    if (this.settings.autoStartServer) {
      // Small delay to let Obsidian finish loading
      setTimeout(() => this.startServer(), 2000);
    }
  }

  async onunload() {
    console.log("Unloading ObsidianRAG plugin");
    await this.stopServer();
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
    this.apiBaseUrl = `http://127.0.0.1:${this.settings.serverPort}`;
  }

  // ==========================================================================
  // View Management
  // ==========================================================================

  async activateChatView() {
    const { workspace } = this.app;

    let leaf = workspace.getLeavesOfType(VIEW_TYPE_CHAT)[0];

    if (!leaf) {
      const rightLeaf = workspace.getRightLeaf(false);
      if (rightLeaf) {
        leaf = rightLeaf;
        await leaf.setViewState({ type: VIEW_TYPE_CHAT, active: true });
      }
    }

    if (leaf) {
      workspace.revealLeaf(leaf);
    }
  }

  // ==========================================================================
  // Server Management
  // ==========================================================================

  async startServer(): Promise<boolean> {
    // First check if already running
    if (await this.isServerRunning()) {
      new Notice("ObsidianRAG server is already running");
      return true;
    }

    new Notice("Starting ObsidianRAG server...");

    try {
      const vaultPath = (this.app.vault.adapter as any).basePath;
      const { spawn } = require("child_process");

      this.serverProcess = spawn(
        this.settings.pythonPath,
        [
          "serve",
          "--vault",
          vaultPath,
          "--port",
          String(this.settings.serverPort),
        ],
        {
          env: {
            ...process.env,
            OBSIDIANRAG_LLM_MODEL: this.settings.llmModel,
          },
          detached: false,
        }
      );

      this.serverProcess.stdout?.on("data", (data: Buffer) => {
        console.log(`[ObsidianRAG] ${data.toString()}`);
      });

      this.serverProcess.stderr?.on("data", (data: Buffer) => {
        console.error(`[ObsidianRAG] ${data.toString()}`);
      });

      this.serverProcess.on("error", (error: Error) => {
        console.error("[ObsidianRAG] Process error:", error);
        new Notice(`Failed to start server: ${error.message}`);
      });

      this.serverProcess.on("exit", (code: number) => {
        console.log(`[ObsidianRAG] Server exited with code ${code}`);
        this.serverProcess = null;
      });

      // Wait for server to be ready
      const ready = await this.waitForServer(30000);
      if (ready) {
        new Notice("ObsidianRAG server started successfully!");
        return true;
      } else {
        new Notice("Server started but not responding. Check logs.");
        return false;
      }
    } catch (error) {
      console.error("[ObsidianRAG] Failed to start server:", error);
      new Notice(`Failed to start server: ${error}`);
      return false;
    }
  }

  async stopServer(): Promise<void> {
    if (this.serverProcess) {
      this.serverProcess.kill();
      this.serverProcess = null;
      new Notice("ObsidianRAG server stopped");
    }
  }

  async isServerRunning(): Promise<boolean> {
    try {
      const response = await fetch(`${this.apiBaseUrl}/health`, {
        method: "GET",
        signal: AbortSignal.timeout(2000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  private async waitForServer(timeout: number): Promise<boolean> {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      if (await this.isServerRunning()) {
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    return false;
  }

  async checkServerStatus(): Promise<void> {
    try {
      const response = await fetch(`${this.apiBaseUrl}/health`);
      if (response.ok) {
        const data: HealthResponse = await response.json();
        new Notice(
          `Server OK\nVersion: ${data.version}\nModel: ${data.model}`
        );
      } else {
        new Notice("Server responded but with an error");
      }
    } catch {
      new Notice("Server is not running");
    }
  }

  // ==========================================================================
  // API Methods
  // ==========================================================================

  async askQuestion(question: string): Promise<AskResponse> {
    try {
      const response = await fetch(`${this.apiBaseUrl}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: question }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      return {
        result: "",
        sources: [],
        question: "",
        process_time: 0,
        session_id: "",
        error: `Failed to get answer: ${error}`,
      };
    }
  }

  /**
   * Ask a question with streaming - yields events as they come
   */
  async *askQuestionStreaming(
    question: string
  ): AsyncGenerator<StreamEvent, void, unknown> {
    try {
      const response = await fetch(`${this.apiBaseUrl}/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: question }),
      });

      if (!response.ok) {
        yield { type: "error", message: `Server error: ${response.status}` };
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        yield { type: "error", message: "No response body" };
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              yield data as StreamEvent;
            } catch {
              // Ignore parse errors
            }
          }
        }
      }
    } catch (error) {
      yield { type: "error", message: `Stream error: ${error}` };
    }
  }
}

// ============================================================================
// Chat View
// ============================================================================

class ChatView extends ItemView {
  plugin: ObsidianRAGPlugin;
  messages: ChatMessage[] = [];
  private containerEl_messages: HTMLElement;
  private inputEl: HTMLTextAreaElement;

  // Status element reference for periodic updates
  private statusEl: HTMLElement | null = null;
  private statusInterval: number | null = null;

  constructor(leaf: WorkspaceLeaf, plugin: ObsidianRAGPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_TYPE_CHAT;
  }

  getDisplayText(): string {
    return "ObsidianRAG Chat";
  }

  getIcon(): string {
    return "message-circle";
  }

  async onOpen() {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("obsidianrag-chat-container");

    // Header
    const header = container.createDiv("obsidianrag-header");
    header.createEl("h4", { text: "🤖 ObsidianRAG" });

    // Status indicator
    this.statusEl = header.createSpan("obsidianrag-status");
    this.updateStatus();

    // Start periodic status check (every 5 seconds)
    this.statusInterval = window.setInterval(() => this.updateStatus(), 5000);

    // Messages container
    this.containerEl_messages = container.createDiv("obsidianrag-messages");

    // Welcome message
    this.addMessage({
      role: "assistant",
      content:
        "Hello! I can answer questions about your notes. What would you like to know?",
      timestamp: new Date(),
    });

    // Input container
    const inputContainer = container.createDiv("obsidianrag-input-container");

    this.inputEl = inputContainer.createEl("textarea", {
      placeholder: "Ask a question about your notes...",
      cls: "obsidianrag-input",
    });

    const sendButton = inputContainer.createEl("button", {
      text: "Send",
      cls: "obsidianrag-send-button",
    });

    // Event handlers
    sendButton.addEventListener("click", () => this.sendMessage());

    this.inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });
  }

  async updateStatus() {
    if (!this.statusEl) return;
    
    const running = await this.plugin.isServerRunning();
    this.statusEl.empty();
    this.statusEl.removeClass("status-online", "status-offline");
    
    if (running) {
      this.statusEl.addClass("status-online");
      this.statusEl.setText("● Online");
    } else {
      this.statusEl.addClass("status-offline");
      this.statusEl.setText("● Offline");
    }
  }

  async sendMessage() {
    const question = this.inputEl.value.trim();
    if (!question) return;

    // Add user message
    this.addMessage({
      role: "user",
      content: question,
      timestamp: new Date(),
    });

    this.inputEl.value = "";

    // Check if server is running
    if (!(await this.plugin.isServerRunning())) {
      this.addMessage({
        role: "assistant",
        content:
          "⚠️ Server is not running. Use the command palette to start it, or enable auto-start in settings.",
        timestamp: new Date(),
      });
      return;
    }

    // Show progress element
    const progressEl = this.containerEl_messages.createDiv(
      "obsidianrag-message assistant loading"
    );
    const progressContent = progressEl.createDiv("progress-content");
    progressContent.innerHTML = "🔄 <strong>Starting...</strong>";

    // Track current step for animation
    const updateProgress = (step: string, details?: string) => {
      progressContent.innerHTML = `🔄 <strong>${step}</strong>${details ? `<br><span class="progress-details">${details}</span>` : ""}`;
      this.containerEl_messages.scrollTop = this.containerEl_messages.scrollHeight;
    };

    // For streaming tokens
    let streamingEl: HTMLElement | null = null;
    let streamingContent = "";
    let retrievedSources: Array<{ source: string; score: number }> = [];
    let ttftLogged = false;

    try {
      let finalAnswer: StreamEventAnswer | null = null;

      // Use streaming API
      for await (const event of this.plugin.askQuestionStreaming(question)) {
        switch (event.type) {
          case "start":
            updateProgress("Connecting...");
            break;

          case "status":
            updateProgress(event.message);
            break;

          case "retrieve_complete":
            retrievedSources = event.sources;
            updateProgress(
              `📚 Retrieved ${event.docs_count} documents`,
              event.sources.slice(0, 3).map((s) => 
                `• ${s.source.split("/").pop()?.replace(".md", "") || s.source}`
              ).join("<br>")
            );
            break;

          case "ttft":
            // Log Time To First Token
            console.log(`⚡ [ObsidianRAG] Time to First Token: ${event.seconds}s`);
            ttftLogged = true;
            break;

          case "token":
            // First token: switch from progress to streaming display
            if (!streamingEl) {
              progressEl.remove();
              streamingEl = this.containerEl_messages.createDiv(
                "obsidianrag-message assistant streaming"
              );
              const contentDiv = streamingEl.createDiv("message-content");
              contentDiv.createDiv("streaming-text streaming-content");
            }
            // Append token and render as markdown
            streamingContent += event.content;
            const textEl = streamingEl.querySelector(".streaming-text");
            if (textEl) {
              // Clear and re-render markdown for live preview
              (textEl as HTMLElement).empty();
              MarkdownRenderer.render(
                this.app,
                streamingContent,
                textEl as HTMLElement,
                "",
                this
              );
            }
            // Auto-scroll
            this.containerEl_messages.scrollTop = this.containerEl_messages.scrollHeight;
            break;

          case "generate_complete":
            // This may come if not using token streaming
            if (!streamingEl) {
              updateProgress(
                "✍️ Generating answer...",
                event.answer_preview.substring(0, 100) + "..."
              );
            }
            break;

          case "answer":
            finalAnswer = event;
            break;

          case "error":
            progressEl.remove();
            if (streamingEl) streamingEl.remove();
            this.addMessage({
              role: "assistant",
              content: `❌ Error: ${event.message}`,
              timestamp: new Date(),
            });
            return;

          case "done":
            break;
        }
      }

      // Remove progress if still showing
      if (progressEl.parentElement) {
        progressEl.remove();
      }

      // Add final answer with proper formatting
      if (finalAnswer) {
        const vaultPath = (this.app.vault.adapter as any).basePath;
        const sourcesWithScores: SourceInfo[] = [];
        
        for (const s of finalAnswer.sources || []) {
          let source = s.source;
          // Remove vault path prefix
          if (source.startsWith(vaultPath)) {
            source = source.substring(vaultPath.length);
            if (source.startsWith("/")) {
              source = source.substring(1);
            }
          }
          // Remove .md extension for display
          let displayPath = source;
          if (displayPath.endsWith(".md")) {
            displayPath = displayPath.substring(0, displayPath.length - 3);
          }
          
          // Verify the file exists in vault
          const fileWithMd = source.endsWith(".md") ? source : source + ".md";
          const file = this.app.vault.getAbstractFileByPath(fileWithMd) 
                    || this.app.vault.getAbstractFileByPath(source);
          
          if (file) {
            sourcesWithScores.push({
              path: displayPath,
              displayName: displayPath.split("/").pop() || displayPath,
              score: s.score,
              exists: true,
            });
          } else {
            // Try to find by name (case-insensitive search)
            const baseName = displayPath.split("/").pop() || displayPath;
            const allFiles = this.app.vault.getMarkdownFiles();
            const matchingFile = allFiles.find(f => 
              f.basename.toLowerCase() === baseName.toLowerCase()
            );
            
            if (matchingFile) {
              const matchPath = matchingFile.path.endsWith(".md") 
                ? matchingFile.path.substring(0, matchingFile.path.length - 3)
                : matchingFile.path;
              sourcesWithScores.push({
                path: matchPath,
                displayName: matchingFile.basename,
                score: s.score,
                exists: true,
              });
            } else {
              // File doesn't exist - still show but mark as non-existent
              // File doesn't exist - skip it entirely
              console.log(`[ObsidianRAG] Skipping non-existent source: ${displayPath}`);
            }
          }
        }

        const seen = new Set<string>();
        const uniqueSorted = sourcesWithScores
          .filter((s) => s.exists !== false)  // Only include existing files
          .sort((a, b) => b.score - a.score)
          .filter((s) => {
            if (seen.has(s.path)) return false;
            seen.add(s.path);
            return true;
          });

        // If we were streaming, upgrade the streaming element to final rendered markdown
        if (streamingEl) {
          // Remove streaming class and cursor animation
          streamingEl.removeClass("streaming");
          const textEl = streamingEl.querySelector(".streaming-text");
          if (textEl) {
            textEl.removeClass("streaming-content");
            // Re-render as proper markdown
            textEl.empty();
            MarkdownRenderer.render(
              this.app,
              finalAnswer.answer,
              textEl as HTMLElement,
              "",
              this
            );
          }
          
          // Add sources to the existing streaming element
          if (uniqueSorted.length > 0 && this.plugin.settings.showSourceLinks) {
            const sourcesEl = streamingEl.createDiv("message-sources");
            sourcesEl.createEl("strong", { text: "Sources (by relevance): " });

            uniqueSorted.forEach((source, i) => {
              if (i > 0) sourcesEl.appendText(" ");
              
              const sourceContainer = sourcesEl.createSpan("source-item");
              const scoreIndicator = this.getScoreIndicator(source.score);
              sourceContainer.appendText(scoreIndicator);
              
              if (source.exists !== false) {
                // File exists - create clickable link
                const link = sourceContainer.createEl("a", { 
                  text: source.displayName, 
                  cls: "internal-link" 
                });
                link.addEventListener("click", (e) => {
                  e.preventDefault();
                  this.app.workspace.openLinkText(source.path, "");
                });
              } else {
                // File doesn't exist - just show text (no link)
                sourceContainer.createSpan({ 
                  text: source.displayName,
                  cls: "source-not-found"
                });
              }
            });
          }
          
          // Store message in history
          this.messages.push({
            role: "assistant",
            content: finalAnswer.answer,
            sources: uniqueSorted,
            timestamp: new Date(),
          });
        } else {
          // No streaming happened, add message normally
          this.addMessage({
            role: "assistant",
            content: finalAnswer.answer,
            sources: uniqueSorted,
            timestamp: new Date(),
          });
        }
      }
    } catch (error) {
      progressEl.remove();
      this.addMessage({
        role: "assistant",
        content: `❌ Error: ${error}`,
        timestamp: new Date(),
      });
    }
  }

  addMessage(message: ChatMessage) {
    this.messages.push(message);

    const messageEl = this.containerEl_messages.createDiv(
      `obsidianrag-message ${message.role}`
    );

    // Render content as markdown (use empty sourcePath to prevent internal link resolution)
    const contentEl = messageEl.createDiv("message-content");
    MarkdownRenderer.render(
      this.app,
      message.content,
      contentEl,
      "",
      this
    );

    // Add sources if present (already sorted by relevance)
    if (
      message.sources &&
      message.sources.length > 0 &&
      this.plugin.settings.showSourceLinks
    ) {
      const sourcesEl = messageEl.createDiv("message-sources");
      sourcesEl.createEl("strong", { text: "Sources (by relevance): " });

      message.sources.forEach((source, i) => {
        if (i > 0) sourcesEl.appendText(" ");
        
        // Create a container for each source with score indicator
        const sourceContainer = sourcesEl.createSpan("source-item");
        
        // Add relevance indicator (emoji based on score)
        const scoreIndicator = this.getScoreIndicator(source.score);
        sourceContainer.appendText(scoreIndicator);
        
        if (source.exists !== false) {
          // File exists - create clickable link
          const link = sourceContainer.createEl("a", { 
            text: source.displayName, 
            cls: "internal-link" 
          });
          link.setAttribute("title", `Relevance: ${(source.score * 100).toFixed(1)}%`);
          link.addEventListener("click", (e) => {
            e.preventDefault();
            this.app.workspace.openLinkText(source.path, "");
          });
        } else {
          // File doesn't exist - just show text
          const span = sourceContainer.createSpan({ 
            text: source.displayName,
            cls: "source-not-found"
          });
          span.setAttribute("title", `File not found in vault`);
        }
      });
    }

    // Scroll to bottom
    this.containerEl_messages.scrollTop =
      this.containerEl_messages.scrollHeight;
  }

  /**
   * Get an emoji indicator based on the relevance score
   */
  getScoreIndicator(score: number): string {
    if (score >= 0.8) return "🟢";      // High relevance
    if (score >= 0.6) return "🟡";      // Medium-high relevance
    if (score >= 0.4) return "🟠";      // Medium relevance
    return "🔴";                         // Lower relevance
  }

  async onClose() {
    // Cleanup periodic status check
    if (this.statusInterval) {
      window.clearInterval(this.statusInterval);
      this.statusInterval = null;
    }
    this.statusEl = null;
  }
}

// ============================================================================
// Settings Tab
// ============================================================================

class ObsidianRAGSettingTab extends PluginSettingTab {
  plugin: ObsidianRAGPlugin;

  constructor(app: App, plugin: ObsidianRAGPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "ObsidianRAG Settings" });

    // Python Path
    new Setting(containerEl)
      .setName("ObsidianRAG Command")
      .setDesc("Path to obsidianrag-server script or command")
      .addText((text) =>
        text
          .setPlaceholder("/usr/local/bin/obsidianrag-server")
          .setValue(this.plugin.settings.pythonPath)
          .onChange(async (value) => {
            this.plugin.settings.pythonPath = value;
            await this.plugin.saveSettings();
          })
      );

    // Server Port
    new Setting(containerEl)
      .setName("Server Port")
      .setDesc("Port for the backend API server")
      .addText((text) =>
        text
          .setPlaceholder("8000")
          .setValue(String(this.plugin.settings.serverPort))
          .onChange(async (value) => {
            const port = parseInt(value) || DEFAULT_PORT;
            this.plugin.settings.serverPort = port;
            await this.plugin.saveSettings();
          })
      );

    // LLM Model
    new Setting(containerEl)
      .setName("LLM Model")
      .setDesc("Ollama model to use for answering questions")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("gemma3", "Gemma 3 (recommended)")
          .addOption("llama3.2", "Llama 3.2")
          .addOption("mistral", "Mistral")
          .addOption("qwen2.5", "Qwen 2.5")
          .addOption("phi3", "Phi 3")
          .setValue(this.plugin.settings.llmModel)
          .onChange(async (value) => {
            this.plugin.settings.llmModel = value;
            await this.plugin.saveSettings();
          })
      );

    // Auto-start
    new Setting(containerEl)
      .setName("Auto-start Server")
      .setDesc("Automatically start the backend when Obsidian opens")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.autoStartServer)
          .onChange(async (value) => {
            this.plugin.settings.autoStartServer = value;
            await this.plugin.saveSettings();
          })
      );

    // Show sources
    new Setting(containerEl)
      .setName("Show Source Links")
      .setDesc("Display links to source notes in answers")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.showSourceLinks)
          .onChange(async (value) => {
            this.plugin.settings.showSourceLinks = value;
            await this.plugin.saveSettings();
          })
      );

    // Server controls
    containerEl.createEl("h3", { text: "Server Controls" });

    new Setting(containerEl)
      .setName("Start Server")
      .setDesc("Manually start the backend server")
      .addButton((button) =>
        button.setButtonText("Start").onClick(async () => {
          await this.plugin.startServer();
        })
      );

    new Setting(containerEl)
      .setName("Stop Server")
      .setDesc("Stop the backend server")
      .addButton((button) =>
        button.setButtonText("Stop").onClick(async () => {
          await this.plugin.stopServer();
        })
      );

    new Setting(containerEl)
      .setName("Check Status")
      .setDesc("Check if the server is running")
      .addButton((button) =>
        button.setButtonText("Check").onClick(async () => {
          await this.plugin.checkServerStatus();
        })
      );

    // Help section
    containerEl.createEl("h3", { text: "Requirements" });
    const helpEl = containerEl.createEl("div", { cls: "setting-item-description" });
    helpEl.innerHTML = `
      <p>This plugin requires:</p>
      <ul>
        <li><strong>Python 3.11+</strong> installed and accessible</li>
        <li><strong>obsidianrag</strong> package: <code>pip install obsidianrag</code></li>
        <li><strong>Ollama</strong> running locally with at least one model</li>
      </ul>
      <p>Install Ollama from <a href="https://ollama.ai">ollama.ai</a></p>
    `;
  }
}
