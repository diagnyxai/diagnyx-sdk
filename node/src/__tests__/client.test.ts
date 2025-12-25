import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Diagnyx } from '../client';

describe('Diagnyx Client', () => {
  let client: Diagnyx;

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should throw if apiKey is missing', () => {
    expect(() => new Diagnyx({ apiKey: '' })).toThrow('apiKey is required');
  });

  it('should initialize with default config', () => {
    const defaultClient = new Diagnyx({ apiKey: 'test' });
    expect(defaultClient.bufferSize).toBe(0);
    // Clear the timer by running pending timers
    vi.runOnlyPendingTimers();
  });

  it('should add calls to buffer', async () => {
    const client = new Diagnyx({
      apiKey: 'test_api_key',
      baseUrl: 'https://test.api.com',
      batchSize: 10,
      flushIntervalMs: 60000, // Long interval to prevent auto-flush
    });

    await client.trackCall({
      provider: 'openai',
      model: 'gpt-4',
      inputTokens: 100,
      outputTokens: 50,
      status: 'success',
    });

    expect(client.bufferSize).toBe(1);
    vi.runOnlyPendingTimers();
  });

  it('should track multiple calls', async () => {
    const client = new Diagnyx({
      apiKey: 'test_api_key',
      baseUrl: 'https://test.api.com',
      batchSize: 10,
      flushIntervalMs: 60000,
    });

    await client.trackCalls([
      {
        provider: 'openai',
        model: 'gpt-4',
        inputTokens: 100,
        outputTokens: 50,
        status: 'success',
      },
      {
        provider: 'anthropic',
        model: 'claude-3-sonnet',
        inputTokens: 200,
        outputTokens: 100,
        status: 'success',
      },
    ]);

    expect(client.bufferSize).toBe(2);
    vi.runOnlyPendingTimers();
  });

  it('should flush when batch size is reached', async () => {
    const client = new Diagnyx({
      apiKey: 'test_api_key',
      baseUrl: 'https://test.api.com',
      batchSize: 10,
      flushIntervalMs: 60000,
    });

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ tracked: 10, totalCost: 0.1, totalTokens: 1500, ids: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    // Add 10 calls to reach batch size
    for (let i = 0; i < 10; i++) {
      await client.trackCall({
        provider: 'openai',
        model: 'gpt-4',
        inputTokens: 100,
        outputTokens: 50,
        status: 'success',
      });
    }

    // Should have flushed
    expect(fetchSpy).toHaveBeenCalled();
    expect(client.bufferSize).toBe(0);

    fetchSpy.mockRestore();
    vi.runOnlyPendingTimers();
  });

  it('should normalize timestamp to ISO string', async () => {
    const client = new Diagnyx({
      apiKey: 'test_api_key',
      baseUrl: 'https://test.api.com',
      batchSize: 10,
      flushIntervalMs: 60000,
    });

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ tracked: 1, totalCost: 0.01, totalTokens: 150, ids: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await client.trackCall({
      provider: 'openai',
      model: 'gpt-4',
      inputTokens: 100,
      outputTokens: 50,
      status: 'success',
      timestamp: new Date('2024-01-15T10:00:00Z'),
    });

    await client.flush();

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: expect.stringContaining('2024-01-15T10:00:00.000Z'),
      }),
    );

    fetchSpy.mockRestore();
    vi.runOnlyPendingTimers();
  });
});
