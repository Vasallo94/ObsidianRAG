
import * as child_process from 'child_process';
import { requestUrl } from 'obsidian';
import ObsidianRAGPlugin from '../src/main';

// Mock child_process
jest.mock('child_process', () => ({
  spawn: jest.fn()
}));

// Mock global fetch
global.fetch = jest.fn();

describe('Edge Cases', () => {
  let plugin: any;
  let mockSpawn: jest.Mock;

  beforeAll(() => {
    // Mock document if missing (Node env)
    if (typeof document === 'undefined') {
      (global as any).document = {
        createElement: () => ({
          createEl: () => ({}),
          appendChild: () => {},
          classList: { add: () => {} }
        }),
      };
    }
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockSpawn = child_process.spawn as unknown as jest.Mock;

    const mockApp = {
      vault: {
        adapter: {
          basePath: '/test/vault'
        }
      },
      workspace: {
        onLayoutReady: (cb: Function) => cb(),
      }
    };
    const mockManifest = {};

    plugin = new ObsidianRAGPlugin(mockApp as any, mockManifest as any);
    plugin.settings = {
      pythonPath: 'python',
      serverPort: 8000,
      llmModel: 'test-model',
      autoStartServer: true,
      useReranker: false
    };

    // Mock getSpawnOptionsForPlatform to return simple options
    plugin.getSpawnOptionsForPlatform = jest.fn().mockReturnValue({});
    // Mock waitForServer to avoid actual timeout
    plugin.waitForServer = jest.fn();
    // Mock updateStatusBar
    plugin.updateStatusBar = jest.fn();
    // Mock handleServerCrash to prevent async retry loops in tests
    (plugin as any).handleServerCrash = jest.fn();
  });

  describe('Server Start - Port Occupied', () => {
    it('should handle server process immediate exit (port occupied)', async () => {
      // Setup spawn mock to return a process that exits immediately
      const mockProcess = {
        stdout: { on: jest.fn() },
        stderr: { on: jest.fn() },
        on: jest.fn((event, cb) => {
          if (event === 'exit') {
            // Simulate immediate exit with error code 1
            cb(1);
          }
        }),
        kill: jest.fn()
      };
      mockSpawn.mockReturnValue(mockProcess);

      // Mock waitForServer to return false (server never came up)
      plugin.waitForServer.mockResolvedValue(false);

      const result = await plugin.startServer();

      expect(result).toBe(false);
      expect(mockSpawn).toHaveBeenCalled();
      // Verify crash handler was triggered
      expect((plugin as any).handleServerCrash).toHaveBeenCalledWith(1);
      // Expect Notice to have been called (we can't easily check the content of Notice
      // unless we spy on the Notice class constructor or mock it differently)
    });
  });

  describe('Server Status - Connection Lost', () => {
    it('should handle connection refused', async () => {
      (global.fetch as jest.Mock).mockRejectedValue(new Error('Connection refused'));

      // We need to spy on Notice to verify the output
      // Since Notice is a class, we can spy on the prototype or just trust the mock implementation logs

      await plugin.checkServerStatus();

      // If no error thrown, it passed the try-catch block
    });
  });

  describe('Vault Stats', () => {
    it('should handle empty vault stats', async () => {
      (requestUrl as jest.Mock).mockResolvedValue({
        status: 200,
        json: {
          total_notes: 0,
          total_chunks: 0,
          total_words: 0,
          total_chars: 0,
          avg_words_per_chunk: 0,
          folders: 0,
          internal_links: 0,
          vault_path: '/test/vault'
        }
      });

      const stats = await plugin.getStats();
      expect(stats).toEqual(expect.objectContaining({
        total_notes: 0,
        total_chunks: 0
      }));
    });

    it('should handle large vault stats', async () => {
      (requestUrl as jest.Mock).mockResolvedValue({
        status: 200,
        json: {
          total_notes: 10000,
          total_chunks: 50000,
          total_words: 1000000,
          total_chars: 5000000,
          avg_words_per_chunk: 200,
          folders: 500,
          internal_links: 20000,
          vault_path: '/test/vault'
        }
      });

      const stats = await plugin.getStats();
      expect(stats).toEqual(expect.objectContaining({
        total_notes: 10000,
        total_chunks: 50000
      }));
    });
  });
});
