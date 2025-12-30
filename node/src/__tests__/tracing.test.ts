import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Tracer, Trace, Span, getCurrentTrace, getCurrentSpan } from '../tracing';

describe('Span', () => {
  let mockClient: { _sendTraces: ReturnType<typeof vi.fn> };
  let tracer: Tracer;
  let trace: Trace;

  beforeEach(() => {
    mockClient = {
      _sendTraces: vi.fn().mockResolvedValue({ success: true, count: 1 }),
    };
    tracer = new Tracer(mockClient, {
      organizationId: 'org-123',
      environment: 'test',
    });
    trace = tracer.trace({ name: 'test-trace' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('constructor', () => {
    it('should create a span with required properties', () => {
      const span = trace.span({ name: 'test-span', spanType: 'function' });

      expect(span.name).toBe('test-span');
      expect(span.spanType).toBe('function');
      expect(span.spanId).toMatch(/^[0-9a-f]{16}$/);
      expect(span.trace).toBe(trace);
      expect(span.startTime).toBeDefined();
      expect(span.parentSpanId).toBeNull();
    });

    it('should create a span with default type "function"', () => {
      const span = trace.span('simple-span');

      expect(span.spanType).toBe('function');
    });

    it('should set parent span when nested', async () => {
      const parentSpan = trace.span('parent');

      // Run within parent span context
      await parentSpan.run(async () => {
        const childSpan = trace.span('child');
        expect(childSpan.parentSpanId).toBe(parentSpan.spanId);
      });
    });
  });

  describe('setInput', () => {
    it('should set string input with auto-preview', () => {
      const span = trace.span('test');
      span.setInput('Hello, World!');

      const data = span.toData();
      expect(data.input).toBe('Hello, World!');
      expect(data.inputPreview).toBe('Hello, World!');
    });

    it('should set object input with JSON preview', () => {
      const span = trace.span('test');
      const input = { messages: [{ role: 'user', content: 'Hello' }] };
      span.setInput(input);

      const data = span.toData();
      expect(data.input).toEqual(input);
      expect(data.inputPreview).toContain('messages');
    });

    it('should truncate preview to max length', () => {
      const span = trace.span('test');
      const longInput = 'a'.repeat(1000);
      span.setInput(longInput, undefined, 100);

      const data = span.toData();
      expect(data.inputPreview?.length).toBe(100);
    });

    it('should use custom preview when provided', () => {
      const span = trace.span('test');
      span.setInput({ complex: 'object' }, 'Custom preview');

      const data = span.toData();
      expect(data.inputPreview).toBe('Custom preview');
    });

    it('should be chainable', () => {
      const span = trace.span('test');
      const result = span.setInput('test');
      expect(result).toBe(span);
    });
  });

  describe('setOutput', () => {
    it('should set string output with auto-preview', () => {
      const span = trace.span('test');
      span.setOutput('Response text');

      const data = span.toData();
      expect(data.output).toBe('Response text');
      expect(data.outputPreview).toBe('Response text');
    });

    it('should set object output with JSON preview', () => {
      const span = trace.span('test');
      const output = { id: 'resp-123', choices: [] };
      span.setOutput(output);

      const data = span.toData();
      expect(data.output).toEqual(output);
      expect(data.outputPreview).toContain('resp-123');
    });

    it('should be chainable', () => {
      const span = trace.span('test');
      const result = span.setOutput('test');
      expect(result).toBe(span);
    });
  });

  describe('setLlmInfo', () => {
    it('should set all LLM info properties', () => {
      const span = trace.span({ name: 'llm-call', spanType: 'llm' });
      span.setLlmInfo({
        provider: 'openai',
        model: 'gpt-4',
        inputTokens: 100,
        outputTokens: 200,
        costUsd: 0.05,
        ttftMs: 150,
      });

      const data = span.toData();
      expect(data.provider).toBe('openai');
      expect(data.model).toBe('gpt-4');
      expect(data.inputTokens).toBe(100);
      expect(data.outputTokens).toBe(200);
      expect(data.totalTokens).toBe(300);
      expect(data.costUsd).toBe(0.05);
      expect(data.ttftMs).toBe(150);
    });

    it('should calculate total tokens from input + output', () => {
      const span = trace.span('test');
      span.setLlmInfo({
        provider: 'anthropic',
        model: 'claude-3',
        inputTokens: 50,
        outputTokens: 75,
      });

      const data = span.toData();
      expect(data.totalTokens).toBe(125);
    });

    it('should be chainable', () => {
      const span = trace.span('test');
      const result = span.setLlmInfo({ provider: 'openai', model: 'gpt-4' });
      expect(result).toBe(span);
    });
  });

  describe('setMetadata', () => {
    it('should set metadata key-value pairs', () => {
      const span = trace.span('test');
      span.setMetadata('customKey', 'customValue');
      span.setMetadata('numericKey', 42);

      const data = span.toData();
      expect(data.metadata?.customKey).toBe('customValue');
      expect(data.metadata?.numericKey).toBe(42);
    });

    it('should be chainable', () => {
      const span = trace.span('test');
      const result = span.setMetadata('key', 'value');
      expect(result).toBe(span);
    });
  });

  describe('addEvent', () => {
    it('should add events with timestamp', () => {
      const span = trace.span('test');
      span.addEvent('checkpoint');
      span.addEvent('completed', { result: 'success' });

      const data = span.toData();
      expect(data.events).toHaveLength(2);
      expect(data.events?.[0].name).toBe('checkpoint');
      expect(data.events?.[0].timestamp).toBeDefined();
      expect(data.events?.[1].name).toBe('completed');
      expect(data.events?.[1].attributes).toEqual({ result: 'success' });
    });

    it('should be chainable', () => {
      const span = trace.span('test');
      const result = span.addEvent('test');
      expect(result).toBe(span);
    });
  });

  describe('setError', () => {
    it('should set error from Error object', () => {
      const span = trace.span('test');
      const error = new Error('Something went wrong');
      span.setError(error);

      const data = span.toData();
      expect(data.status).toBe('error');
      expect(data.errorType).toBe('Error');
      expect(data.errorMessage).toBe('Something went wrong');
    });

    it('should set error from string', () => {
      const span = trace.span('test');
      span.setError('Custom error message');

      const data = span.toData();
      expect(data.status).toBe('error');
      expect(data.errorType).toBe('Error');
      expect(data.errorMessage).toBe('Custom error message');
    });

    it('should use custom error type', () => {
      const span = trace.span('test');
      span.setError('Rate limit exceeded', 'RateLimitError');

      const data = span.toData();
      expect(data.errorType).toBe('RateLimitError');
    });

    it('should be chainable', () => {
      const span = trace.span('test');
      const result = span.setError('error');
      expect(result).toBe(span);
    });
  });

  describe('end', () => {
    it('should set end time and duration', () => {
      const span = trace.span('test');

      // Small delay to ensure duration > 0
      const start = Date.now();
      while (Date.now() - start < 5) { /* wait */ }

      span.end();

      const data = span.toData();
      expect(data.endTime).toBeDefined();
      expect(data.durationMs).toBeGreaterThanOrEqual(0);
    });

    it('should set status to success by default', () => {
      const span = trace.span('test');
      span.end();

      const data = span.toData();
      expect(data.status).toBe('success');
    });

    it('should preserve error status when ending', () => {
      const span = trace.span('test');
      span.setError('failed');
      span.end();

      const data = span.toData();
      expect(data.status).toBe('error');
    });

    it('should accept explicit status', () => {
      const span = trace.span('test');
      span.end('cancelled');

      const data = span.toData();
      expect(data.status).toBe('cancelled');
    });

    it('should be idempotent', () => {
      const span = trace.span('test');
      span.end();
      const data1 = span.toData();

      span.end('error');
      const data2 = span.toData();

      expect(data1.endTime).toBe(data2.endTime);
      expect(data1.status).toBe(data2.status);
    });

    it('should be chainable', () => {
      const span = trace.span('test');
      const result = span.end();
      expect(result).toBe(span);
    });
  });

  describe('toData', () => {
    it('should serialize all span properties', () => {
      const span = trace.span({ name: 'complete-span', spanType: 'llm' });
      span.setInput('input', 'input preview');
      span.setOutput('output', 'output preview');
      span.setLlmInfo({
        provider: 'openai',
        model: 'gpt-4',
        inputTokens: 100,
        outputTokens: 200,
      });
      span.setMetadata('key', 'value');
      span.addEvent('event1');
      span.end();

      const data = span.toData();

      expect(data.spanId).toBeDefined();
      expect(data.name).toBe('complete-span');
      expect(data.spanType).toBe('llm');
      expect(data.startTime).toBeDefined();
      expect(data.endTime).toBeDefined();
      expect(data.durationMs).toBeDefined();
      expect(data.provider).toBe('openai');
      expect(data.model).toBe('gpt-4');
      expect(data.inputTokens).toBe(100);
      expect(data.outputTokens).toBe(200);
      expect(data.totalTokens).toBe(300);
      expect(data.input).toBe('input');
      expect(data.output).toBe('output');
      expect(data.inputPreview).toBe('input preview');
      expect(data.outputPreview).toBe('output preview');
      expect(data.metadata).toEqual({ key: 'value' });
      expect(data.events).toHaveLength(1);
      expect(data.status).toBe('success');
    });

    it('should have undefined for unset optional properties', () => {
      const span = trace.span('minimal');
      span.end();

      const data = span.toData();

      expect(data.provider).toBeUndefined();
      expect(data.model).toBeUndefined();
      expect(data.costUsd).toBeUndefined();
    });
  });

  describe('run', () => {
    it('should execute function and auto-end span', async () => {
      const span = trace.span('test');

      const result = await span.run(async () => {
        return 'completed';
      });

      expect(result).toBe('completed');
      expect(span.toData().status).toBe('success');
      expect(span.toData().endTime).toBeDefined();
    });

    it('should set error status on exception and rethrow', async () => {
      const span = trace.span('test');

      await expect(span.run(async () => {
        throw new Error('Test error');
      })).rejects.toThrow('Test error');

      expect(span.toData().status).toBe('error');
      expect(span.toData().errorMessage).toBe('Test error');
    });
  });
});

describe('Trace', () => {
  let mockClient: { _sendTraces: ReturnType<typeof vi.fn> };
  let tracer: Tracer;

  beforeEach(() => {
    mockClient = {
      _sendTraces: vi.fn().mockResolvedValue({ success: true, count: 1 }),
    };
    tracer = new Tracer(mockClient, {
      organizationId: 'org-123',
      environment: 'production',
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('constructor', () => {
    it('should create trace with generated ID', () => {
      const trace = tracer.trace({ name: 'test-trace' });

      expect(trace.traceId).toMatch(/^[0-9a-f]{16}$/);
      expect(trace.name).toBe('test-trace');
      expect(trace.startTime).toBeDefined();
    });

    it('should use provided trace ID', () => {
      const trace = tracer.trace({ traceId: 'custom-trace-id', name: 'test' });

      expect(trace.traceId).toBe('custom-trace-id');
    });

    it('should initialize with options', () => {
      const trace = tracer.trace({
        name: 'test',
        userId: 'user-123',
        sessionId: 'session-456',
        metadata: { key: 'value' },
        tags: ['tag1', 'tag2'],
      });

      const data = trace.toData();
      expect(data.userId).toBe('user-123');
      expect(data.sessionId).toBe('session-456');
      expect(data.metadata).toEqual({ key: 'value' });
      expect(data.tags).toEqual(['tag1', 'tag2']);
    });
  });

  describe('span', () => {
    it('should create span within trace', () => {
      const trace = tracer.trace({ name: 'test' });
      const span = trace.span('child-span');

      expect(span.trace).toBe(trace);
      expect(span.name).toBe('child-span');
    });

    it('should accept span options object', () => {
      const trace = tracer.trace({ name: 'test' });
      const span = trace.span({
        name: 'llm-span',
        spanType: 'llm',
        metadata: { model: 'gpt-4' },
      });

      expect(span.spanType).toBe('llm');
    });
  });

  describe('setMetadata', () => {
    it('should set metadata key-value pairs', () => {
      const trace = tracer.trace({ name: 'test' });
      trace.setMetadata('key1', 'value1');
      trace.setMetadata('key2', 123);

      const data = trace.toData();
      expect(data.metadata?.key1).toBe('value1');
      expect(data.metadata?.key2).toBe(123);
    });

    it('should be chainable', () => {
      const trace = tracer.trace({ name: 'test' });
      const result = trace.setMetadata('key', 'value');
      expect(result).toBe(trace);
    });
  });

  describe('addTag', () => {
    it('should add tags', () => {
      const trace = tracer.trace({ name: 'test' });
      trace.addTag('production');
      trace.addTag('high-priority');

      const data = trace.toData();
      expect(data.tags).toContain('production');
      expect(data.tags).toContain('high-priority');
    });

    it('should not add duplicate tags', () => {
      const trace = tracer.trace({ name: 'test' });
      trace.addTag('tag1');
      trace.addTag('tag1');

      const data = trace.toData();
      expect(data.tags?.filter(t => t === 'tag1')).toHaveLength(1);
    });

    it('should be chainable', () => {
      const trace = tracer.trace({ name: 'test' });
      const result = trace.addTag('tag');
      expect(result).toBe(trace);
    });
  });

  describe('setUser', () => {
    it('should set user ID', () => {
      const trace = tracer.trace({ name: 'test' });
      trace.setUser('user-abc');

      const data = trace.toData();
      expect(data.userId).toBe('user-abc');
    });

    it('should be chainable', () => {
      const trace = tracer.trace({ name: 'test' });
      const result = trace.setUser('user');
      expect(result).toBe(trace);
    });
  });

  describe('setSession', () => {
    it('should set session ID', () => {
      const trace = tracer.trace({ name: 'test' });
      trace.setSession('session-xyz');

      const data = trace.toData();
      expect(data.sessionId).toBe('session-xyz');
    });

    it('should be chainable', () => {
      const trace = tracer.trace({ name: 'test' });
      const result = trace.setSession('session');
      expect(result).toBe(trace);
    });
  });

  describe('end', () => {
    it('should set end time and duration', async () => {
      const trace = tracer.trace({ name: 'test' });

      // Small delay
      await new Promise(r => setTimeout(r, 5));

      trace.end();

      const data = trace.toData();
      expect(data.endTime).toBeDefined();
      expect(data.durationMs).toBeGreaterThanOrEqual(0);
    });

    it('should determine status from spans', async () => {
      const trace = tracer.trace({ name: 'test' });
      const span = trace.span('child');
      span.setError('error');
      span.end();

      trace.end();

      const data = trace.toData();
      expect(data.status).toBe('error');
    });

    it('should set success status when no errors', () => {
      const trace = tracer.trace({ name: 'test' });
      const span = trace.span('child');
      span.end();

      trace.end();

      const data = trace.toData();
      expect(data.status).toBe('success');
    });

    it('should accept explicit status', () => {
      const trace = tracer.trace({ name: 'test' });
      trace.end('cancelled');

      const data = trace.toData();
      expect(data.status).toBe('cancelled');
    });

    it('should send trace to tracer', () => {
      const trace = tracer.trace({ name: 'test' });
      trace.end();

      expect(mockClient._sendTraces).toHaveBeenCalled();
    });

    it('should be idempotent', () => {
      const trace = tracer.trace({ name: 'test' });
      trace.end();
      const data1 = trace.toData();

      trace.end('error');
      const data2 = trace.toData();

      expect(data1.endTime).toBe(data2.endTime);
      expect(data1.status).toBe(data2.status);
    });

    it('should be chainable', () => {
      const trace = tracer.trace({ name: 'test' });
      const result = trace.end();
      expect(result).toBe(trace);
    });
  });

  describe('toData', () => {
    it('should serialize all trace properties', () => {
      const trace = tracer.trace({
        name: 'complete-trace',
        userId: 'user-123',
        sessionId: 'session-456',
        metadata: { key: 'value' },
        tags: ['tag1'],
      });

      const span = trace.span('child');
      span.end();

      trace.end();

      const data = trace.toData();

      expect(data.traceId).toBeDefined();
      expect(data.name).toBe('complete-trace');
      expect(data.startTime).toBeDefined();
      expect(data.endTime).toBeDefined();
      expect(data.durationMs).toBeDefined();
      expect(data.status).toBe('success');
      expect(data.environment).toBe('production');
      expect(data.userId).toBe('user-123');
      expect(data.sessionId).toBe('session-456');
      expect(data.metadata).toEqual({ key: 'value' });
      expect(data.tags).toEqual(['tag1']);
      expect(data.sdkName).toBe('diagnyx-node');
      expect(data.sdkVersion).toBe('0.1.0');
      expect(data.spans).toHaveLength(1);
    });
  });

  describe('run', () => {
    it('should execute function within trace context', async () => {
      const trace = tracer.trace({ name: 'test' });

      const result = await trace.run(async () => {
        const current = getCurrentTrace();
        expect(current).toBe(trace);
        return 'done';
      });

      expect(result).toBe('done');
      expect(trace.toData().status).toBe('success');
    });

    it('should set error status on exception and rethrow', async () => {
      const trace = tracer.trace({ name: 'test' });

      await expect(trace.run(async () => {
        throw new Error('Trace error');
      })).rejects.toThrow('Trace error');

      expect(trace.toData().status).toBe('error');
    });
  });
});

describe('Tracer', () => {
  let mockClient: { _sendTraces: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    mockClient = {
      _sendTraces: vi.fn().mockResolvedValue({ success: true, count: 1 }),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('constructor', () => {
    it('should initialize with config', () => {
      const tracer = new Tracer(mockClient, {
        organizationId: 'org-123',
        environment: 'staging',
        defaultMetadata: { version: '1.0' },
      });

      const trace = tracer.trace({ name: 'test' });
      const data = trace.toData();

      expect(data.environment).toBe('staging');
      expect(data.metadata?.version).toBe('1.0');
    });
  });

  describe('trace', () => {
    it('should create new trace', () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });
      const trace = tracer.trace({ name: 'test' });

      expect(trace).toBeInstanceOf(Trace);
      expect(trace.tracer).toBe(tracer);
    });

    it('should merge default metadata with trace metadata', () => {
      const tracer = new Tracer(mockClient, {
        organizationId: 'org-123',
        defaultMetadata: { default: 'value' },
      });

      const trace = tracer.trace({
        name: 'test',
        metadata: { custom: 'data' },
      });

      const data = trace.toData();
      expect(data.metadata?.default).toBe('value');
      expect(data.metadata?.custom).toBe('data');
    });
  });

  describe('span', () => {
    it('should create span in current trace context', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });
      const trace = tracer.trace({ name: 'test' });

      await trace.run(async () => {
        const span = tracer.span('standalone-span');
        expect(span.trace).toBe(trace);
      });
    });

    it('should create new trace if none exists', () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });
      const span = tracer.span('orphan-span');

      expect(span).toBeInstanceOf(Span);
      expect(span.trace).toBeInstanceOf(Trace);
    });
  });

  describe('flush', () => {
    it('should send pending traces to backend', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });
      const trace = tracer.trace({ name: 'test' });
      trace.end();

      // Wait for auto-flush
      await new Promise(r => setTimeout(r, 10));

      expect(mockClient._sendTraces).toHaveBeenCalledWith(
        'org-123',
        expect.arrayContaining([
          expect.objectContaining({ name: 'test' })
        ])
      );
    });

    it('should return null when no pending traces', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });
      const result = await tracer.flush();

      expect(result).toBeNull();
    });
  });

  describe('getCurrentTrace', () => {
    it('should return current trace in context', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });
      const trace = tracer.trace({ name: 'test' });

      await trace.run(async () => {
        const current = tracer.getCurrentTrace();
        expect(current).toBe(trace);
      });
    });

    it('should return undefined outside trace context', () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });
      const current = tracer.getCurrentTrace();

      expect(current).toBeUndefined();
    });
  });

  describe('getCurrentSpan', () => {
    it('should return current span in context', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });
      const trace = tracer.trace({ name: 'test' });
      const span = trace.span('test-span');

      await span.run(async () => {
        const current = tracer.getCurrentSpan();
        expect(current).toBe(span);
      });
    });

    it('should return undefined outside span context', () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });
      const current = tracer.getCurrentSpan();

      expect(current).toBeUndefined();
    });
  });

  describe('wrapOpenAI', () => {
    it('should wrap OpenAI client and trace calls', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });

      let createCalled = false;
      const mockOpenAI = {
        chat: {
          completions: {
            create: async () => {
              createCalled = true;
              return {
                id: 'chatcmpl-123',
                model: 'gpt-4',
                choices: [{ message: { content: 'Hello!' } }],
                usage: { prompt_tokens: 10, completion_tokens: 20 },
              };
            },
          },
        },
      };

      const wrappedClient = tracer.wrapOpenAI(mockOpenAI);

      const result = await wrappedClient.chat.completions.create({
        model: 'gpt-4',
        messages: [{ role: 'user', content: 'Hello' }],
      });

      expect(result).toHaveProperty('id', 'chatcmpl-123');
      expect(createCalled).toBe(true);

      // Wait for trace to be sent
      await new Promise(r => setTimeout(r, 10));

      expect(mockClient._sendTraces).toHaveBeenCalled();
      const sentTraces = mockClient._sendTraces.mock.calls[0][1];
      expect(sentTraces[0].spans).toHaveLength(1);
      expect(sentTraces[0].spans[0].name).toBe('openai.chat.completions.create');
      expect(sentTraces[0].spans[0].provider).toBe('openai');
      expect(sentTraces[0].spans[0].inputTokens).toBe(10);
      expect(sentTraces[0].spans[0].outputTokens).toBe(20);
    });

    it('should handle errors and still trace', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });

      const mockOpenAI = {
        chat: {
          completions: {
            create: async () => {
              throw new Error('API Error');
            },
          },
        },
      };

      const wrappedClient = tracer.wrapOpenAI(mockOpenAI);

      await expect(wrappedClient.chat.completions.create({
        model: 'gpt-4',
        messages: [],
      })).rejects.toThrow('API Error');

      // Wait for trace to be sent
      await new Promise(r => setTimeout(r, 10));

      const sentTraces = mockClient._sendTraces.mock.calls[0][1];
      expect(sentTraces[0].spans[0].status).toBe('error');
      expect(sentTraces[0].spans[0].errorMessage).toBe('API Error');
    });

    it('should use existing trace context if available', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });

      const mockOpenAI = {
        chat: {
          completions: {
            create: async () => ({
              id: 'chatcmpl-123',
              model: 'gpt-4',
              choices: [],
              usage: { prompt_tokens: 5, completion_tokens: 10 },
            }),
          },
        },
      };

      const wrappedClient = tracer.wrapOpenAI(mockOpenAI);

      const parentTrace = tracer.trace({ name: 'parent-operation' });

      await parentTrace.run(async () => {
        await wrappedClient.chat.completions.create({
          model: 'gpt-4',
          messages: [],
        });
      });

      const data = parentTrace.toData();
      expect(data.name).toBe('parent-operation');
      expect(data.spans).toHaveLength(1);
      expect(data.spans[0].name).toBe('openai.chat.completions.create');
    });
  });

  describe('wrapAnthropic', () => {
    it('should wrap Anthropic client and trace calls', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });

      let createCalled = false;
      const mockAnthropic = {
        messages: {
          create: async () => {
            createCalled = true;
            return {
              id: 'msg-123',
              model: 'claude-3-opus',
              content: [{ type: 'text', text: 'Hello!' }],
              usage: { input_tokens: 15, output_tokens: 25 },
            };
          },
        },
      };

      const wrappedClient = tracer.wrapAnthropic(mockAnthropic);

      const result = await wrappedClient.messages.create({
        model: 'claude-3-opus',
        system: 'You are helpful',
        messages: [{ role: 'user', content: 'Hello' }],
      });

      expect(result).toHaveProperty('id', 'msg-123');
      expect(createCalled).toBe(true);

      // Wait for trace to be sent
      await new Promise(r => setTimeout(r, 10));

      expect(mockClient._sendTraces).toHaveBeenCalled();
      const sentTraces = mockClient._sendTraces.mock.calls[0][1];
      expect(sentTraces[0].spans).toHaveLength(1);
      expect(sentTraces[0].spans[0].name).toBe('anthropic.messages.create');
      expect(sentTraces[0].spans[0].provider).toBe('anthropic');
      expect(sentTraces[0].spans[0].inputTokens).toBe(15);
      expect(sentTraces[0].spans[0].outputTokens).toBe(25);
    });

    it('should handle errors and still trace', async () => {
      const tracer = new Tracer(mockClient, { organizationId: 'org-123' });

      const mockAnthropic = {
        messages: {
          create: async () => {
            throw new Error('Anthropic Error');
          },
        },
      };

      const wrappedClient = tracer.wrapAnthropic(mockAnthropic);

      await expect(wrappedClient.messages.create({
        model: 'claude-3',
        messages: [],
      })).rejects.toThrow('Anthropic Error');

      // Wait for trace to be sent
      await new Promise(r => setTimeout(r, 10));

      const sentTraces = mockClient._sendTraces.mock.calls[0][1];
      expect(sentTraces[0].spans[0].status).toBe('error');
    });
  });
});

describe('Context functions', () => {
  let mockClient: { _sendTraces: ReturnType<typeof vi.fn> };
  let tracer: Tracer;

  beforeEach(() => {
    mockClient = {
      _sendTraces: vi.fn().mockResolvedValue({ success: true }),
    };
    tracer = new Tracer(mockClient, { organizationId: 'org-123' });
  });

  describe('getCurrentTrace', () => {
    it('should return undefined when not in trace context', () => {
      expect(getCurrentTrace()).toBeUndefined();
    });

    it('should return current trace when in context', async () => {
      const trace = tracer.trace({ name: 'test' });

      await trace.run(async () => {
        expect(getCurrentTrace()).toBe(trace);
      });
    });
  });

  describe('getCurrentSpan', () => {
    it('should return undefined when not in span context', () => {
      expect(getCurrentSpan()).toBeUndefined();
    });

    it('should return current span when in context', async () => {
      const trace = tracer.trace({ name: 'test' });
      const span = trace.span('test-span');

      await span.run(async () => {
        expect(getCurrentSpan()).toBe(span);
      });
    });
  });
});
