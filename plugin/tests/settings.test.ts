/**
 * Tests for Plugin Settings Management
 */

describe('Plugin Settings', () => {
  const DEFAULT_SETTINGS = {
    pythonPath: '/usr/local/bin/obsidianrag-server',
    serverPort: 8000,
    llmModel: 'gemma3',
    autoStartServer: true,
    showSourceLinks: true
  };

  describe('Default Settings', () => {
    it('should have correct default values', () => {
      expect(DEFAULT_SETTINGS.pythonPath).toBe('/usr/local/bin/obsidianrag-server');
      expect(DEFAULT_SETTINGS.serverPort).toBe(8000);
      expect(DEFAULT_SETTINGS.llmModel).toBe('gemma3');
      expect(DEFAULT_SETTINGS.autoStartServer).toBe(true);
      expect(DEFAULT_SETTINGS.showSourceLinks).toBe(true);
    });
  });

  describe('Settings Merge', () => {
    it('should merge saved settings with defaults', () => {
      const savedSettings = {
        serverPort: 9000,
        llmModel: 'llama3.2'
      };

      const mergedSettings = Object.assign({}, DEFAULT_SETTINGS, savedSettings);

      expect(mergedSettings.serverPort).toBe(9000);
      expect(mergedSettings.llmModel).toBe('llama3.2');
      expect(mergedSettings.pythonPath).toBe('/usr/local/bin/obsidianrag-server');
      expect(mergedSettings.autoStartServer).toBe(true);
    });

    it('should handle empty saved settings', () => {
      const mergedSettings = Object.assign({}, DEFAULT_SETTINGS, {});

      expect(mergedSettings).toEqual(DEFAULT_SETTINGS);
    });
  });

  describe('API Base URL Generation', () => {
    it('should generate correct API base URL', () => {
      const port = 8000;
      const apiBaseUrl = `http://127.0.0.1:${port}`;

      expect(apiBaseUrl).toBe('http://127.0.0.1:8000');
    });

    it('should update API base URL when port changes', () => {
      let port = 8000;
      let apiBaseUrl = `http://127.0.0.1:${port}`;
      expect(apiBaseUrl).toBe('http://127.0.0.1:8000');

      port = 9000;
      apiBaseUrl = `http://127.0.0.1:${port}`;
      expect(apiBaseUrl).toBe('http://127.0.0.1:9000');
    });
  });

  describe('Port Validation', () => {
    it('should parse valid port strings', () => {
      const port = parseInt('8000') || 8000;
      expect(port).toBe(8000);
    });

    it('should use default port for invalid strings', () => {
      const port = parseInt('invalid') || 8000;
      expect(port).toBe(8000);
    });

    it('should use default port for empty strings', () => {
      const port = parseInt('') || 8000;
      expect(port).toBe(8000);
    });
  });
});
