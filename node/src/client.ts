import { Tracer } from './tracing';
import { IngestResult, TraceData } from './tracing-types';
import { DiagnyxConfig, LLMCallData, BatchResult } from './types';

const DEFAULT_BASE_URL = 'https://api.diagnyx.com';
const DEFAULT_BATCH_SIZE = 100;
const DEFAULT_FLUSH_INTERVAL = 5000;
const DEFAULT_MAX_RETRIES = 3;

export class Diagnyx {
  private apiKey: string;
  private baseUrl: string;
  private batchSize: number;
  private flushIntervalMs: number;
  private maxRetries: number;
  private debug: boolean;

  private buffer: LLMCallData[] = [];
  private flushTimer: NodeJS.Timeout | null = null;
  private isFlushing = false;
  private tracers: Map<string, Tracer> = new Map();

  /** Configuration options (for use by wrappers) */
  readonly config: {
    captureFullContent: boolean;
    contentMaxLength: number;
  };

  constructor(config: DiagnyxConfig) {
    if (!config.apiKey) {
      throw new Error('Diagnyx: apiKey is required');
    }

    this.apiKey = config.apiKey;
    this.baseUrl = config.baseUrl || DEFAULT_BASE_URL;
    this.batchSize = config.batchSize || DEFAULT_BATCH_SIZE;
    this.flushIntervalMs = config.flushIntervalMs || DEFAULT_FLUSH_INTERVAL;
    this.maxRetries = config.maxRetries || DEFAULT_MAX_RETRIES;
    this.debug = config.debug || false;
    this.config = {
      captureFullContent: config.captureFullContent || false,
      contentMaxLength: config.contentMaxLength || 10000,
    };

    this.startFlushTimer();
  }

  /**
   * Get or create a tracer for an organization
   */
  tracer(
    organizationId: string,
    options: { environment?: string; defaultMetadata?: Record<string, unknown> } = {}
  ): Tracer {
    const cacheKey = `${organizationId}:${options.environment ?? ''}`;
    let tracer = this.tracers.get(cacheKey);
    if (!tracer) {
      tracer = new Tracer(this, {
        organizationId,
        environment: options.environment,
        defaultMetadata: options.defaultMetadata,
      });
      this.tracers.set(cacheKey, tracer);
    }
    return tracer;
  }

  /**
   * Send traces to the backend API (internal)
   */
  async _sendTraces(organizationId: string, traces: TraceData[]): Promise<IngestResult> {
    const payload = { traces };

    let lastError: Error | null = null;

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const response = await fetch(
          `${this.baseUrl}/api/v1/organizations/${organizationId}/tracing/ingest`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${this.apiKey}`,
            },
            body: JSON.stringify(payload),
          }
        );

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const data = (await response.json()) as { accepted?: number; failed?: number; errors?: string[] };
        return {
          accepted: data.accepted ?? traces.length,
          failed: data.failed ?? 0,
          errors: data.errors,
        };
      } catch (error) {
        lastError = error as Error;
        this.log(`Trace send attempt ${attempt + 1} failed:`, lastError.message);

        if (attempt < this.maxRetries - 1) {
          await this.sleep(Math.pow(2, attempt) * 1000);
        }
      }
    }

    throw lastError;
  }

  /**
   * Track a single LLM call
   */
  async trackCall(data: LLMCallData): Promise<void> {
    this.buffer.push(this.normalizeCallData(data));

    if (this.buffer.length >= this.batchSize) {
      await this.flush();
    }
  }

  /**
   * Track multiple LLM calls at once
   */
  async trackCalls(calls: LLMCallData[]): Promise<void> {
    for (const call of calls) {
      this.buffer.push(this.normalizeCallData(call));
    }

    if (this.buffer.length >= this.batchSize) {
      await this.flush();
    }
  }

  /**
   * Flush the buffer immediately
   */
  async flush(): Promise<BatchResult | null> {
    if (this.isFlushing || this.buffer.length === 0) {
      return null;
    }

    this.isFlushing = true;
    const calls = [...this.buffer];
    this.buffer = [];

    try {
      const result = await this.sendBatch(calls);
      this.log('Flushed', calls.length, 'calls');
      return result;
    } catch (error) {
      // On error, put calls back in buffer
      this.buffer = [...calls, ...this.buffer];
      this.log('Flush failed, calls returned to buffer');
      throw error;
    } finally {
      this.isFlushing = false;
    }
  }

  /**
   * Shutdown the client, flushing any remaining calls
   */
  async shutdown(): Promise<void> {
    this.stopFlushTimer();
    if (this.buffer.length > 0) {
      await this.flush();
    }
  }

  /**
   * Get the current buffer size
   */
  get bufferSize(): number {
    return this.buffer.length;
  }

  private normalizeCallData(data: LLMCallData): LLMCallData {
    return {
      ...data,
      timestamp: data.timestamp
        ? data.timestamp instanceof Date
          ? data.timestamp.toISOString()
          : data.timestamp
        : new Date().toISOString(),
    };
  }

  private async sendBatch(calls: LLMCallData[]): Promise<BatchResult> {
    const payload = {
      calls: calls.map((call) => ({
        provider: call.provider,
        model: call.model,
        inputTokens: call.inputTokens,
        outputTokens: call.outputTokens,
        latencyMs: call.latencyMs,
        ttftMs: call.ttftMs,
        status: call.status,
        errorCode: call.errorCode,
        errorMessage: call.errorMessage,
        endpoint: call.endpoint,
        projectId: call.projectId,
        environment: call.environment,
        traceId: call.traceId,
        userIdentifier: call.userIdentifier,
        timestamp: call.timestamp,
      })),
    };

    let lastError: Error | null = null;

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const response = await fetch(`${this.baseUrl}/ingest/llm/batch`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${this.apiKey}`,
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        return (await response.json()) as BatchResult;
      } catch (error) {
        lastError = error as Error;
        this.log(`Attempt ${attempt + 1} failed:`, lastError.message);

        if (attempt < this.maxRetries - 1) {
          // Exponential backoff
          await this.sleep(Math.pow(2, attempt) * 1000);
        }
      }
    }

    throw lastError;
  }

  private startFlushTimer(): void {
    this.flushTimer = setInterval(() => {
      if (this.buffer.length > 0) {
        this.flush().catch((err) => this.log('Background flush error:', err));
      }
    }, this.flushIntervalMs);
  }

  private stopFlushTimer(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
      this.flushTimer = null;
    }
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private log(...args: unknown[]): void {
    if (this.debug) {
      console.log('[Diagnyx]', ...args);
    }
  }
}
