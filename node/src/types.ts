export type LLMProvider =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'cohere'
  | 'mistral'
  | 'groq'
  | 'together'
  | 'fireworks'
  | 'custom';

export type CallStatus = 'success' | 'error' | 'timeout' | 'rate_limited';

export interface DiagnyxConfig {
  apiKey: string;
  baseUrl?: string;
  batchSize?: number;
  flushIntervalMs?: number;
  maxRetries?: number;
  debug?: boolean;
}

export interface LLMCallData {
  provider: LLMProvider;
  model: string;
  inputTokens: number;
  outputTokens: number;
  latencyMs?: number;
  ttftMs?: number;
  status: CallStatus;
  errorCode?: string;
  errorMessage?: string;
  endpoint?: string;
  projectId?: string;
  environment?: string;
  traceId?: string;
  userIdentifier?: string;
  timestamp?: Date | string;
}

export interface TrackResult {
  id: string;
  costUsd: number;
  totalTokens: number;
}

export interface BatchResult {
  tracked: number;
  totalCost: number;
  totalTokens: number;
  ids: string[];
}

export interface OpenAIUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface AnthropicUsage {
  input_tokens: number;
  output_tokens: number;
}

export interface WrapperOptions {
  projectId?: string;
  environment?: string;
  userIdentifier?: string;
}
