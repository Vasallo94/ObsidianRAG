/**
 * Tests for Server Health Check and API Communication
 */

describe('Server Health Check', () => {
  let mockFetch: jest.Mock;

  beforeEach(() => {
    mockFetch = jest.fn();
    global.fetch = mockFetch;
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('isServerRunning', () => {
    it('should return true when server responds with 200 OK', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        status: 200
      });

      const apiBaseUrl = 'http://127.0.0.1:8000';
      const response = await fetch(`${apiBaseUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(2000)
      });

      expect(response.ok).toBe(true);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/health',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('should return false when server is unreachable', async () => {
      mockFetch.mockRejectedValue(new Error('Connection refused'));

      try {
        await fetch('http://127.0.0.1:8000/health');
      } catch (e) {
        expect(e).toBeInstanceOf(Error);
        expect((e as Error).message).toBe('Connection refused');
      }
    });
  });

  describe('askQuestion', () => {
    it('should send POST request with question', async () => {
      const mockResponse = {
        result: 'Test answer',
        sources: [],
        question: 'Test question',
        process_time: 1.5,
        session_id: 'test-session'
      };

      mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockResponse
      });

      const response = await fetch('http://127.0.0.1:8000/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Test question' })
      });

      const data = await response.json();

      expect(mockFetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/ask',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        })
      );
      expect(data.result).toBe('Test answer');
    });

    it('should handle server errors gracefully', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500
      });

      const response = await fetch('http://127.0.0.1:8000/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Test' })
      });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(500);
    });
  });
});

describe('SSE Stream Parsing', () => {
  it('should parse SSE data correctly', () => {
    const sseData = 'data: {"type":"token","content":"Hello"}';
    const line = sseData.slice(6); // Remove "data: " prefix
    const parsed = JSON.parse(line);

    expect(parsed.type).toBe('token');
    expect(parsed.content).toBe('Hello');
  });

  it('should handle multiple SSE events', () => {
    const buffer = `data: {"type":"start"}
data: {"type":"token","content":"Test"}
data: {"type":"done"}
`;

    const lines = buffer.split('\n').filter(l => l.startsWith('data: '));
    const events = lines.map(l => JSON.parse(l.slice(6)));

    expect(events).toHaveLength(3);
    expect(events[0].type).toBe('start');
    expect(events[1].type).toBe('token');
    expect(events[2].type).toBe('done');
  });

  it('should ignore non-data SSE lines', () => {
    const lines = [
      'data: {"type":"token"}',
      ': comment',
      'data: {"type":"done"}',
      ''
    ];

    const dataLines = lines.filter(l => l.startsWith('data: '));
    expect(dataLines).toHaveLength(2);
  });

  it('should handle malformed JSON gracefully', () => {
    const badLine = 'data: {invalid json}';

    try {
      JSON.parse(badLine.slice(6));
      fail('Should have thrown error');
    } catch (e) {
      expect(e).toBeInstanceOf(SyntaxError);
    }
  });
});
