// Mock de Obsidian API para tests
export class Plugin {
  app: any;
  manifest: any;

  constructor(app: any, manifest: any) {
    this.app = app;
    this.manifest = manifest;
  }

  async loadData() { return {}; }
  async saveData(data: any) {}
  addCommand(command: any) {}
  addRibbonIcon(icon: string, title: string, callback: () => void) {}
  addSettingTab(tab: any) {}
  registerView(type: string, viewCreator: any) {}
}

export class Modal {
  app: any;
  contentEl: any = document.createElement('div');

  constructor(app: any) {
    this.app = app;
  }

  open() {}
  close() {}
  setContent(content: string) {}
}

export class ItemView {
  app: any;
  leaf: any;
  containerEl: any = { children: [null, document.createElement('div')] };

  constructor(leaf: any) {
    this.leaf = leaf;
  }

  getViewType() { return ''; }
  getDisplayText() { return ''; }
  onOpen() {}
  onClose() {}
}

export class PluginSettingTab {
  app: any;
  plugin: any;
  containerEl: any = document.createElement('div');

  constructor(app: any, plugin: any) {
    this.app = app;
    this.plugin = plugin;
  }

  display() {}
}

export class Notice {
  constructor(message: string) {
    console.log(`[Notice] ${message}`);
  }
}

export class Setting {
  constructor(containerEl: any) {}
  setName(name: string) { return this; }
  setDesc(desc: string) { return this; }
  addText(cb: any) { return this; }
  addToggle(cb: any) { return this; }
  addDropdown(cb: any) { return this; }
  addButton(cb: any) { return this; }
}

export const MarkdownRenderer = {
  render: jest.fn()
};

export const requestUrl = jest.fn();
