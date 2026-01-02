/**
 * Streaming guardrails for real-time token-by-token LLM output validation.
 *
 * This module provides the StreamingGuardrail class for evaluating LLM output
 * tokens as they are generated, enabling early termination on policy violations.
 *
 * @example
 * ```typescript
 * import { StreamingGuardrail } from '@diagnyx/node';
 *
 * const guardrail = new StreamingGuardrail({
 *   apiKey: 'dx_...',
 *   organizationId: 'org_123',
 *   projectId: 'proj_456',
 * });
 *
 * // Start a session
 * const session = await guardrail.startSession();
 *
 * // Evaluate tokens as they arrive
 * for await (const chunk of openaiStream) {
 *   const token = chunk.choices[0]?.delta?.content || '';
 *   const isLast = chunk.choices[0]?.finish_reason !== null;
 *
 *   for await (const filteredToken of guardrail.evaluate(token, { isLast })) {
 *     process.stdout.write(filteredToken);
 *   }
 * }
 * ```
 */

import { io, Socket } from 'socket.io-client';

/**
 * Enforcement level for guardrail policies
 */
export type EnforcementLevel = 'advisory' | 'warning' | 'blocking';

/**
 * Types of streaming events
 */
export type StreamingEventType =
  | 'session_started'
  | 'token_allowed'
  | 'violation_detected'
  | 'early_termination'
  | 'session_complete'
  | 'error'
  | 'heartbeat';

/**
 * Configuration for StreamingGuardrail
 */
export interface StreamingGuardrailConfig {
  apiKey: string;
  organizationId: string;
  projectId: string;
  baseUrl?: string;
  wsUrl?: string;
  timeout?: number;
  evaluateEveryNTokens?: number;
  enableEarlyTermination?: boolean;
  useWebSocket?: boolean;
  debug?: boolean;
}

/**
 * Guardrail violation details
 */
export interface GuardrailViolation {
  policyId: string;
  policyName: string;
  policyType: string;
  violationType: string;
  message: string;
  severity: string;
  enforcementLevel: EnforcementLevel;
  details?: Record<string, unknown>;
}

/**
 * Streaming session state
 */
export interface StreamingSession {
  sessionId: string;
  organizationId: string;
  projectId: string;
  activePolicies: string[];
  tokensProcessed: number;
  violations: GuardrailViolation[];
  terminated: boolean;
  terminationReason?: string;
  allowed: boolean;
  accumulatedText: string;
}

/**
 * Options for starting a session
 */
export interface StartSessionOptions {
  input?: string;
}

/**
 * Options for evaluating a token
 */
export interface EvaluateOptions {
  tokenIndex?: number;
  isLast?: boolean;
}

/**
 * Error thrown when a blocking guardrail violation terminates the stream
 */
export class GuardrailViolationError extends Error {
  constructor(
    public readonly violation: GuardrailViolation,
    public readonly session: StreamingSession,
  ) {
    super(`Guardrail violation: ${violation.message}`);
    this.name = 'GuardrailViolationError';
  }
}

/**
 * Token-by-token streaming guardrail for LLM output validation.
 *
 * Provides real-time evaluation of LLM response tokens against configured
 * guardrail policies with support for early termination on blocking violations.
 *
 * Supports both HTTP SSE and WebSocket connections for streaming evaluation.
 */
export class StreamingGuardrail {
  private readonly config: Required<StreamingGuardrailConfig>;
  private session: StreamingSession | null = null;
  private tokenIndex = 0;
  private wsClient: Socket | null = null;

  constructor(config: StreamingGuardrailConfig) {
    const baseUrl = config.baseUrl?.replace(/\/$/, '') || 'https://api.diagnyx.io';
    const wsUrl =
      config.wsUrl ||
      (baseUrl.startsWith('https://')
        ? baseUrl.replace('https://', 'wss://') + '/guardrails'
        : baseUrl.replace('http://', 'ws://') + '/guardrails');

    this.config = {
      apiKey: config.apiKey,
      organizationId: config.organizationId,
      projectId: config.projectId,
      baseUrl,
      wsUrl,
      timeout: config.timeout || 30000,
      evaluateEveryNTokens: config.evaluateEveryNTokens || 10,
      enableEarlyTermination: config.enableEarlyTermination ?? true,
      useWebSocket: config.useWebSocket || false,
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
   * Start a new streaming guardrail session
   */
  async startSession(options: StartSessionOptions = {}): Promise<StreamingSession> {
    if (this.config.useWebSocket) {
      return this.startWsSession(options);
    }

    const payload = {
      projectId: this.config.projectId,
      evaluateEveryNTokens: this.config.evaluateEveryNTokens,
      enableEarlyTermination: this.config.enableEarlyTermination,
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

    if (data.type === 'session_started') {
      this.session = {
        sessionId: data.sessionId,
        organizationId: this.config.organizationId,
        projectId: this.config.projectId,
        activePolicies: data.activePolicies || [],
        tokensProcessed: 0,
        violations: [],
        terminated: false,
        allowed: true,
        accumulatedText: '',
      };
      this.tokenIndex = 0;
      this.log(`Session started: ${this.session.sessionId}`);
      return this.session;
    } else if (data.type === 'error') {
      throw new Error(`Failed to start session: ${data.error}`);
    }

    throw new Error(`Unexpected response type: ${data.type}`);
  }

  /**
   * Start session via WebSocket
   */
  private async startWsSession(options: StartSessionOptions): Promise<StreamingSession> {
    return new Promise((resolve, reject) => {
      this.wsClient = io(this.config.wsUrl, {
        auth: { token: this.config.apiKey },
        transports: ['websocket'],
      });

      this.wsClient.on('connect', () => {
        this.log('WebSocket connected');
        this.wsClient?.emit('start_session', {
          projectId: this.config.projectId,
          input: options.input,
          evaluateEveryNTokens: this.config.evaluateEveryNTokens,
          enableEarlyTermination: this.config.enableEarlyTermination,
        });
      });

      this.wsClient.on('session_started', (data: any) => {
        this.session = {
          sessionId: data.sessionId,
          organizationId: this.config.organizationId,
          projectId: this.config.projectId,
          activePolicies: data.activePolicies || [],
          tokensProcessed: 0,
          violations: [],
          terminated: false,
          allowed: true,
          accumulatedText: '',
        };
        this.tokenIndex = 0;
        this.log(`Session started (WS): ${this.session.sessionId}`);
        resolve(this.session);
      });

      this.wsClient.on('error', (error: any) => {
        reject(new Error(`WebSocket error: ${error.error || error}`));
      });

      this.wsClient.on('connect_error', (error: Error) => {
        reject(new Error(`WebSocket connection failed: ${error.message}`));
      });
    });
  }

  /**
   * Evaluate a token against guardrail policies
   *
   * Yields the token if it passes validation. Throws GuardrailViolationError
   * if a blocking violation is detected and early termination is enabled.
   */
  async *evaluate(token: string, options: EvaluateOptions = {}): AsyncGenerator<string> {
    if (!this.session) {
      throw new Error('No active session. Call startSession() first.');
    }

    if (this.config.useWebSocket && this.wsClient) {
      yield* this.evaluateWs(token, options);
      return;
    }

    const payload = {
      sessionId: this.session.sessionId,
      token,
      tokenIndex: options.tokenIndex ?? this.tokenIndex,
      isLast: options.isLast ?? false,
    };

    this.session.accumulatedText += token;
    this.tokenIndex++;

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
      throw new Error('No response body');
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
            const eventType = data.type;

            if (eventType === 'token_allowed') {
              this.session.tokensProcessed = (data.tokenIndex ?? 0) + 1;
              yield token;
            } else if (eventType === 'violation_detected') {
              const violation = this.parseViolation(data);
              this.session.violations.push(violation);

              if (violation.enforcementLevel === 'blocking') {
                this.session.allowed = false;
              }
            } else if (eventType === 'early_termination') {
              const violation = this.parseViolation(data.blockingViolation || {});
              this.session.terminated = true;
              this.session.terminationReason = data.reason;
              this.session.allowed = false;
              throw new GuardrailViolationError(violation, this.session);
            } else if (eventType === 'session_complete') {
              this.session.tokensProcessed = data.totalTokens ?? 0;
              this.session.allowed = data.allowed ?? true;
            } else if (eventType === 'error') {
              this.log(`Error: ${data.error}`);
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
   * Evaluate token via WebSocket
   */
  private async *evaluateWs(token: string, options: EvaluateOptions): AsyncGenerator<string> {
    if (!this.wsClient || !this.session) {
      throw new Error('WebSocket not connected');
    }

    const session = this.session;
    session.accumulatedText += token;
    const currentIndex = this.tokenIndex++;

    return yield* new Promise<AsyncGenerator<string>>((resolve) => {
      const results: string[] = [];
      let resolved = false;

      const handlers = {
        token_allowed: (data: any) => {
          session.tokensProcessed = (data.tokenIndex ?? 0) + 1;
          results.push(token);
          cleanup();
          resolve(
            (async function* () {
              yield token;
            })(),
          );
        },
        violation_detected: (data: any) => {
          const violation = this.parseViolation(data);
          session.violations.push(violation);
          if (violation.enforcementLevel === 'blocking') {
            session.allowed = false;
          }
        },
        early_termination: (data: any) => {
          const violation = this.parseViolation(data.blockingViolation || {});
          session.terminated = true;
          session.terminationReason = data.reason;
          session.allowed = false;
          cleanup();
          resolve(
            (async function* () {
              throw new GuardrailViolationError(violation, session);
            })(),
          );
        },
        session_complete: (data: any) => {
          session.tokensProcessed = data.totalTokens ?? 0;
          session.allowed = data.allowed ?? true;
          cleanup();
          resolve(
            (async function* () {
              // Nothing to yield on complete
            })(),
          );
        },
      };

      const cleanup = () => {
        if (resolved) return;
        resolved = true;
        Object.keys(handlers).forEach((event) => {
          this.wsClient?.off(event, (handlers as any)[event]);
        });
      };

      Object.keys(handlers).forEach((event) => {
        this.wsClient?.on(event, (handlers as any)[event]);
      });

      this.wsClient?.emit('evaluate_token', {
        sessionId: session.sessionId,
        token,
        tokenIndex: options.tokenIndex ?? currentIndex,
        isLast: options.isLast ?? false,
      });
    });
  }

  /**
   * Complete the current session
   */
  async completeSession(): Promise<StreamingSession> {
    if (!this.session) {
      throw new Error('No active session');
    }

    if (this.config.useWebSocket && this.wsClient) {
      return this.completeWsSession();
    }

    const response = await fetch(
      `${this.getBaseEndpoint()}/evaluate/stream/${this.session.sessionId}/complete`,
      {
        method: 'POST',
        headers: this.getHeaders(),
      },
    );

    if (!response.ok) {
      throw new Error(`Failed to complete session: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (reader) {
      const decoder = new TextDecoder();
      let buffer = '';

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
            if (data.type === 'session_complete') {
              this.session.tokensProcessed = data.totalTokens ?? 0;
              this.session.allowed = data.allowed ?? true;
            }
          } catch {
            // Skip invalid JSON
          }
        }
      }
      reader.releaseLock();
    }

    const session = this.session;
    this.session = null;
    return session;
  }

  /**
   * Complete session via WebSocket
   */
  private async completeWsSession(): Promise<StreamingSession> {
    return new Promise((resolve) => {
      if (!this.wsClient || !this.session) {
        throw new Error('WebSocket not connected');
      }

      const session = this.session;

      this.wsClient.once('session_complete', (data: any) => {
        session.tokensProcessed = data.totalTokens ?? 0;
        session.allowed = data.allowed ?? true;
        this.session = null;
        resolve(session);
      });

      this.wsClient.emit('complete_session', {
        sessionId: session.sessionId,
      });
    });
  }

  /**
   * Cancel the current session
   */
  async cancelSession(): Promise<boolean> {
    if (!this.session) {
      return false;
    }

    if (this.config.useWebSocket && this.wsClient) {
      this.wsClient.emit('cancel_session', {
        sessionId: this.session.sessionId,
      });
      this.session = null;
      return true;
    }

    const response = await fetch(
      `${this.getBaseEndpoint()}/evaluate/stream/${this.session.sessionId}`,
      {
        method: 'DELETE',
        headers: this.getHeaders(),
      },
    );

    if (!response.ok) {
      throw new Error(`Failed to cancel session: ${response.statusText}`);
    }

    const data = await response.json();
    this.session = null;
    return data.cancelled ?? false;
  }

  /**
   * Get the current session
   */
  getSession(): StreamingSession | null {
    return this.session;
  }

  /**
   * Check if there's an active session
   */
  isActive(): boolean {
    return this.session !== null && !this.session.terminated;
  }

  /**
   * Parse violation data
   */
  private parseViolation(data: Record<string, any>): GuardrailViolation {
    const enforcement = data.enforcementLevel || data.enforcement_level || 'advisory';
    return {
      policyId: data.policyId || data.policy_id || '',
      policyName: data.policyName || data.policy_name || '',
      policyType: data.policyType || data.policy_type || '',
      violationType: data.violationType || data.violation_type || '',
      message: data.message || '',
      severity: data.severity || '',
      enforcementLevel: enforcement as EnforcementLevel,
      details: data.details,
    };
  }

  /**
   * Close the client and release resources
   */
  close(): void {
    if (this.wsClient) {
      this.wsClient.disconnect();
      this.wsClient = null;
    }
    this.session = null;
  }
}

/**
 * Wrap an async token stream with guardrail protection
 */
export async function* streamWithGuardrails(
  guardrail: StreamingGuardrail,
  tokenStream: AsyncIterable<string>,
  inputText?: string,
): AsyncGenerator<string> {
  await guardrail.startSession({ input: inputText });

  try {
    for await (const token of tokenStream) {
      for await (const filteredToken of guardrail.evaluate(token)) {
        yield filteredToken;
      }
    }
  } finally {
    if (guardrail.isActive()) {
      await guardrail.completeSession();
    }
  }
}
