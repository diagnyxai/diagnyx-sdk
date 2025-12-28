/**
 * Tracing context and span management for Diagnyx SDK
 */

import { AsyncLocalStorage } from 'async_hooks';
import {
  IngestResult,
  SpanData,
  SpanEvent,
  SpanOptions,
  SpanStatus,
  SpanType,
  TraceData,
  TraceOptions,
  TraceStatus,
  TracerConfig,
} from './tracing-types';

const SDK_NAME = 'diagnyx-node';
const SDK_VERSION = '0.1.0';

// Context storage for traces and spans
const traceStorage = new AsyncLocalStorage<Trace>();
const spanStorage = new AsyncLocalStorage<Span>();

/**
 * Generate a unique ID for traces and spans
 */
function generateId(): string {
  const hex = '0123456789abcdef';
  let id = '';
  for (let i = 0; i < 16; i++) {
    id += hex[Math.floor(Math.random() * 16)];
  }
  return id;
}

/**
 * Get current time as ISO string
 */
function nowIso(): string {
  return new Date().toISOString();
}

/**
 * A span represents a single operation within a trace
 */
export class Span {
  readonly trace: Trace;
  readonly spanId: string;
  readonly name: string;
  readonly spanType: SpanType;
  readonly parent: Span | null;
  readonly parentSpanId: string | null;
  readonly startTime: string;
  readonly startTimestamp: number;

  private _endTime: string | null = null;
  private _durationMs: number | null = null;
  private _ttftMs: number | null = null;
  private _provider: string | null = null;
  private _model: string | null = null;
  private _inputTokens: number | null = null;
  private _outputTokens: number | null = null;
  private _totalTokens: number | null = null;
  private _costUsd: number | null = null;
  private _inputPreview: string | null = null;
  private _outputPreview: string | null = null;
  private _input: unknown = null;
  private _output: unknown = null;
  private _status: SpanStatus = 'running';
  private _errorType: string | null = null;
  private _errorMessage: string | null = null;
  private _metadata: Record<string, unknown> = {};
  private _events: SpanEvent[] = [];
  private _ended = false;

  constructor(trace: Trace, name: string, spanType: SpanType, parent: Span | null, metadata?: Record<string, unknown>) {
    this.trace = trace;
    this.spanId = generateId();
    this.name = name;
    this.spanType = spanType;
    this.parent = parent;
    this.parentSpanId = parent?.spanId ?? null;
    this.startTime = nowIso();
    this.startTimestamp = Date.now();
    this._metadata = metadata ?? {};
  }

  /**
   * Set the input for this span
   */
  setInput(input: unknown, preview?: string, maxPreviewLength = 500): this {
    this._input = input;
    if (preview) {
      this._inputPreview = preview.slice(0, maxPreviewLength);
    } else if (typeof input === 'string') {
      this._inputPreview = input.slice(0, maxPreviewLength);
    } else if (typeof input === 'object') {
      this._inputPreview = JSON.stringify(input).slice(0, maxPreviewLength);
    }
    return this;
  }

  /**
   * Set the output for this span
   */
  setOutput(output: unknown, preview?: string, maxPreviewLength = 500): this {
    this._output = output;
    if (preview) {
      this._outputPreview = preview.slice(0, maxPreviewLength);
    } else if (typeof output === 'string') {
      this._outputPreview = output.slice(0, maxPreviewLength);
    } else if (typeof output === 'object') {
      this._outputPreview = JSON.stringify(output).slice(0, maxPreviewLength);
    }
    return this;
  }

  /**
   * Set LLM-specific information for this span
   */
  setLlmInfo(options: {
    provider: string;
    model: string;
    inputTokens?: number;
    outputTokens?: number;
    costUsd?: number;
    ttftMs?: number;
  }): this {
    this._provider = options.provider;
    this._model = options.model;
    this._inputTokens = options.inputTokens ?? null;
    this._outputTokens = options.outputTokens ?? null;
    if (options.inputTokens != null && options.outputTokens != null) {
      this._totalTokens = options.inputTokens + options.outputTokens;
    }
    this._costUsd = options.costUsd ?? null;
    this._ttftMs = options.ttftMs ?? null;
    return this;
  }

  /**
   * Set a metadata key-value pair
   */
  setMetadata(key: string, value: unknown): this {
    this._metadata[key] = value;
    return this;
  }

  /**
   * Add an event to this span
   */
  addEvent(name: string, attributes?: Record<string, unknown>): this {
    this._events.push({
      name,
      timestamp: nowIso(),
      attributes,
    });
    return this;
  }

  /**
   * Mark this span as errored
   */
  setError(error: Error | string, errorType?: string): this {
    this._status = 'error';
    if (error instanceof Error) {
      this._errorType = errorType ?? error.name;
      this._errorMessage = error.message;
    } else {
      this._errorType = errorType ?? 'Error';
      this._errorMessage = error;
    }
    return this;
  }

  /**
   * End this span
   */
  end(status?: SpanStatus): this {
    if (this._ended) return this;

    this._ended = true;
    this._endTime = nowIso();
    this._durationMs = Date.now() - this.startTimestamp;

    if (status) {
      this._status = status;
    } else if (this._status === 'running') {
      this._status = 'success';
    }

    // Add span to trace
    this.trace._addSpan(this);

    return this;
  }

  /**
   * Convert to SpanData for serialization
   */
  toData(): SpanData {
    return {
      spanId: this.spanId,
      name: this.name,
      spanType: this.spanType,
      parentSpanId: this.parentSpanId ?? undefined,
      startTime: this.startTime,
      endTime: this._endTime ?? undefined,
      durationMs: this._durationMs ?? undefined,
      ttftMs: this._ttftMs ?? undefined,
      provider: this._provider ?? undefined,
      model: this._model ?? undefined,
      inputTokens: this._inputTokens ?? undefined,
      outputTokens: this._outputTokens ?? undefined,
      totalTokens: this._totalTokens ?? undefined,
      costUsd: this._costUsd ?? undefined,
      inputPreview: this._inputPreview ?? undefined,
      outputPreview: this._outputPreview ?? undefined,
      input: this._input ?? undefined,
      output: this._output ?? undefined,
      status: this._status,
      errorType: this._errorType ?? undefined,
      errorMessage: this._errorMessage ?? undefined,
      metadata: Object.keys(this._metadata).length > 0 ? this._metadata : undefined,
      events: this._events.length > 0 ? this._events : undefined,
    };
  }

  /**
   * Run a function within this span's context
   */
  async run<T>(fn: () => T | Promise<T>): Promise<T> {
    return spanStorage.run(this, async () => {
      try {
        const result = await fn();
        this.end();
        return result;
      } catch (error) {
        this.setError(error as Error);
        this.end();
        throw error;
      }
    });
  }
}

/**
 * A trace represents a complete request flow with multiple spans
 */
export class Trace {
  readonly tracer: Tracer;
  readonly traceId: string;
  readonly name: string | null;
  readonly startTime: string;
  readonly startTimestamp: number;

  private _endTime: string | null = null;
  private _durationMs: number | null = null;
  private _status: TraceStatus = 'running';
  private _environment: string | null;
  private _userId: string | null;
  private _sessionId: string | null;
  private _metadata: Record<string, unknown>;
  private _tags: string[];
  private _spans: SpanData[] = [];
  private _ended = false;

  constructor(tracer: Tracer, options: TraceOptions & { environment?: string }) {
    this.tracer = tracer;
    this.traceId = options.traceId ?? generateId();
    this.name = options.name ?? null;
    this.startTime = nowIso();
    this.startTimestamp = Date.now();
    this._environment = options.environment ?? null;
    this._userId = options.userId ?? null;
    this._sessionId = options.sessionId ?? null;
    this._metadata = options.metadata ?? {};
    this._tags = options.tags ?? [];
  }

  /**
   * Create a new span within this trace
   */
  span(nameOrOptions: string | SpanOptions): Span {
    const options = typeof nameOrOptions === 'string' ? { name: nameOrOptions } : nameOrOptions;
    const parent = spanStorage.getStore() ?? null;
    return new Span(this, options.name, options.spanType ?? 'function', parent, options.metadata);
  }

  /**
   * Set a metadata key-value pair
   */
  setMetadata(key: string, value: unknown): this {
    this._metadata[key] = value;
    return this;
  }

  /**
   * Add a tag to this trace
   */
  addTag(tag: string): this {
    if (!this._tags.includes(tag)) {
      this._tags.push(tag);
    }
    return this;
  }

  /**
   * Set the user ID for this trace
   */
  setUser(userId: string): this {
    this._userId = userId;
    return this;
  }

  /**
   * Set the session ID for this trace
   */
  setSession(sessionId: string): this {
    this._sessionId = sessionId;
    return this;
  }

  /**
   * Add a completed span to this trace (internal)
   */
  _addSpan(span: Span): void {
    this._spans.push(span.toData());
  }

  /**
   * End this trace and send to backend
   */
  end(status?: TraceStatus): this {
    if (this._ended) return this;

    this._ended = true;
    this._endTime = nowIso();
    this._durationMs = Date.now() - this.startTimestamp;

    if (status) {
      this._status = status;
    } else if (this._status === 'running') {
      // Determine status from spans
      const hasError = this._spans.some((s) => s.status === 'error');
      this._status = hasError ? 'error' : 'success';
    }

    // Send trace to backend
    this.tracer._sendTrace(this);

    return this;
  }

  /**
   * Convert to TraceData for serialization
   */
  toData(): TraceData {
    return {
      traceId: this.traceId,
      name: this.name ?? undefined,
      startTime: this.startTime,
      endTime: this._endTime ?? undefined,
      durationMs: this._durationMs ?? undefined,
      status: this._status,
      environment: this._environment ?? undefined,
      userId: this._userId ?? undefined,
      sessionId: this._sessionId ?? undefined,
      metadata: Object.keys(this._metadata).length > 0 ? this._metadata : undefined,
      tags: this._tags.length > 0 ? this._tags : undefined,
      sdkName: SDK_NAME,
      sdkVersion: SDK_VERSION,
      spans: this._spans,
    };
  }

  /**
   * Run a function within this trace's context
   */
  async run<T>(fn: () => T | Promise<T>): Promise<T> {
    return traceStorage.run(this, async () => {
      try {
        const result = await fn();
        this.end();
        return result;
      } catch (error) {
        this._status = 'error';
        this.end();
        throw error;
      }
    });
  }
}

/**
 * Tracer for creating and managing traces
 */
export class Tracer {
  private client: { _sendTraces: (orgId: string, traces: TraceData[]) => Promise<IngestResult> };
  private organizationId: string;
  private environment: string | null;
  private defaultMetadata: Record<string, unknown>;
  private pendingTraces: TraceData[] = [];

  constructor(
    client: { _sendTraces: (orgId: string, traces: TraceData[]) => Promise<IngestResult> },
    config: TracerConfig
  ) {
    this.client = client;
    this.organizationId = config.organizationId;
    this.environment = config.environment ?? null;
    this.defaultMetadata = config.defaultMetadata ?? {};
  }

  /**
   * Create a new trace
   */
  trace(options: TraceOptions = {}): Trace {
    const mergedMetadata = { ...this.defaultMetadata, ...(options.metadata ?? {}) };
    return new Trace(this, {
      ...options,
      metadata: mergedMetadata,
      environment: this.environment ?? undefined,
    });
  }

  /**
   * Create a span in the current trace context
   * If no trace is active, creates a new trace automatically
   */
  span(nameOrOptions: string | SpanOptions): Span {
    let trace = traceStorage.getStore();
    if (!trace) {
      const name = typeof nameOrOptions === 'string' ? nameOrOptions : nameOrOptions.name;
      trace = this.trace({ name });
      // Note: This trace won't have context set - use trace.run() for proper context
    }
    return trace.span(nameOrOptions);
  }

  /**
   * Send a completed trace to the backend (internal)
   */
  _sendTrace(trace: Trace): void {
    this.pendingTraces.push(trace.toData());
    // Flush immediately for now (could be batched later)
    this.flush().catch((err) => {
      console.error('[Diagnyx] Failed to flush trace:', err);
    });
  }

  /**
   * Flush pending traces to the backend
   */
  async flush(): Promise<IngestResult | null> {
    if (this.pendingTraces.length === 0) {
      return null;
    }

    const traces = [...this.pendingTraces];
    this.pendingTraces = [];

    return this.client._sendTraces(this.organizationId, traces);
  }

  /**
   * Get the current trace from context
   */
  getCurrentTrace(): Trace | undefined {
    return traceStorage.getStore();
  }

  /**
   * Get the current span from context
   */
  getCurrentSpan(): Span | undefined {
    return spanStorage.getStore();
  }
}

/**
 * Get the current trace from context
 */
export function getCurrentTrace(): Trace | undefined {
  return traceStorage.getStore();
}

/**
 * Get the current span from context
 */
export function getCurrentSpan(): Span | undefined {
  return spanStorage.getStore();
}
