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
  Modal,
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
const MAX_RETRY_ATTEMPTS = 3;
const RETRY_DELAY_MS = 1000;

// ============================================================================
// Interfaces
// ============================================================================

interface ObsidianRAGSettings {
  pythonPath: string;
  serverPort: number;
  llmModel: string;
  autoStartServer: boolean;
  showSourceLinks: boolean;
  useReranker: boolean;
  hasCompletedSetup: boolean;
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
  useReranker: true,
  hasCompletedSetup: false,
};

// ============================================================================
// Stats Response Interface
// ============================================================================

interface StatsResponse {
  total_notes: number;
  total_chunks: number;
  total_words: number;
  total_chars: number;
  avg_words_per_chunk: number;
  folders: number;
  internal_links: number;
  vault_path: string;
  error?: string;
}

// ============================================================================
// Ollama Models Interface
// ============================================================================

interface OllamaModel {
  name: string;
  modified_at: string;
  size: number;
}

interface OllamaModelsResponse {
  models: OllamaModel[];
}

// ============================================================================
// Main Plugin Class
// ============================================================================

export default class ObsidianRAGPlugin extends Plugin {
  settings!: ObsidianRAGSettings;
  private serverProcess: any = null;
  private apiBaseUrl: string = "";
  private restartAttempts: number = 0;
  private maxRestartAttempts: number = 3;
  private isRestarting: boolean = false;
  statusBarItem: HTMLElement | null = null;

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

    // Add status bar item
    this.statusBarItem = this.addStatusBarItem();
    this.statusBarItem.addClass("obsidianrag-status-bar");
    this.updateStatusBar();

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

    this.addCommand({
      id: "ask-question",
      name: "Ask a Question",
      callback: () => new AskQuestionModal(this.app, this).open(),
    });

    this.addCommand({
      id: "reindex-vault",
      name: "Reindex Vault",
      callback: () => this.reindexVault(),
    });

    // Add settings tab
    this.addSettingTab(new ObsidianRAGSettingTab(this.app, this));

    // Show setup modal on first run
    if (!this.settings.hasCompletedSetup) {
      new SetupModal(this.app, this).open();
    }

    // Auto-start server if enabled
    if (this.settings.autoStartServer) {
      // Small delay to let Obsidian finish loading
      setTimeout(() => this.startServer(), 2000);
    }

    // Start status bar update interval
    this.registerInterval(
      window.setInterval(() => this.updateStatusBar(), 10000)
    );
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
  // Status Bar
  // ==========================================================================

  async updateStatusBar() {
    if (!this.statusBarItem) return;
    
    const running = await this.isServerRunning();
    this.statusBarItem.empty();
    
    if (running) {
      this.statusBarItem.setText("🤖 RAG ●");
      this.statusBarItem.setAttribute("title", "ObsidianRAG: Online - Click to open chat");
      this.statusBarItem.addClass("status-online");
      this.statusBarItem.removeClass("status-offline");
    } else {
      this.statusBarItem.setText("🤖 RAG ○");
      this.statusBarItem.setAttribute("title", "ObsidianRAG: Offline - Click to start server");
      this.statusBarItem.addClass("status-offline");
      this.statusBarItem.removeClass("status-online");
    }
    
    // Make status bar clickable
    this.statusBarItem.onClickEvent(() => {
      if (running) {
        this.activateChatView();
      } else {
        this.startServer();
      }
    });
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
      const platform = process.platform;

      // Get platform-specific spawn options
      const spawnOptions = this.getSpawnOptionsForPlatform(platform);

      // Prepare the command based on platform
      let command: string;
      let args: string[];

      if (platform === 'win32') {
        // On Windows, we need to use shell and handle paths differently
        command = this.settings.pythonPath;
        args = [
          "serve",
          "--vault",
          `"${vaultPath}"`, // Quote path for Windows
          "--port",
          String(this.settings.serverPort),
          "--model",
          this.settings.llmModel,
          this.settings.useReranker ? "--reranker" : "--no-reranker",
        ];
      } else {
        // macOS and Linux
        command = this.settings.pythonPath;
        args = [
          "serve",
          "--vault",
          vaultPath,
          "--port",
          String(this.settings.serverPort),
          "--model",
          this.settings.llmModel,
          this.settings.useReranker ? "--reranker" : "--no-reranker",
        ];
      }

      this.serverProcess = spawn(command, args, spawnOptions);

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
        // Auto-restart if enabled and not manually stopped
        if (this.settings.autoStartServer && !this.isRestarting) {
          this.handleServerCrash(code);
        }
      });

      // Wait for server to be ready
      const ready = await this.waitForServer(30000);
      if (ready) {
        this.restartAttempts = 0; // Reset on successful start
        new Notice("ObsidianRAG server started successfully!");
        this.updateStatusBar();
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

  private async handleServerCrash(exitCode: number): Promise<void> {
    if (this.restartAttempts >= this.maxRestartAttempts) {
      new Notice(`Server crashed ${this.maxRestartAttempts} times. Please check logs and restart manually.`);
      this.restartAttempts = 0;
      return;
    }

    this.restartAttempts++;
    this.isRestarting = true;
    
    const delay = RETRY_DELAY_MS * this.restartAttempts; // Exponential backoff
    new Notice(`Server exited with code ${exitCode}. Restarting in ${delay/1000}s... (attempt ${this.restartAttempts}/${this.maxRestartAttempts})`);
    
    await new Promise(resolve => setTimeout(resolve, delay));
    
    this.isRestarting = false;
    await this.startServer();
  }

  async stopServer(): Promise<void> {
    this.isRestarting = true; // Prevent auto-restart
    
    // First, try to kill the tracked process
    if (this.serverProcess) {
      this.serverProcess.kill();
      this.serverProcess = null;
    }
    
    // Also try to kill any process on the port (in case server was started externally)
    try {
      const { exec } = require("child_process");
      const platform = process.platform;
      
      if (platform === 'win32') {
        // Windows: use netstat and taskkill
        exec(`for /f "tokens=5" %a in ('netstat -aon ^| find ":${this.settings.serverPort}" ^| find "LISTENING"') do taskkill /F /PID %a`, 
          (error: Error | null) => {
            if (error) console.log("[ObsidianRAG] No process found on port (Windows)");
          });
      } else {
        // macOS/Linux: use lsof and kill
        exec(`lsof -ti:${this.settings.serverPort} | xargs kill -9 2>/dev/null`, 
          (error: Error | null) => {
            if (error) console.log("[ObsidianRAG] No process found on port");
          });
      }
    } catch (e) {
      console.log("[ObsidianRAG] Could not kill process by port:", e);
    }
    
    new Notice("ObsidianRAG server stopped");
    this.isRestarting = false;
    this.updateStatusBar();
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

  /**
   * Fetch available models from Ollama
   */
  async getOllamaModels(): Promise<string[]> {
    try {
      const response = await fetch("http://localhost:11434/api/tags", {
        method: "GET",
        signal: AbortSignal.timeout(5000),
      });
      
      if (!response.ok) {
        console.warn("[ObsidianRAG] Failed to fetch Ollama models");
        return [];
      }
      
      const data: OllamaModelsResponse = await response.json();
      // Extract model names (remove :latest suffix for cleaner display)
      return data.models.map(m => m.name.replace(":latest", ""));
    } catch (error) {
      console.warn("[ObsidianRAG] Ollama not available:", error);
      return [];
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

  /**
   * Get vault statistics from the server
   */
  async getStats(): Promise<StatsResponse | null> {
    return await this.fetchWithRetry<StatsResponse>(`${this.apiBaseUrl}/stats`);
  }

  /**
   * Trigger vault reindexing
   */
  async reindexVault(): Promise<boolean> {
    if (!(await this.isServerRunning())) {
      new Notice("Server is not running. Start it first.");
      return false;
    }

    new Notice("Reindexing vault... This may take a while.");
    
    try {
      const response = await fetch(`${this.apiBaseUrl}/rebuild_db`, {
        method: "POST",
        signal: AbortSignal.timeout(300000), // 5 min timeout for large vaults
      });

      if (response.ok) {
        const data = await response.json();
        new Notice(`Reindexing complete! Indexed ${data.total_chunks || 'unknown'} chunks.`);
        return true;
      } else {
        new Notice(`Reindexing failed: ${response.status}`);
        return false;
      }
    } catch (error) {
      new Notice(`Reindexing failed: ${error}`);
      return false;
    }
  }

  /**
   * Fetch with retry logic
   */
  private async fetchWithRetry<T>(
    url: string,
    options: RequestInit = {},
    attempts: number = MAX_RETRY_ATTEMPTS
  ): Promise<T | null> {
    let lastError: Error | null = null;

    for (let i = 0; i < attempts; i++) {
      try {
        const response = await fetch(url, {
          ...options,
          signal: AbortSignal.timeout(10000),
        });

        if (response.ok) {
          return await response.json();
        }
        
        lastError = new Error(`HTTP ${response.status}`);
      } catch (error) {
        lastError = error as Error;
        // Wait before retry with exponential backoff
        if (i < attempts - 1) {
          await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS * (i + 1)));
        }
      }
    }

    console.error(`[ObsidianRAG] Failed after ${attempts} attempts:`, lastError);
    return null;
  }

  /**
   * Get platform-specific spawn options
   */
  getSpawnOptionsForPlatform(platform: string): { 
    shell: boolean; 
    env: NodeJS.ProcessEnv;
    windowsHide?: boolean;
  } {
    const env = { 
      ...process.env, 
      OBSIDIANRAG_LLM_MODEL: this.settings.llmModel,
      OBSIDIANRAG_USE_RERANKER: this.settings.useReranker ? "true" : "false",
    };

    if (platform === 'win32') {
      // Windows: use shell for proper command resolution, hide console window
      return { 
        shell: true, 
        env,
        windowsHide: true,
      };
    } else if (platform === 'linux') {
      // Linux: similar to macOS but may need different shell handling
      return { 
        shell: false, 
        env,
      };
    } else {
      // macOS and others
      return { 
        shell: false, 
        env,
      };
    }
  }

  /**
   * Get default Python command based on platform
   */
  getDefaultPythonCommand(): string {
    const platform = process.platform;
    
    if (platform === 'win32') {
      // Windows: try py launcher first, then python
      return 'py -m obsidianrag';
    } else if (platform === 'linux') {
      // Linux: usually python3
      return 'python3 -m obsidianrag';
    } else {
      // macOS: could be python3 or the obsidianrag-server wrapper
      return '/usr/local/bin/obsidianrag-server';
    }
  }
}

// ============================================================================
// Modals
// ============================================================================

/**
 * Setup Modal - First-time setup wizard
 */
class SetupModal extends Modal {
  plugin: ObsidianRAGPlugin;
  private currentStep: number = 0;
  private contentEl_modal!: HTMLElement;
  private availableModels: string[] = [];

  constructor(app: App, plugin: ObsidianRAGPlugin) {
    super(app);
    this.plugin = plugin;
  }

  async onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("obsidianrag-setup-modal");

    contentEl.createEl("h2", { text: "🤖 Welcome to ObsidianRAG!" });

    // Fetch available models
    this.availableModels = await this.plugin.getOllamaModels();

    this.contentEl_modal = contentEl.createDiv("setup-content");
    this.showStep(0);
  }

  showStep(step: number) {
    this.currentStep = step;
    this.contentEl_modal.empty();

    const steps = [
      this.renderRequirements.bind(this),
      this.renderConfiguration.bind(this),
      this.renderComplete.bind(this),
    ];

    if (step < steps.length) {
      steps[step]();
    }
  }

  renderRequirements() {
    const el = this.contentEl_modal;
    
    el.createEl("h3", { text: "Step 1: Check Requirements" });
    
    const requirements = el.createEl("ul");
    requirements.createEl("li").innerHTML = "<strong>Python 3.11+</strong> - Required for the backend";
    requirements.createEl("li").innerHTML = "<strong>obsidianrag</strong> package - <code>pip install obsidianrag</code>";
    requirements.createEl("li").innerHTML = "<strong>Ollama</strong> - Local LLM server from <a href='https://ollama.ai'>ollama.ai</a>";
    requirements.createEl("li").innerHTML = "At least one Ollama model - <code>ollama pull gemma3</code>";

    el.createEl("p", { 
      text: "Make sure you have all requirements installed before proceeding.",
      cls: "setting-item-description"
    });

    const buttons = el.createDiv("modal-button-container");
    
    const nextBtn = buttons.createEl("button", { text: "Next →", cls: "mod-cta" });
    nextBtn.addEventListener("click", () => this.showStep(1));

    const skipBtn = buttons.createEl("button", { text: "Skip Setup" });
    skipBtn.addEventListener("click", () => this.completeSetup());
  }

  renderConfiguration() {
    const el = this.contentEl_modal;
    
    el.createEl("h3", { text: "Step 2: Configuration" });

    // Server command
    new Setting(el)
      .setName("Backend Command")
      .setDesc("Path to obsidianrag-server or 'obsidianrag' if installed globally")
      .addText(text => text
        .setValue(this.plugin.settings.pythonPath)
        .onChange(async (value) => {
          this.plugin.settings.pythonPath = value;
          await this.plugin.saveSettings();
        }));

    // Port
    new Setting(el)
      .setName("Server Port")
      .addText(text => text
        .setValue(String(this.plugin.settings.serverPort))
        .onChange(async (value) => {
          this.plugin.settings.serverPort = parseInt(value) || DEFAULT_PORT;
          await this.plugin.saveSettings();
        }));

    // Model - populated from Ollama
    const modelSetting = new Setting(el)
      .setName("LLM Model");
    
    if (this.availableModels.length > 0) {
      modelSetting.addDropdown(dropdown => {
        this.availableModels.forEach(model => {
          dropdown.addOption(model, model);
        });
        
        // Set current value, or first available if current not in list
        const currentModel = this.plugin.settings.llmModel;
        if (this.availableModels.includes(currentModel)) {
          dropdown.setValue(currentModel);
        } else if (this.availableModels.length > 0) {
          dropdown.setValue(this.availableModels[0]);
          this.plugin.settings.llmModel = this.availableModels[0];
          this.plugin.saveSettings();
        }
        
        dropdown.onChange(async (value) => {
          this.plugin.settings.llmModel = value;
          await this.plugin.saveSettings();
        });
      });
    } else {
      modelSetting
        .setDesc("⚠️ Ollama not detected. Make sure Ollama is running.")
        .addText(text => text
          .setPlaceholder("gemma3")
          .setValue(this.plugin.settings.llmModel)
          .onChange(async (value) => {
            this.plugin.settings.llmModel = value;
            await this.plugin.saveSettings();
          }));
    }

    // Auto-start
    new Setting(el)
      .setName("Auto-start server")
      .setDesc("Start the backend automatically when Obsidian opens")
      .addToggle(toggle => toggle
        .setValue(this.plugin.settings.autoStartServer)
        .onChange(async (value) => {
          this.plugin.settings.autoStartServer = value;
          await this.plugin.saveSettings();
        }));

    const buttons = el.createDiv("modal-button-container");
    
    const backBtn = buttons.createEl("button", { text: "← Back" });
    backBtn.addEventListener("click", () => this.showStep(0));

    const nextBtn = buttons.createEl("button", { text: "Finish →", cls: "mod-cta" });
    nextBtn.addEventListener("click", () => this.showStep(2));
  }

  renderComplete() {
    const el = this.contentEl_modal;
    
    el.createEl("h3", { text: "✅ Setup Complete!" });
    el.createEl("p", { text: "You're all set to use ObsidianRAG." });

    const tips = el.createEl("ul");
    tips.createEl("li", { text: "Click the 🤖 icon in the ribbon to open the chat" });
    tips.createEl("li", { text: "Use Cmd/Ctrl+P and search 'ObsidianRAG' for all commands" });
    tips.createEl("li", { text: "First question may take a moment while the vault is indexed" });

    const buttons = el.createDiv("modal-button-container");
    
    const startBtn = buttons.createEl("button", { text: "Start Server & Open Chat", cls: "mod-cta" });
    startBtn.addEventListener("click", async () => {
      await this.plugin.startServer();
      this.completeSetup();
      this.plugin.activateChatView();
    });

    const laterBtn = buttons.createEl("button", { text: "Maybe Later" });
    laterBtn.addEventListener("click", () => this.completeSetup());
  }

  async completeSetup() {
    this.plugin.settings.hasCompletedSetup = true;
    await this.plugin.saveSettings();
    this.close();
  }

  onClose() {
    const { contentEl } = this;
    contentEl.empty();
  }
}

/**
 * Ask Question Modal - Quick question from command palette
 */
class AskQuestionModal extends Modal {
  plugin: ObsidianRAGPlugin;
  private inputEl!: HTMLTextAreaElement;
  private resultEl!: HTMLElement;

  constructor(app: App, plugin: ObsidianRAGPlugin) {
    super(app);
    this.plugin = plugin;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("obsidianrag-ask-modal");

    contentEl.createEl("h2", { text: "🤖 Ask ObsidianRAG" });

    // Input
    this.inputEl = contentEl.createEl("textarea", {
      placeholder: "Ask a question about your notes...",
      cls: "obsidianrag-modal-input"
    });

    // Buttons
    const buttonContainer = contentEl.createDiv("modal-button-container");
    
    const askBtn = buttonContainer.createEl("button", { text: "Ask", cls: "mod-cta" });
    askBtn.addEventListener("click", () => this.askQuestion());

    const openChatBtn = buttonContainer.createEl("button", { text: "Open Full Chat" });
    openChatBtn.addEventListener("click", () => {
      this.close();
      this.plugin.activateChatView();
    });

    // Result area
    this.resultEl = contentEl.createDiv("obsidianrag-modal-result");

    // Focus input
    this.inputEl.focus();

    // Enter to submit
    this.inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.askQuestion();
      }
    });
  }

  async askQuestion() {
    const question = this.inputEl.value.trim();
    if (!question) return;

    if (!(await this.plugin.isServerRunning())) {
      this.resultEl.setText("⚠️ Server is not running. Start it first.");
      return;
    }

    this.resultEl.empty();
    this.resultEl.createDiv({ text: "🔄 Thinking...", cls: "loading" });

    try {
      let answer = "";
      for await (const event of this.plugin.askQuestionStreaming(question)) {
        if (event.type === "token") {
          answer += event.content;
        } else if (event.type === "answer") {
          answer = event.answer;
        } else if (event.type === "error") {
          this.resultEl.setText(`❌ ${event.message}`);
          return;
        }
      }

      this.resultEl.empty();
      MarkdownRenderer.render(
        this.app,
        answer,
        this.resultEl,
        "",
        this.plugin
      );
    } catch (error) {
      this.resultEl.setText(`❌ Error: ${error}`);
    }
  }

  onClose() {
    const { contentEl } = this;
    contentEl.empty();
  }
}

/**
 * Error Modal - Display errors with helpful suggestions
 */
class ErrorModal extends Modal {
  title: string;
  message: string;
  suggestions: string[];

  constructor(app: App, title: string, message: string, suggestions: string[] = []) {
    super(app);
    this.title = title;
    this.message = message;
    this.suggestions = suggestions;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("obsidianrag-error-modal");

    contentEl.createEl("h2", { text: `❌ ${this.title}` });
    contentEl.createEl("p", { text: this.message, cls: "error-message" });

    if (this.suggestions.length > 0) {
      contentEl.createEl("h4", { text: "Suggestions:" });
      const list = contentEl.createEl("ul");
      this.suggestions.forEach(s => list.createEl("li", { text: s }));
    }

    const buttons = contentEl.createDiv("modal-button-container");
    const okBtn = buttons.createEl("button", { text: "OK", cls: "mod-cta" });
    okBtn.addEventListener("click", () => this.close());
  }

  onClose() {
    const { contentEl } = this;
    contentEl.empty();
  }
}

// ============================================================================
// Chat View
// ============================================================================

class ChatView extends ItemView {
  plugin: ObsidianRAGPlugin;
  messages: ChatMessage[] = [];
  private containerEl_messages!: HTMLElement;
  private inputEl!: HTMLTextAreaElement;

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

    // Header controls
    const headerControls = header.createDiv("obsidianrag-header-controls");

    // Reindex button
    const reindexBtn = headerControls.createEl("button", {
      cls: "obsidianrag-header-btn",
      attr: { "aria-label": "Reindex vault" }
    });
    reindexBtn.innerHTML = "🔄";
    reindexBtn.addEventListener("click", async () => {
      await this.plugin.reindexVault();
    });

    // Clear history button
    const clearBtn = headerControls.createEl("button", {
      cls: "obsidianrag-header-btn",
      attr: { "aria-label": "Clear chat history" }
    });
    clearBtn.innerHTML = "🗑️";
    clearBtn.addEventListener("click", () => this.clearHistory());

    // Status indicator
    this.statusEl = headerControls.createSpan("obsidianrag-status");
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

  clearHistory() {
    this.messages = [];
    this.containerEl_messages.empty();
    this.addMessage({
      role: "assistant",
      content: "Chat history cleared. How can I help you?",
      timestamp: new Date(),
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
  private statusRefreshInterval: number | null = null;
  private availableModels: string[] = [];

  constructor(app: App, plugin: ObsidianRAGPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  async display(): Promise<void> {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "ObsidianRAG Settings" });

    // Fetch available models from Ollama
    this.availableModels = await this.plugin.getOllamaModels();

    // Server Status Section (live)
    this.renderServerStatus(containerEl);

    // Configuration Section
    containerEl.createEl("h3", { text: "Configuration" });

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

    // LLM Model - dynamically populated from Ollama
    const modelSetting = new Setting(containerEl)
      .setName("LLM Model")
      .setDesc("Ollama model to use for answering questions");

    if (this.availableModels.length > 0) {
      modelSetting.addDropdown((dropdown) => {
        // Add all available models from Ollama
        this.availableModels.forEach(model => {
          dropdown.addOption(model, model);
        });
        
        // Set current value, or first available if current not in list
        const currentModel = this.plugin.settings.llmModel;
        if (this.availableModels.includes(currentModel)) {
          dropdown.setValue(currentModel);
        } else if (this.availableModels.length > 0) {
          // Current model not available, switch to first available
          dropdown.setValue(this.availableModels[0]);
          this.plugin.settings.llmModel = this.availableModels[0];
          this.plugin.saveSettings();
          new Notice(`Model '${currentModel}' not found. Switched to '${this.availableModels[0]}'`);
        }
        
        dropdown.onChange(async (value) => {
          this.plugin.settings.llmModel = value;
          await this.plugin.saveSettings();
        });
      });
    } else {
      // Ollama not available - show warning and text input
      modelSetting
        .setDesc("⚠️ Could not connect to Ollama. Make sure Ollama is running (ollama serve).")
        .addText((text) =>
          text
            .setPlaceholder("gemma3")
            .setValue(this.plugin.settings.llmModel)
            .onChange(async (value) => {
              this.plugin.settings.llmModel = value;
              await this.plugin.saveSettings();
            })
        );
    }

    // RAG Settings Section
    containerEl.createEl("h3", { text: "RAG Settings" });

    // Use Reranker
    new Setting(containerEl)
      .setName("Use Reranker")
      .setDesc("Enable CrossEncoder reranking for better relevance (slower but more accurate)")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.useReranker)
          .onChange(async (value) => {
            this.plugin.settings.useReranker = value;
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
          this.display(); // Refresh status
        })
      );

    new Setting(containerEl)
      .setName("Stop Server")
      .setDesc("Stop the backend server")
      .addButton((button) =>
        button.setButtonText("Stop").onClick(async () => {
          await this.plugin.stopServer();
          this.display(); // Refresh status
        })
      );

    new Setting(containerEl)
      .setName("Reindex Vault")
      .setDesc("Force reindex all notes in the vault")
      .addButton((button) =>
        button
          .setButtonText("Reindex")
          .setWarning()
          .onClick(async () => {
            await this.plugin.reindexVault();
          })
      );

    // Vault Statistics Section
    this.renderVaultStats(containerEl);

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

    // Reset Setup
    containerEl.createEl("h3", { text: "Advanced" });
    
    new Setting(containerEl)
      .setName("Reset to Defaults")
      .setDesc("Reset all settings to their default values")
      .addButton((button) =>
        button
          .setButtonText("Reset All Settings")
          .setWarning()
          .onClick(async () => {
            // Keep hasCompletedSetup true so wizard doesn't show again
            const keepSetupComplete = this.plugin.settings.hasCompletedSetup;
            
            // Reset to defaults
            this.plugin.settings = {
              pythonPath: "/usr/local/bin/obsidianrag-server",
              serverPort: 8000,
              llmModel: "gemma3",
              autoStartServer: true,
              showSourceLinks: true,
              useReranker: true,
              hasCompletedSetup: keepSetupComplete,
            };
            
            await this.plugin.saveSettings();
            new Notice("Settings reset to defaults");
            this.display(); // Refresh the settings page
          })
      );

    new Setting(containerEl)
      .setName("Reset Setup Wizard")
      .setDesc("Show the setup wizard again on next reload")
      .addButton((button) =>
        button
          .setButtonText("Reset Wizard")
          .onClick(async () => {
            this.plugin.settings.hasCompletedSetup = false;
            await this.plugin.saveSettings();
            new Notice("Setup wizard will show on next reload");
          })
      );
  }

  private async renderServerStatus(containerEl: HTMLElement) {
    const statusContainer = containerEl.createDiv("obsidianrag-settings-status");
    statusContainer.createEl("h3", { text: "Server Status" });
    
    const statusEl = statusContainer.createDiv("status-display");
    
    // Initial render
    await this.updateServerStatusDisplay(statusEl);
    
    // Set up periodic refresh (every 3 seconds)
    if (this.statusRefreshInterval) {
      window.clearInterval(this.statusRefreshInterval);
    }
    this.statusRefreshInterval = window.setInterval(async () => {
      await this.updateServerStatusDisplay(statusEl);
    }, 3000);
  }

  private async updateServerStatusDisplay(statusEl: HTMLElement): Promise<void> {
    const running = await this.plugin.isServerRunning();
    
    // Clear previous classes and content
    statusEl.removeClass("status-online", "status-offline");
    statusEl.empty();
    
    if (running) {
      statusEl.addClass("status-online");
      statusEl.createSpan({ cls: "status-indicator", text: "●" });
      statusEl.createSpan({ cls: "status-text", text: " Server is running" });
      
      // Fetch and display health info
      try {
        const response = await fetch(`http://127.0.0.1:${this.plugin.settings.serverPort}/health`);
        if (response.ok) {
          const health: HealthResponse = await response.json();
          const detailsEl = statusEl.createDiv("status-details");
          detailsEl.createDiv({ text: `Version: ${health.version || "unknown"}` });
          detailsEl.createDiv({ text: `Model: ${health.model || "unknown"}` });
        }
      } catch {
        // Ignore fetch errors
      }
    } else {
      statusEl.addClass("status-offline");
      statusEl.createSpan({ cls: "status-indicator", text: "●" });
      statusEl.createSpan({ cls: "status-text", text: " Server is offline" });
    }
  }

  private async renderVaultStats(containerEl: HTMLElement) {
    containerEl.createEl("h3", { text: "Vault Statistics" });
    
    const statsContainer = containerEl.createDiv("obsidianrag-vault-stats");
    
    const running = await this.plugin.isServerRunning();
    
    if (!running) {
      statsContainer.setText("Start the server to view vault statistics.");
      return;
    }
    
    statsContainer.setText("Loading statistics...");
    
    const stats = await this.plugin.getStats();
    
    if (stats && !stats.error) {
      statsContainer.empty();
      const table = statsContainer.createEl("table", { cls: "stats-table" });
      
      const rows = [
        ["Total Notes", String(stats.total_notes)],
        ["Total Chunks", String(stats.total_chunks)],
        ["Total Words", String(stats.total_words).replace(/\B(?=(\d{3})+(?!\d))/g, ",")],
        ["Avg Words/Chunk", String(stats.avg_words_per_chunk)],
        ["Folders", String(stats.folders)],
        ["Internal Links", String(stats.internal_links)],
        ["Vault", stats.vault_path],
      ];
      
      rows.forEach(([label, value]) => {
        const row = table.createEl("tr");
        row.createEl("td", { text: label, cls: "stats-label" });
        row.createEl("td", { text: value, cls: "stats-value" });
      });
    } else {
      statsContainer.setText(stats?.error || "Could not load statistics.");
    }
  }

  hide(): void {
    if (this.statusRefreshInterval) {
      window.clearInterval(this.statusRefreshInterval);
      this.statusRefreshInterval = null;
    }
  }
}
