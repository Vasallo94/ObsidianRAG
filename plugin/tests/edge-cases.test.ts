
import * as child_process from 'child_process';
import { requestUrl } from 'obsidian';
import ObsidianRAGPlugin from '../src/main';

// Mock child_process
jest.mock('child_process', () => ({
  execFile: jest.fn((_command, _args, callback) => callback(null)),
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
    (requestUrl as jest.Mock).mockResolvedValue({
      status: 200,
      json: {
        state: 'missing', active_revision: null, serving_revision: null,
        query_ready: false, indexed_notes: 0, indexed_chunks: 0,
        changed_notes: 0, deleted_notes: 0, reason: null
      }
    });

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
    (plugin as any).apiBaseUrl = 'http://127.0.0.1:8000';
    plugin.settings = {
      pythonPath: 'python',
      serverPort: 8000,
      llmProvider: 'custom',
      llmApiFormat: 'chat-completions',
      llmModel: 'test-model',
      llmBaseUrl: 'http://localhost:1234/v1',
      llmApiKey: 'session-secret',
      autoStartServer: true,
      showSourceLinks: true,
      hasCompletedSetup: true
    };

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

  describe('Server Ownership and Secrets', () => {
    it('never launches the backend through a shell', () => {
      expect(plugin.getSpawnOptionsForPlatform('win32')).toEqual(expect.objectContaining({
        shell: false,
        windowsHide: true
      }));
      expect(plugin.getSpawnOptionsForPlatform('darwin')).toEqual(expect.objectContaining({
        shell: false
      }));
      expect(plugin.getSpawnOptionsForPlatform('linux')).toEqual(expect.objectContaining({
        shell: false
      }));
    });

    it('keeps vault metacharacters in one process argument', async () => {
      const mockProcess = {
        stdout: { on: jest.fn() }, stderr: { on: jest.fn() },
        on: jest.fn(), kill: jest.fn()
      };
      mockSpawn.mockReturnValue(mockProcess);
      plugin.waitForServer.mockResolvedValue(true);
      plugin.app.vault.adapter.basePath = 'C:\\Vault & Notes';

      await plugin.startServer();

      const args = mockSpawn.mock.calls[0][1] as string[];
      expect(args[args.indexOf('--vault') + 1]).toBe('C:\\Vault & Notes');
      expect(mockSpawn.mock.calls[0][2]).toEqual(expect.objectContaining({ shell: false }));
    });

    it('should not expose the API key in process arguments', async () => {
      const mockProcess = {
        stdout: { on: jest.fn() },
        stderr: { on: jest.fn() },
        on: jest.fn(),
        kill: jest.fn()
      };
      mockSpawn.mockReturnValue(mockProcess);
      plugin.waitForServer.mockResolvedValue(true);

      await plugin.startServer();

      const args = mockSpawn.mock.calls[0][1] as string[];
      expect(args).not.toContain('--api-key');
      expect(args).not.toContain('session-secret');
    });

    it('should stop only the process spawned by the plugin', async () => {
      const mockProcess = { kill: jest.fn() };
      (plugin as any).serverProcess = mockProcess;

      await plugin.stopServer();

      expect(mockProcess.kill).toHaveBeenCalledTimes(1);
      expect((plugin as any).serverProcess).toBeNull();
    });

    it('should not let an old exit event orphan a replacement process', async () => {
      const callbacks = new Map<string, Function>();
      const oldProcess = {
        stdout: { on: jest.fn() },
        stderr: { on: jest.fn() },
        on: jest.fn((event, callback) => callbacks.set(event, callback)),
        kill: jest.fn()
      };
      const replacementProcess = {
        stdout: { on: jest.fn() },
        stderr: { on: jest.fn() },
        on: jest.fn(),
        kill: jest.fn()
      };
      mockSpawn.mockReturnValueOnce(oldProcess).mockReturnValueOnce(replacementProcess);
      plugin.isServerRunning = jest.fn().mockResolvedValue(false);
      plugin.waitForServer.mockResolvedValue(true);

      await plugin.startServer();
      await plugin.stopServer();
      await plugin.startServer();
      callbacks.get('exit')?.(0);

      expect((plugin as any).serverProcess).toBe(replacementProcess);
    });

    it('should terminate only the owned process tree on Windows', async () => {
      const mockProcess = { pid: 1234, kill: jest.fn() };

      await (plugin as any).terminateManagedProcess(mockProcess, 'win32');

      expect(child_process.execFile).toHaveBeenCalledWith(
        'taskkill',
        ['/PID', '1234', '/T', '/F'],
        expect.any(Function)
      );
      expect(mockProcess.kill).not.toHaveBeenCalled();
    });

    it('should fall back to the owned child when Windows tree termination fails', async () => {
      const mockProcess = { pid: 1234, kill: jest.fn() };
      (child_process.execFile as unknown as jest.Mock).mockImplementationOnce(
        (_command, _args, callback) => callback(new Error('taskkill failed'))
      );

      await (plugin as any).terminateManagedProcess(mockProcess, 'win32');

      expect(mockProcess.kill).toHaveBeenCalledTimes(1);
    });

    it('should not persist API keys in plugin data', async () => {
      plugin.saveData = jest.fn().mockResolvedValue(undefined);

      await plugin.saveSettings();

      expect(plugin.saveData).toHaveBeenCalledWith(
        expect.not.objectContaining({ llmApiKey: expect.anything() })
      );
      expect(plugin.settings.llmApiKey).toBe('session-secret');
    });

    it('should require the expected backend API contract', async () => {
      (requestUrl as jest.Mock)
        .mockResolvedValueOnce({
          status: 200,
          json: { api_version: 4, backend_version: '4.0.0' }
        })
        .mockResolvedValueOnce({ status: 200, json: { status: 'ok' } });

      await expect(plugin.isServerRunning()).resolves.toBe(true);

      (requestUrl as jest.Mock).mockResolvedValueOnce({
        status: 200,
        json: { api_version: 3, backend_version: '3.0.3' }
      });
      await expect(plugin.isServerRunning()).resolves.toBe(false);
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

  describe('v4 index lifecycle', () => {
    it('accepts only the API 4 backend contract', async () => {
      expect(plugin.getIndexActionLabel({ state: 'missing' })).toBe('Build index');
      expect(plugin.getIndexActionLabel({ state: 'current' })).toBe('Refresh index');
      expect(plugin.getIndexActionLabel({ state: 'stale' })).toBe('Refresh index');
      expect(plugin.getIndexActionLabel({ state: 'rebuild_required' })).toBe('Full rebuild');
    });

    it('builds through the v4 lifecycle endpoint', async () => {
      (requestUrl as jest.Mock)
        .mockResolvedValueOnce({
          status: 200,
          json: { revision: 'r2', notes: 2, chunks: 3, reused_chunks: 1,
            reindexed_notes: 1, deleted_notes: 0 }
        })
        .mockResolvedValueOnce({
          status: 200,
          json: { state: 'current', active_revision: 'r2', serving_revision: 'r2',
            query_ready: true, indexed_notes: 2, indexed_chunks: 3,
            changed_notes: 0, deleted_notes: 0, reason: null }
        });

      await expect(plugin.buildIndex(true)).resolves.toBe(true);
      expect(requestUrl).toHaveBeenNthCalledWith(1, expect.objectContaining({
        url: 'http://127.0.0.1:8000/index/build',
        method: 'POST',
        body: JSON.stringify({ full_rebuild: true })
      }));
    });

    it('prunes through the v4 lifecycle endpoint', async () => {
      (requestUrl as jest.Mock)
        .mockResolvedValueOnce({
          status: 200,
          json: { active_revision: 'r2', deleted_revisions: ['r1'] }
        })
        .mockResolvedValueOnce({
          status: 200,
          json: { state: 'current', active_revision: 'r2', serving_revision: 'r2',
            query_ready: true, indexed_notes: 2, indexed_chunks: 3,
            changed_notes: 0, deleted_notes: 0, reason: null }
        });

      await expect(plugin.pruneIndex()).resolves.toBe(true);
      expect(requestUrl).toHaveBeenNthCalledWith(1, {
        url: 'http://127.0.0.1:8000/index/prune', method: 'POST'
      });
    });
  });
});
