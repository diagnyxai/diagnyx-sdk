/**
 * LangChain callback handler for Diagnyx cost tracking and tracing.
 *
 * This handler automatically tracks LLM calls made through LangChain.js,
 * capturing token usage, latency, and errors.
 *
 * @example
 * ```typescript
 * import { Diagnyx, DiagnyxCallbackHandler } from '@diagnyx/node';
 * import { ChatOpenAI } from '@langchain/openai';
 *
 * const dx = new Diagnyx({ apiKey: 'dx_...' });
 * const handler = new DiagnyxCallbackHandler(dx, { projectId: 'my-project' });
 *
 * const llm = new ChatOpenAI({ model: 'gpt-4', callbacks: [handler] });
 * const response = await llm.invoke('Hello, world!');
 * ```
 */

import type { Diagnyx } from '../client';
import type { LLMProvider, LLMCallData, CallStatus } from '../types';

/** Options for the Diagnyx callback handler */
export interface DiagnyxCallbackHandlerOptions {
  /** Project ID for categorizing calls */
  projectId?: string;
  /** Environment name (production, staging, etc.) */
  environment?: string;
  /** User identifier for tracking */
  userIdentifier?: string;
  /** Whether to capture prompt/response content (default: false) */
  captureContent?: boolean;
}

/** Model to provider mapping */
const MODEL_PROVIDER_MAP: Record<string, LLMProvider> = {
  'gpt-': 'openai',
  'o1-': 'openai',
  'claude-': 'anthropic',
  'gemini-': 'google',
  command: 'cohere',
  mistral: 'mistral',
  mixtral: 'mistral',
  llama: 'groq',
  groq: 'groq',
};

/**
 * Detect the LLM provider from the model name.
 */
function detectProvider(model: string): LLMProvider {
  const modelLower = model.toLowerCase();
  for (const [prefix, provider] of Object.entries(MODEL_PROVIDER_MAP)) {
    if (modelLower.startsWith(prefix)) {
      return provider;
    }
  }
  return 'custom';
}

/**
 * Extract token usage from LangChain response.
 */
function extractTokenUsage(response: any): { inputTokens: number; outputTokens: number } {
  let inputTokens = 0;
  let outputTokens = 0;

  // Try llmOutput first
  const llmOutput = response?.llmOutput || {};

  // OpenAI style
  const tokenUsage = llmOutput.tokenUsage || llmOutput.token_usage || {};
  if (tokenUsage.promptTokens || tokenUsage.prompt_tokens) {
    inputTokens = tokenUsage.promptTokens || tokenUsage.prompt_tokens || 0;
    outputTokens = tokenUsage.completionTokens || tokenUsage.completion_tokens || 0;
    return { inputTokens, outputTokens };
  }

  // Anthropic style
  const usage = llmOutput.usage || {};
  if (usage.inputTokens || usage.input_tokens) {
    inputTokens = usage.inputTokens || usage.input_tokens || 0;
    outputTokens = usage.outputTokens || usage.output_tokens || 0;
    return { inputTokens, outputTokens };
  }

  return { inputTokens, outputTokens };
}

/**
 * Extract model name from serialized data.
 */
function extractModelName(serialized: Record<string, any>, kwargs: Record<string, any>): string {
  // Try invocation params first
  const invocationParams = kwargs?.invocation_params || kwargs?.invocationParams || {};
  if (invocationParams.model) return invocationParams.model;
  if (invocationParams.model_name || invocationParams.modelName) {
    return invocationParams.model_name || invocationParams.modelName;
  }

  // Try serialized kwargs
  const serializedKwargs = serialized?.kwargs || {};
  if (serializedKwargs.model) return serializedKwargs.model;
  if (serializedKwargs.model_name || serializedKwargs.modelName) {
    return serializedKwargs.model_name || serializedKwargs.modelName;
  }

  // Try name from serialized
  if (serialized?.name) return serialized.name;

  return 'unknown';
}

/**
 * LangChain callback handler for Diagnyx cost tracking and tracing.
 */
export class DiagnyxCallbackHandler {
  private diagnyx: Diagnyx;
  private projectId?: string;
  private environment?: string;
  private userIdentifier?: string;
  private captureContent: boolean;
  private callStarts: Map<string, number> = new Map();
  private callMetadata: Map<string, Record<string, any>> = new Map();

  /** Handler name for LangChain */
  name = 'DiagnyxCallbackHandler';

  constructor(diagnyx: Diagnyx, options: DiagnyxCallbackHandlerOptions = {}) {
    this.diagnyx = diagnyx;
    this.projectId = options.projectId;
    this.environment = options.environment;
    this.userIdentifier = options.userIdentifier;
    this.captureContent = options.captureContent ?? false;
  }

  /**
   * Called when an LLM starts running.
   */
  handleLLMStart(
    llm: Record<string, any>,
    prompts: string[],
    runId: string,
    parentRunId?: string,
    extraParams?: Record<string, any>,
    tags?: string[],
    metadata?: Record<string, any>,
  ): void {
    this.callStarts.set(runId, Date.now());
    this.callMetadata.set(runId, {
      serialized: llm,
      prompts,
      tags,
      metadata,
      extraParams,
    });
  }

  /**
   * Called when a chat model starts running.
   */
  handleChatModelStart(
    llm: Record<string, any>,
    messages: any[][],
    runId: string,
    parentRunId?: string,
    extraParams?: Record<string, any>,
    tags?: string[],
    metadata?: Record<string, any>,
  ): void {
    this.callStarts.set(runId, Date.now());

    // Convert messages to prompts
    const prompts: string[] = messages.map((msgList) => {
      return msgList
        .map((msg) => {
          const content = msg?.content || msg?.kwargs?.content || '';
          const role = msg?.type || msg?.role || msg?._getType?.() || 'unknown';
          return `[${role}]: ${content}`;
        })
        .join('\n');
    });

    this.callMetadata.set(runId, {
      serialized: llm,
      prompts,
      messages,
      tags,
      metadata,
      extraParams,
    });
  }

  /**
   * Called when an LLM finishes running.
   */
  handleLLMEnd(output: any, runId: string, parentRunId?: string): void {
    const startTime = this.callStarts.get(runId);
    const callMetadata = this.callMetadata.get(runId) || {};

    // Clean up
    this.callStarts.delete(runId);
    this.callMetadata.delete(runId);

    const latencyMs = startTime ? Date.now() - startTime : undefined;

    // Extract model name
    const serialized = callMetadata.serialized || {};
    let model = extractModelName(serialized, callMetadata.extraParams || {});

    // Try to get from llmOutput
    const llmOutput = output?.llmOutput || {};
    if (llmOutput.modelName || llmOutput.model_name) {
      model = llmOutput.modelName || llmOutput.model_name;
    } else if (llmOutput.model) {
      model = llmOutput.model;
    }

    // Detect provider
    const provider = detectProvider(model);

    // Extract token usage
    const { inputTokens, outputTokens } = extractTokenUsage(output);

    // Extract content if enabled
    let fullPrompt: string | undefined;
    let fullResponse: string | undefined;

    if (this.captureContent || (this.diagnyx as any).config?.captureFullContent) {
      const maxLength = (this.diagnyx as any).config?.contentMaxLength || 10000;
      const prompts = callMetadata.prompts || [];
      if (prompts.length > 0) {
        const promptText = prompts.join('\n---\n');
        fullPrompt =
          promptText.length > maxLength
            ? promptText.substring(0, maxLength) + '... [truncated]'
            : promptText;
      }

      // Extract response text
      const generations = output?.generations || [];
      const responseParts: string[] = [];
      for (const genList of generations) {
        for (const gen of genList) {
          const text = gen?.text || gen?.message?.content || '';
          if (text) {
            responseParts.push(text);
          }
        }
      }
      if (responseParts.length > 0) {
        const responseText = responseParts.join('\n');
        fullResponse =
          responseText.length > maxLength
            ? responseText.substring(0, maxLength) + '... [truncated]'
            : responseText;
      }
    }

    const callData: LLMCallData = {
      provider,
      model,
      inputTokens,
      outputTokens,
      status: 'success' as CallStatus,
      latencyMs,
      projectId: this.projectId,
      environment: this.environment,
      userIdentifier: this.userIdentifier,
      timestamp: new Date(),
      fullPrompt,
      fullResponse,
    };

    this.diagnyx.trackCall(callData);
  }

  /**
   * Called when an LLM errors.
   */
  handleLLMError(error: Error, runId: string, parentRunId?: string): void {
    const startTime = this.callStarts.get(runId);
    const callMetadata = this.callMetadata.get(runId) || {};

    // Clean up
    this.callStarts.delete(runId);
    this.callMetadata.delete(runId);

    const latencyMs = startTime ? Date.now() - startTime : undefined;

    // Extract model name
    const serialized = callMetadata.serialized || {};
    const model = extractModelName(serialized, callMetadata.extraParams || {});

    // Detect provider
    const provider = detectProvider(model);

    // Extract error details
    const errorMessage = error?.message || String(error);
    const errorCode = (error as any)?.code || (error as any)?.status?.toString();

    const callData: LLMCallData = {
      provider,
      model,
      inputTokens: 0,
      outputTokens: 0,
      status: 'error' as CallStatus,
      latencyMs,
      errorCode,
      errorMessage: errorMessage.substring(0, 500),
      projectId: this.projectId,
      environment: this.environment,
      userIdentifier: this.userIdentifier,
      timestamp: new Date(),
    };

    this.diagnyx.trackCall(callData);
  }

  /**
   * Called when a chain starts. No-op for cost tracking.
   */
  handleChainStart(
    chain: Record<string, any>,
    inputs: Record<string, any>,
    runId: string,
    parentRunId?: string,
    tags?: string[],
    metadata?: Record<string, any>,
  ): void {
    // No-op for cost tracking
  }

  /**
   * Called when a chain ends. No-op for cost tracking.
   */
  handleChainEnd(outputs: Record<string, any>, runId: string, parentRunId?: string): void {
    // No-op for cost tracking
  }

  /**
   * Called when a chain errors. No-op for cost tracking.
   */
  handleChainError(error: Error, runId: string, parentRunId?: string): void {
    // No-op for cost tracking
  }

  /**
   * Called when a tool starts. No-op for cost tracking.
   */
  handleToolStart(
    tool: Record<string, any>,
    input: string,
    runId: string,
    parentRunId?: string,
    tags?: string[],
    metadata?: Record<string, any>,
  ): void {
    // No-op for cost tracking
  }

  /**
   * Called when a tool ends. No-op for cost tracking.
   */
  handleToolEnd(output: string, runId: string, parentRunId?: string): void {
    // No-op for cost tracking
  }

  /**
   * Called when a tool errors. No-op for cost tracking.
   */
  handleToolError(error: Error, runId: string, parentRunId?: string): void {
    // No-op for cost tracking
  }

  /**
   * Called when text is streamed. No-op for cost tracking.
   */
  handleText(text: string, runId: string, parentRunId?: string): void {
    // No-op for cost tracking
  }

  /**
   * Called on retry. No-op for cost tracking.
   */
  handleRetry(retry: any, runId: string, parentRunId?: string): void {
    // No-op for cost tracking
  }
}
