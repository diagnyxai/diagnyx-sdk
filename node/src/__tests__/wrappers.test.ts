import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Diagnyx } from '../client';
import { wrapOpenAI, wrapAnthropic, trackWithTiming } from '../wrappers';

describe('OpenAI Wrapper', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('should wrap OpenAI client and track calls', async () => {
    const diagnyx = new Diagnyx({
      apiKey: 'test_api_key',
      baseUrl: 'https://test.api.com',
      flushIntervalMs: 60000,
    });
    const trackCallSpy = vi.spyOn(diagnyx, 'trackCall');

    const mockOpenAI = {
      chat: {
        completions: {
          create: vi.fn().mockResolvedValue({
            id: 'test-id',
            model: 'gpt-4',
            usage: {
              prompt_tokens: 100,
              completion_tokens: 50,
              total_tokens: 150,
            },
          }),
        },
      },
    };

    const wrapped = wrapOpenAI(mockOpenAI, diagnyx);
    const result = await wrapped.chat.completions.create({ model: 'gpt-4' });

    expect(result.model).toBe('gpt-4');
    expect(trackCallSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: 'openai',
        model: 'gpt-4',
        inputTokens: 100,
        outputTokens: 50,
        status: 'success',
      }),
    );
  });

  it('should track errors on OpenAI failures', async () => {
    const diagnyx = new Diagnyx({
      apiKey: 'test_api_key',
      baseUrl: 'https://test.api.com',
      flushIntervalMs: 60000,
    });
    const trackCallSpy = vi.spyOn(diagnyx, 'trackCall');

    const mockOpenAI = {
      chat: {
        completions: {
          create: vi.fn().mockRejectedValue(new Error('API Error')),
        },
      },
    };

    const wrapped = wrapOpenAI(mockOpenAI, diagnyx);

    await expect(wrapped.chat.completions.create({ model: 'gpt-4' })).rejects.toThrow('API Error');

    expect(trackCallSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: 'openai',
        status: 'error',
        errorMessage: 'API Error',
      }),
    );
  });
});

describe('Anthropic Wrapper', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('should wrap Anthropic client and track calls', async () => {
    const diagnyx = new Diagnyx({
      apiKey: 'test_api_key',
      baseUrl: 'https://test.api.com',
      flushIntervalMs: 60000,
    });
    const trackCallSpy = vi.spyOn(diagnyx, 'trackCall');

    const mockAnthropic = {
      messages: {
        create: vi.fn().mockResolvedValue({
          id: 'test-id',
          model: 'claude-3-sonnet',
          usage: {
            input_tokens: 200,
            output_tokens: 100,
          },
        }),
      },
    };

    const wrapped = wrapAnthropic(mockAnthropic, diagnyx);
    const result = await wrapped.messages.create({ model: 'claude-3-sonnet' });

    expect(result.model).toBe('claude-3-sonnet');
    expect(trackCallSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: 'anthropic',
        model: 'claude-3-sonnet',
        inputTokens: 200,
        outputTokens: 100,
        status: 'success',
      }),
    );
  });
});

describe('trackWithTiming', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('should track manual calls with timing', async () => {
    const diagnyx = new Diagnyx({
      apiKey: 'test_api_key',
      baseUrl: 'https://test.api.com',
      flushIntervalMs: 60000,
    });
    const trackCallSpy = vi.spyOn(diagnyx, 'trackCall');

    const result = await trackWithTiming(
      diagnyx,
      'openai',
      'gpt-4',
      async () => ({ response: 'Hello!', tokens: { in: 10, out: 5 } }),
      (res) => ({ inputTokens: res.tokens.in, outputTokens: res.tokens.out }),
    );

    expect(result.response).toBe('Hello!');
    expect(trackCallSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: 'openai',
        model: 'gpt-4',
        inputTokens: 10,
        outputTokens: 5,
        status: 'success',
      }),
    );
  });
});
