/**
 * Streaming guardrails client for real-time LLM response validation
 */

import {
  EarlyTerminationEvent,
  ErrorEvent,
  EvaluateTokenOptions,
  GuardrailSession,
  GuardrailViolation,
  parseEvent,
  SessionCompleteEvent,
  SessionStartedEvent,
  StartSessionOptions,
  StreamingEvaluationEvent,
  StreamingGuardrailsConfig,
  toViolation,
  ViolationDetectedEvent,
} from './types';

/**
 * Error thrown when a blocking guardrail violation terminates the stream
 */
export class GuardrailViolationError extends Error {
  constructor(
    public readonly violation: GuardrailViolation,
    public readonly session: GuardrailSession,
  ) {
    super(`Guardrail violation: ${violation.message}`);
    this.name = 'GuardrailViolationError';
  }
}

/**
 * Client for streaming guardrails evaluation.
 *
 * Provides real-time validation of LLM response tokens against configured
 * guardrail policies with support for early termination on blocking violations.
 *
 * @example
 * ```typescript
 * import { StreamingGuardrails } from '@diagnyx/node';
 *
 * const guardrails = new StreamingGuardrails({
 *   apiKey: 'dx_...',
 *   organizationId: 'org_123',
 *   projectId: 'proj_456',
 * });
 *
 * // Start a session
 * const session = await guardrails.startSession();
 *
 * // Evaluate tokens as they arrive
 * for await (const chunk of openaiStream) {
 *   for await (const event of guardrails.evaluateToken(
 *     session.sessionId,
 *     chunk.choices[0]?.delta?.content || '',
 *     { isLast: chunk.choices[0]?.finish_reason !== null }
 *   )) {
 *     if (event.type === 'early_termination') {
 *       console.log('Stream terminated:', event.reason);
 *       break;
 *     }
 *   }
 *   yield chunk;
 * }
 * ```
 */
export class StreamingGuardrails {
  private readonly config: Required<StreamingGuardrailsConfig>;
  private readonly sessions: Map<string, GuardrailSession> = new Map();

  constructor(config: StreamingGuardrailsConfig) {
    this.config = {
      apiKey: config.apiKey,
      organizationId: config.organizationId,
      projectId: config.projectId,
      baseUrl: config.baseUrl?.replace(/\/$/, '') || 'https://api.diagnyx.io',
      timeout: config.timeout || 30000,
      evaluateEveryNTokens: config.evaluateEveryNTokens || 10,
      enableEarlyTermination: config.enableEarlyTermination ?? true,
      debug: config.debug || false,
    };
  }

  private log(message: string): void {
    if (this.config.debug) {
      console.log(`[DiagnyxGuardrails] ${message}`);
    }
  }

  private getHeaders(): Record<string, string> {
    return {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${this.config.apiKey}`,
      Accept: 'text/event-stream',
    };
  }

  private getBaseEndpoint(): string {
    return `${this.config.baseUrl}/api/v1/organizations/${this.config.organizationId}/guardrails`;
  }

  /**
   * Start a new streaming guardrails session
   */
  async startSession(options: StartSessionOptions = {}): Promise<SessionStartedEvent> {
    const payload = {
      projectId: this.config.projectId,
      evaluateEveryNTokens: this.config.evaluateEveryNTokens,
      enableEarlyTermination: this.config.enableEarlyTermination,
      ...(options.sessionId && { sessionId: options.sessionId }),
      ...(options.input && { input: options.input }),
    };

    const response = await fetch(`${this.getBaseEndpoint()}/evaluate/stream/start`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Failed to start session: ${response.statusText}`);
    }

    const data = await response.json();
    const event = parseEvent(data);

    if (event.type === 'session_started') {
      const sessionEvent = event as SessionStartedEvent;
      this.sessions.set(sessionEvent.sessionId, {
        sessionId: sessionEvent.sessionId,
        organizationId: this.config.organizationId,
        projectId: this.config.projectId,
        activePolicies: sessionEvent.activePolicies,
        tokensProcessed: 0,
        violations: [],
        terminated: false,
        allowed: true,
      });
      this.log(`Session started: ${sessionEvent.sessionId}`);
      return sessionEvent;
    } else if (event.type === 'error') {
      throw new Error(`Failed to start session: ${(event as ErrorEvent).error}`);
    }

    throw new Error(`Unexpected response type: ${event.type}`);
  }

  /**
   * Evaluate a token against guardrail policies
   */
  async *evaluateToken(
    sessionId: string,
    token: string,
    options: EvaluateTokenOptions = {},
  ): AsyncGenerator<StreamingEvaluationEvent> {
    const session = this.sessions.get(sessionId);
    if (!session) {
      yield {
        type: 'error',
        sessionId,
        timestamp: Date.now(),
        error: 'Session not found',
        code: 'SESSION_NOT_FOUND',
      };
      return;
    }

    const payload = {
      sessionId,
      token,
      ...(options.tokenIndex !== undefined && { tokenIndex: options.tokenIndex }),
      ...(options.isLast !== undefined && { isLast: options.isLast }),
    };

    const response = await fetch(`${this.getBaseEndpoint()}/evaluate/stream`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Token evaluation failed: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      yield {
        type: 'error',
        sessionId,
        timestamp: Date.now(),
        error: 'No response body',
      };
      return;
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;

          try {
            const data = JSON.parse(line.slice(6));
            const event = parseEvent(data);

            this.updateSession(session, event);

            yield event;

            if (event.type === 'early_termination') {
              const termEvent = event as EarlyTerminationEvent;
              if (termEvent.blockingViolation) {
                throw new GuardrailViolationError(toViolation(termEvent.blockingViolation), session);
              }
              return;
            }

            if (event.type === 'session_complete' || event.type === 'error') {
              return;
            }
          } catch (e) {
            if (e instanceof GuardrailViolationError) throw e;
            this.log(`Failed to parse event: ${e}`);
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  /**
   * Complete a streaming session manually
   */
  async *completeSession(sessionId: string): AsyncGenerator<StreamingEvaluationEvent> {
    const response = await fetch(`${this.getBaseEndpoint()}/evaluate/stream/${sessionId}/complete`, {
      method: 'POST',
      headers: this.getHeaders(),
    });

    if (!response.ok) {
      throw new Error(`Failed to complete session: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      yield {
        type: 'error',
        sessionId,
        timestamp: Date.now(),
        error: 'No response body',
      };
      return;
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;

          try {
            const data = JSON.parse(line.slice(6));
            yield parseEvent(data);
          } catch {
            // Skip invalid JSON
          }
        }
      }
    } finally {
      reader.releaseLock();
      this.sessions.delete(sessionId);
    }
  }

  /**
   * Cancel a streaming session
   */
  async cancelSession(sessionId: string): Promise<boolean> {
    const response = await fetch(`${this.getBaseEndpoint()}/evaluate/stream/${sessionId}`, {
      method: 'DELETE',
      headers: this.getHeaders(),
    });

    if (!response.ok) {
      throw new Error(`Failed to cancel session: ${response.statusText}`);
    }

    const data = await response.json();
    this.sessions.delete(sessionId);
    return data.cancelled ?? false;
  }

  /**
   * Get current session state
   */
  getSession(sessionId: string): GuardrailSession | undefined {
    return this.sessions.get(sessionId);
  }

  private updateSession(session: GuardrailSession, event: StreamingEvaluationEvent): void {
    switch (event.type) {
      case 'violation_detected': {
        const violation = toViolation(event as ViolationDetectedEvent);
        session.violations.push(violation);
        if ((event as ViolationDetectedEvent).enforcementLevel === 'blocking') {
          session.allowed = false;
        }
        break;
      }

      case 'early_termination': {
        const termEvent = event as EarlyTerminationEvent;
        session.terminated = true;
        session.terminationReason = termEvent.reason;
        session.allowed = false;
        session.tokensProcessed = termEvent.tokensProcessed;
        break;
      }

      case 'session_complete': {
        const completeEvent = event as SessionCompleteEvent;
        session.tokensProcessed = completeEvent.totalTokens;
        session.allowed = completeEvent.allowed;
        break;
      }
    }
  }
}
