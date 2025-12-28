/**
 * Type definitions for Diagnyx tracing
 */

export type SpanType =
  | 'llm'
  | 'embedding'
  | 'retrieval'
  | 'tool'
  | 'agent'
  | 'chain'
  | 'function'
  | 'custom';

export type SpanStatus = 'running' | 'success' | 'error' | 'timeout';

export type TraceStatus = 'running' | 'success' | 'error' | 'timeout';

export interface SpanEvent {
  name: string;
  timestamp?: string;
  attributes?: Record<string, unknown>;
}

export interface SpanData {
  spanId: string;
  name: string;
  spanType: SpanType;
  startTime: string;
  parentSpanId?: string;
  endTime?: string;
  durationMs?: number;
  ttftMs?: number;
  provider?: string;
  model?: string;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  costUsd?: number;
  inputPreview?: string;
  outputPreview?: string;
  input?: unknown;
  output?: unknown;
  status: SpanStatus;
  errorType?: string;
  errorMessage?: string;
  metadata?: Record<string, unknown>;
  events?: SpanEvent[];
}

export interface TraceData {
  traceId: string;
  name?: string;
  startTime?: string;
  endTime?: string;
  durationMs?: number;
  status: TraceStatus;
  environment?: string;
  userId?: string;
  sessionId?: string;
  metadata?: Record<string, unknown>;
  tags?: string[];
  sdkName: string;
  sdkVersion: string;
  spans: SpanData[];
}

export interface IngestResult {
  accepted: number;
  failed: number;
  errors?: string[];
}

export interface TracerConfig {
  organizationId: string;
  environment?: string;
  defaultMetadata?: Record<string, unknown>;
}

export interface SpanOptions {
  name: string;
  spanType?: SpanType;
  metadata?: Record<string, unknown>;
}

export interface TraceOptions {
  name?: string;
  traceId?: string;
  userId?: string;
  sessionId?: string;
  metadata?: Record<string, unknown>;
  tags?: string[];
}
