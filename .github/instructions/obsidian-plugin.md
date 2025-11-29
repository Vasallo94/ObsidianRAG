# Obsidian Plugin Development Guidelines

> Instructions for developing the ObsidianRAG TypeScript plugin

## Overview

The Obsidian plugin serves as the frontend for ObsidianRAG, providing:
- Chat interface for asking questions
- Settings UI for configuration
- Backend lifecycle management (start/stop Python server)
- Display of answers with source links

## Project Structure (Planned)

```
plugin/
├── src/
│   ├── main.ts              # Plugin entry point
│   ├── settings.ts          # Settings tab
│   ├── chat-view.ts         # Chat sidebar view
│   ├── api-client.ts        # Backend HTTP client
│   ├── server-manager.ts    # Python server lifecycle
│   └── types.ts             # TypeScript interfaces
├── styles.css               # Plugin styles
├── manifest.json            # Plugin manifest
├── package.json
├── tsconfig.json
├── esbuild.config.mjs
└── README.md
```

## Obsidian Plugin Basics

### Plugin Entry Point
```typescript
// main.ts
import { Plugin, WorkspaceLeaf } from 'obsidian';
import { ObsidianRAGSettingTab } from './settings';
import { ChatView, VIEW_TYPE_CHAT } from './chat-view';
import { ServerManager } from './server-manager';
import { ApiClient } from './api-client';

interface ObsidianRAGSettings {
    pythonPath: string;
    serverPort: number;
    llmModel: string;
    autoStartServer: boolean;
}

const DEFAULT_SETTINGS: ObsidianRAGSettings = {
    pythonPath: 'python',
    serverPort: 8000,
    llmModel: 'gemma3',
    autoStartServer: true,
};

export default class ObsidianRAGPlugin extends Plugin {
    settings: ObsidianRAGSettings;
    serverManager: ServerManager;
    apiClient: ApiClient;

    async onload() {
        await this.loadSettings();
        
        // Initialize components
        this.serverManager = new ServerManager(this);
        this.apiClient = new ApiClient(this.settings.serverPort);
        
        // Register view
        this.registerView(
            VIEW_TYPE_CHAT,
            (leaf) => new ChatView(leaf, this)
        );

        // Add ribbon icon
        this.addRibbonIcon('message-circle', 'ObsidianRAG Chat', () => {
            this.activateChatView();
        });

        // Add settings tab
        this.addSettingTab(new ObsidianRAGSettingTab(this.app, this));

        // Add commands
        this.addCommand({
            id: 'open-chat',
            name: 'Open Chat',
            callback: () => this.activateChatView(),
        });

        this.addCommand({
            id: 'start-server',
            name: 'Start Backend Server',
            callback: () => this.serverManager.start(),
        });

        // Auto-start server if configured
        if (this.settings.autoStartServer) {
            await this.serverManager.start();
        }
    }

    async onunload() {
        await this.serverManager.stop();
    }

    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings() {
        await this.saveData(this.settings);
    }

    async activateChatView() {
        const { workspace } = this.app;
        
        let leaf = workspace.getLeavesOfType(VIEW_TYPE_CHAT)[0];
        
        if (!leaf) {
            leaf = workspace.getRightLeaf(false);
            await leaf.setViewState({ type: VIEW_TYPE_CHAT, active: true });
        }
        
        workspace.revealLeaf(leaf);
    }
}
```

### Settings Tab
```typescript
// settings.ts
import { App, PluginSettingTab, Setting } from 'obsidian';
import ObsidianRAGPlugin from './main';

export class ObsidianRAGSettingTab extends PluginSettingTab {
    plugin: ObsidianRAGPlugin;

    constructor(app: App, plugin: ObsidianRAGPlugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display(): void {
        const { containerEl } = this;
        containerEl.empty();

        containerEl.createEl('h2', { text: 'ObsidianRAG Settings' });

        new Setting(containerEl)
            .setName('Python Path')
            .setDesc('Path to Python executable (python, python3, or full path)')
            .addText(text => text
                .setPlaceholder('python')
                .setValue(this.plugin.settings.pythonPath)
                .onChange(async (value) => {
                    this.plugin.settings.pythonPath = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('Server Port')
            .setDesc('Port for the backend server')
            .addText(text => text
                .setPlaceholder('8000')
                .setValue(String(this.plugin.settings.serverPort))
                .onChange(async (value) => {
                    this.plugin.settings.serverPort = parseInt(value) || 8000;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('LLM Model')
            .setDesc('Ollama model to use')
            .addDropdown(dropdown => dropdown
                .addOption('gemma3', 'Gemma 3')
                .addOption('llama3.2', 'Llama 3.2')
                .addOption('mistral', 'Mistral')
                .addOption('qwen2.5', 'Qwen 2.5')
                .setValue(this.plugin.settings.llmModel)
                .onChange(async (value) => {
                    this.plugin.settings.llmModel = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('Auto-start Server')
            .setDesc('Automatically start backend when Obsidian opens')
            .addToggle(toggle => toggle
                .setValue(this.plugin.settings.autoStartServer)
                .onChange(async (value) => {
                    this.plugin.settings.autoStartServer = value;
                    await this.plugin.saveSettings();
                }));
    }
}
```

### Chat View
```typescript
// chat-view.ts
import { ItemView, WorkspaceLeaf, MarkdownRenderer } from 'obsidian';
import ObsidianRAGPlugin from './main';

export const VIEW_TYPE_CHAT = 'obsidianrag-chat';

interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    sources?: string[];
}

export class ChatView extends ItemView {
    plugin: ObsidianRAGPlugin;
    messages: ChatMessage[] = [];
    inputEl: HTMLTextAreaElement;
    messagesEl: HTMLElement;

    constructor(leaf: WorkspaceLeaf, plugin: ObsidianRAGPlugin) {
        super(leaf);
        this.plugin = plugin;
    }

    getViewType(): string {
        return VIEW_TYPE_CHAT;
    }

    getDisplayText(): string {
        return 'ObsidianRAG Chat';
    }

    getIcon(): string {
        return 'message-circle';
    }

    async onOpen() {
        const container = this.containerEl.children[1];
        container.empty();
        container.addClass('obsidianrag-chat-container');

        // Messages container
        this.messagesEl = container.createDiv('obsidianrag-messages');

        // Input area
        const inputContainer = container.createDiv('obsidianrag-input-container');
        this.inputEl = inputContainer.createEl('textarea', {
            placeholder: 'Ask a question about your notes...',
            cls: 'obsidianrag-input',
        });

        const sendButton = inputContainer.createEl('button', {
            text: 'Send',
            cls: 'obsidianrag-send-button',
        });

        // Event handlers
        sendButton.addEventListener('click', () => this.sendMessage());
        this.inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    async sendMessage() {
        const question = this.inputEl.value.trim();
        if (!question) return;

        // Add user message
        this.addMessage({ role: 'user', content: question });
        this.inputEl.value = '';

        // Show loading
        const loadingEl = this.messagesEl.createDiv('obsidianrag-loading');
        loadingEl.setText('Thinking...');

        try {
            const response = await this.plugin.apiClient.ask(question);
            loadingEl.remove();
            
            this.addMessage({
                role: 'assistant',
                content: response.answer,
                sources: response.sources,
            });
        } catch (error) {
            loadingEl.remove();
            this.addMessage({
                role: 'assistant',
                content: `Error: ${error.message}`,
            });
        }
    }

    addMessage(message: ChatMessage) {
        this.messages.push(message);
        
        const messageEl = this.messagesEl.createDiv(`obsidianrag-message ${message.role}`);
        
        // Render markdown content
        MarkdownRenderer.renderMarkdown(
            message.content,
            messageEl.createDiv('message-content'),
            '',
            this
        );

        // Add sources if present
        if (message.sources?.length) {
            const sourcesEl = messageEl.createDiv('message-sources');
            sourcesEl.createEl('strong', { text: 'Sources: ' });
            message.sources.forEach((source, i) => {
                if (i > 0) sourcesEl.appendText(', ');
                const link = sourcesEl.createEl('a', { text: source });
                link.addEventListener('click', () => {
                    this.app.workspace.openLinkText(source, '');
                });
            });
        }

        // Scroll to bottom
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }

    async onClose() {
        // Cleanup
    }
}
```

### API Client
```typescript
// api-client.ts
interface AskResponse {
    answer: string;
    sources: string[];
}

interface HealthResponse {
    status: string;
    version: string;
}

export class ApiClient {
    private baseUrl: string;

    constructor(port: number) {
        this.baseUrl = `http://127.0.0.1:${port}`;
    }

    async ask(question: string): Promise<AskResponse> {
        const response = await fetch(`${this.baseUrl}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question }),
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        return response.json();
    }

    async health(): Promise<HealthResponse> {
        const response = await fetch(`${this.baseUrl}/health`);
        return response.json();
    }

    async isServerRunning(): Promise<boolean> {
        try {
            await this.health();
            return true;
        } catch {
            return false;
        }
    }
}
```

### Server Manager
```typescript
// server-manager.ts
import { spawn, ChildProcess } from 'child_process';
import { Notice } from 'obsidian';
import ObsidianRAGPlugin from './main';

export class ServerManager {
    private plugin: ObsidianRAGPlugin;
    private process: ChildProcess | null = null;

    constructor(plugin: ObsidianRAGPlugin) {
        this.plugin = plugin;
    }

    async start(): Promise<void> {
        if (await this.plugin.apiClient.isServerRunning()) {
            new Notice('ObsidianRAG server is already running');
            return;
        }

        const vaultPath = this.plugin.app.vault.adapter.basePath;
        const { pythonPath, serverPort, llmModel } = this.plugin.settings;

        this.process = spawn(pythonPath, [
            '-m', 'obsidianrag',
            'serve',
            '--vault-path', vaultPath,
            '--port', String(serverPort),
        ], {
            env: {
                ...process.env,
                OBSIDIANRAG_LLM_MODEL: llmModel,
            },
        });

        this.process.stdout?.on('data', (data) => {
            console.log(`[ObsidianRAG] ${data}`);
        });

        this.process.stderr?.on('data', (data) => {
            console.error(`[ObsidianRAG] ${data}`);
        });

        this.process.on('error', (error) => {
            new Notice(`Failed to start ObsidianRAG: ${error.message}`);
        });

        // Wait for server to be ready
        await this.waitForServer();
        new Notice('ObsidianRAG server started');
    }

    async stop(): Promise<void> {
        if (this.process) {
            this.process.kill();
            this.process = null;
            new Notice('ObsidianRAG server stopped');
        }
    }

    private async waitForServer(timeout = 30000): Promise<void> {
        const start = Date.now();
        while (Date.now() - start < timeout) {
            if (await this.plugin.apiClient.isServerRunning()) {
                return;
            }
            await new Promise(resolve => setTimeout(resolve, 500));
        }
        throw new Error('Server startup timeout');
    }
}
```

## Development Setup

```bash
# Clone and setup
cd plugin
npm install

# Development build (with watch)
npm run dev

# Production build
npm run build

# Link to Obsidian vault for testing
ln -s $(pwd) /path/to/vault/.obsidian/plugins/obsidianrag
```

## TypeScript Configuration

```json
// tsconfig.json
{
    "compilerOptions": {
        "target": "ES2018",
        "module": "ESNext",
        "lib": ["ES2018", "DOM"],
        "moduleResolution": "node",
        "strict": true,
        "noImplicitAny": true,
        "outDir": "./dist",
        "sourceMap": true,
        "declaration": true,
        "esModuleInterop": true,
        "skipLibCheck": true
    },
    "include": ["src/**/*.ts"]
}
```

## Styling

```css
/* styles.css */
.obsidianrag-chat-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 10px;
}

.obsidianrag-messages {
    flex: 1;
    overflow-y: auto;
    margin-bottom: 10px;
}

.obsidianrag-message {
    margin-bottom: 15px;
    padding: 10px;
    border-radius: 8px;
}

.obsidianrag-message.user {
    background-color: var(--background-secondary);
    margin-left: 20%;
}

.obsidianrag-message.assistant {
    background-color: var(--background-primary-alt);
    margin-right: 20%;
}

.obsidianrag-input-container {
    display: flex;
    gap: 10px;
}

.obsidianrag-input {
    flex: 1;
    min-height: 60px;
    resize: vertical;
}

.obsidianrag-send-button {
    align-self: flex-end;
}

.message-sources {
    margin-top: 10px;
    font-size: 0.85em;
    color: var(--text-muted);
}

.message-sources a {
    color: var(--text-accent);
    cursor: pointer;
}
```

## Best Practices

### DO ✅
- Use Obsidian's built-in components (Notice, Modal, Setting)
- Respect user's theme (use CSS variables)
- Handle server connection errors gracefully
- Clean up resources in `onunload()`
- Use TypeScript strict mode

### DON'T ❌
- Don't block the UI during long operations
- Don't store sensitive data in plain settings
- Don't assume server is always running
- Don't use inline styles (use CSS file)
- Don't hardcode paths

## Testing

```typescript
// Manual testing checklist
// 1. Plugin loads without errors
// 2. Settings save and persist
// 3. Server starts/stops correctly
// 4. Chat view opens and functions
// 5. Questions get answered
// 6. Source links work
// 7. Handles server offline gracefully
// 8. Works with different themes
```

## Resources

- [Obsidian Plugin API](https://docs.obsidian.md/Plugins/Getting+started/Build+a+plugin)
- [Obsidian Sample Plugin](https://github.com/obsidianmd/obsidian-sample-plugin)
- [Obsidian API Reference](https://docs.obsidian.md/Reference/TypeScript+API)
