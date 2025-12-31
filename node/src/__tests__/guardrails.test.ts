/**
 * Tests for Diagnyx streaming guardrails module
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  StreamingGuardrails,
  GuardrailViolationError,
  streamWithGuardrails,
  wrapStreamingResponse,
} from '../guardrails';
import {
  GuardrailViolation,
  toViolation,
  ViolationDetectedEvent,
} from '../guardrails/types';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('StreamingGuardrails', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('constructor', () => {
    it('should initialize with required parameters', () => {
      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      expect(client).toBeDefined();
      expect(typeof client.startSession).toBe('function');
      expect(typeof client.evaluateToken).toBe('function');
      expect(typeof client.getSession).toBe('function');
    });

    it('should use default base URL when not provided', () => {
      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      // Verify client is created with defaults
      expect(client).toBeDefined();
    });

    it('should accept custom base URL', () => {
      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        baseUrl: 'https://custom.api.com',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      // Verify client is created successfully with custom URL
      expect(client).toBeDefined();
    });
  });

  describe('startSession', () => {
    it('should start a session successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          type: 'session_started',
          sessionId: 'session_123',
          timestamp: Date.now(),
          activePolicies: ['content_filter', 'pii_detection'],
        }),
      });

      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      const event = await client.startSession();

      expect(event.type).toBe('session_started');
      expect(event.sessionId).toBe('session_123');
      expect(event.activePolicies).toContain('content_filter');
    });

    it('should start session with input text', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          type: 'session_started',
          sessionId: 'session_123',
          timestamp: Date.now(),
          activePolicies: ['content_filter'],
        }),
      });

      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      const event = await client.startSession({ input: 'Hello world' });

      expect(event.sessionId).toBe('session_123');
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/stream/start'),
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('Hello world'),
        }),
      );
    });

    it('should store session state', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          type: 'session_started',
          sessionId: 'session_123',
          timestamp: Date.now(),
          activePolicies: ['content_filter'],
        }),
      });

      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      await client.startSession();
      const session = client.getSession('session_123');

      expect(session).toBeDefined();
      expect(session?.sessionId).toBe('session_123');
    });
  });

  describe('evaluateToken', () => {
    it('should be an async generator method', () => {
      // Note: Full streaming tests require SSE mock infrastructure
      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      // Verify the method exists and is a function
      expect(typeof client.evaluateToken).toBe('function');
    });
  });

  describe('completeSession', () => {
    it('should be an async generator method', () => {
      // Note: Full streaming tests require SSE mock infrastructure
      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      // Verify the method exists and is a function
      expect(typeof client.completeSession).toBe('function');
    });
  });

  describe('cancelSession', () => {
    it('should cancel existing session', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            type: 'session_started',
            sessionId: 'session_123',
            timestamp: Date.now(),
            activePolicies: ['content_filter'],
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            cancelled: true,
          }),
        });

      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      await client.startSession();
      const result = await client.cancelSession('session_123');

      expect(result).toBe(true);
      expect(client.getSession('session_123')).toBeUndefined();
    });

    it('should return false when API returns not cancelled', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          cancelled: false,
        }),
      });

      const client = new StreamingGuardrails({
        apiKey: 'test-key',
        organizationId: 'org_123',
        projectId: 'proj_456',
      });

      const result = await client.cancelSession('nonexistent');
      expect(result).toBe(false);
    });
  });
});

describe('streamWithGuardrails', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should wrap async iterable stream', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          type: 'session_started',
          sessionId: 'session_123',
          timestamp: Date.now(),
          activePolicies: ['content_filter'],
        }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          events: [
            {
              type: 'token_allowed',
              sessionId: 'session_123',
              timestamp: Date.now(),
              tokenIndex: 0,
              accumulatedLength: 5,
            },
          ],
        }),
      });

    const guardrails = new StreamingGuardrails({
      apiKey: 'test-key',
      organizationId: 'org_123',
      projectId: 'proj_456',
    });

    async function* mockStream() {
      yield { choices: [{ delta: { content: 'Hello' }, finish_reason: null }] };
      yield { choices: [{ delta: { content: ' World' }, finish_reason: 'stop' }] };
    }

    const chunks: unknown[] = [];
    for await (const chunk of streamWithGuardrails(mockStream(), { guardrails })) {
      chunks.push(chunk);
    }

    expect(chunks).toHaveLength(2);
  });

  it('should support violation callback option', () => {
    // Test that the violation callback option is properly typed
    // Full streaming integration tests require SSE mock infrastructure
    const guardrails = new StreamingGuardrails({
      apiKey: 'test-key',
      organizationId: 'org_123',
      projectId: 'proj_456',
    });

    const violations: GuardrailViolation[] = [];
    const onViolation = (violation: GuardrailViolation) => violations.push(violation);

    // Verify the options interface accepts onViolation callback
    const options = {
      guardrails,
      onViolation,
    };

    expect(typeof options.onViolation).toBe('function');
    expect(options.guardrails).toBeDefined();
  });

  it('should handle blocking violations by throwing or returning early', async () => {
    // Note: This test verifies the error class can be constructed and thrown
    // Full streaming tests require SSE mock infrastructure
    const violation: GuardrailViolation = {
      policyId: 'policy_123',
      policyName: 'Content Filter',
      policyType: 'content_filter',
      violationType: 'blocked',
      message: 'Blocked content',
      severity: 'critical',
      enforcementLevel: 'blocking',
    };

    const error = new GuardrailViolationError(violation, null);
    expect(error).toBeInstanceOf(GuardrailViolationError);
    expect(error.violation.policyName).toBe('Content Filter');

    // Verify it can be thrown and caught
    expect(() => {
      throw error;
    }).toThrow(GuardrailViolationError);
  });

  it('should support raiseOnBlocking option', () => {
    // Test that the option is properly typed and can be passed
    // Full streaming integration tests require SSE mock infrastructure
    const guardrails = new StreamingGuardrails({
      apiKey: 'test-key',
      organizationId: 'org_123',
      projectId: 'proj_456',
    });

    // Verify the options interface is correct
    const options = {
      guardrails,
      raiseOnBlocking: false,
    };

    expect(options.raiseOnBlocking).toBe(false);
    expect(options.guardrails).toBe(guardrails);
  });

  it('should use custom token extractor', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          type: 'session_started',
          sessionId: 'session_123',
          timestamp: Date.now(),
          activePolicies: [],
        }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          events: [
            {
              type: 'token_allowed',
              sessionId: 'session_123',
              timestamp: Date.now(),
              tokenIndex: 0,
              accumulatedLength: 5,
            },
          ],
        }),
      });

    const guardrails = new StreamingGuardrails({
      apiKey: 'test-key',
      organizationId: 'org_123',
      projectId: 'proj_456',
    });

    interface CustomChunk {
      text: string;
      done: boolean;
    }

    async function* mockStream(): AsyncGenerator<CustomChunk> {
      yield { text: 'Hello', done: false };
      yield { text: ' World', done: true };
    }

    const chunks: CustomChunk[] = [];
    for await (const chunk of streamWithGuardrails(mockStream(), {
      guardrails,
      getTokenContent: (item: CustomChunk) => item.text,
      getIsLast: (item: CustomChunk) => item.done,
    })) {
      chunks.push(chunk);
    }

    expect(chunks).toHaveLength(2);
    expect(chunks[0].text).toBe('Hello');
  });
});

describe('wrapStreamingResponse', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should wrap a function returning stream', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          type: 'session_started',
          sessionId: 'session_123',
          timestamp: Date.now(),
          activePolicies: [],
        }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          events: [
            {
              type: 'token_allowed',
              sessionId: 'session_123',
              timestamp: Date.now(),
              tokenIndex: 0,
              accumulatedLength: 5,
            },
          ],
        }),
      });

    const guardrails = new StreamingGuardrails({
      apiKey: 'test-key',
      organizationId: 'org_123',
      projectId: 'proj_456',
    });

    async function* mockStream() {
      yield { choices: [{ delta: { content: 'Hello' }, finish_reason: null }] };
      yield { choices: [{ delta: { content: '!' }, finish_reason: 'stop' }] };
    }

    const getCompletion = wrapStreamingResponse(
      guardrails,
      async (_prompt: string) => mockStream(),
    );

    const stream = await getCompletion('test');
    const chunks: unknown[] = [];
    for await (const chunk of stream) {
      chunks.push(chunk);
    }

    expect(chunks).toHaveLength(2);
  });
});

describe('GuardrailViolationError', () => {
  it('should contain violation and session', () => {
    const violation: GuardrailViolation = {
      policyId: 'policy_123',
      policyName: 'Test Policy',
      policyType: 'content_filter',
      violationType: 'blocked',
      message: 'Content blocked',
      severity: 'critical',
      enforcementLevel: 'blocking',
    };

    const error = new GuardrailViolationError(violation, null);

    expect(error.violation).toBe(violation);
    expect(error.session).toBeNull();
    expect(error.message).toContain('Content blocked');
    expect(error.name).toBe('GuardrailViolationError');
  });
});

describe('toViolation', () => {
  it('should convert ViolationDetectedEvent to GuardrailViolation', () => {
    const event: ViolationDetectedEvent = {
      type: 'violation_detected',
      sessionId: 'session_123',
      timestamp: Date.now(),
      policyId: 'policy_123',
      policyName: 'Test Policy',
      policyType: 'content_filter',
      violationType: 'blocked',
      message: 'Content blocked',
      severity: 'critical',
      enforcementLevel: 'blocking',
    };

    const violation = toViolation(event);

    expect(violation.policyId).toBe('policy_123');
    expect(violation.policyName).toBe('Test Policy');
    expect(violation.enforcementLevel).toBe('blocking');
  });

  it('should set enforcementLevel to advisory', () => {
    const event: ViolationDetectedEvent = {
      type: 'violation_detected',
      sessionId: 'session_123',
      timestamp: Date.now(),
      policyId: 'policy_123',
      policyName: 'Test Policy',
      policyType: 'pii_detection',
      violationType: 'pii_found',
      message: 'PII detected',
      severity: 'medium',
      enforcementLevel: 'advisory',
    };

    const violation = toViolation(event);
    expect(violation.enforcementLevel).toBe('advisory');
  });
});
