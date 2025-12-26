import type { Diagnyx } from '../client';
import type { WrapperOptions } from '../types';

/**
 * Type definitions for OpenAI SDK
 * We use minimal types to avoid requiring openai as a dependency
 */
interface OpenAIUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens?: number;
}

interface OpenAIChatCompletionMessage {
  role: string;
  content?: string | null;
}

interface OpenAIChatCompletionChoice {
  index: number;
  message: OpenAIChatCompletionMessage;
  finish_reason?: string;
}

interface OpenAIChatCompletion {
  id: string;
  model: string;
  usage?: OpenAIUsage;
  choices?: OpenAIChatCompletionChoice[];
}

interface OpenAIChatCompletionChunkDelta {
  role?: string;
  content?: string | null;
}

interface OpenAIChatCompletionChunkChoice {
  index: number;
  delta: OpenAIChatCompletionChunkDelta;
  finish_reason?: string | null;
}

interface OpenAIChatCompletionChunk {
  id: string;
  model: string;
  usage?: OpenAIUsage;
  choices?: OpenAIChatCompletionChunkChoice[];
}

interface OpenAIEmbeddingResponse {
  model: string;
  usage: {
    prompt_tokens: number;
    total_tokens: number;
  };
}

interface OpenAIMessageInput {
  role: string;
  content?: string | { type: string; text?: string; [key: string]: unknown }[] | null;
  [key: string]: unknown;
}

type CreateChatCompletionFn = (options: {
  model: string;
  stream?: boolean;
  messages?: OpenAIMessageInput[];
  [key: string]: unknown;
}) => Promise<OpenAIChatCompletion | AsyncIterable<OpenAIChatCompletionChunk>>;

/**
 * Extract prompt content from OpenAI messages array
 */
function extractPromptContent(messages?: OpenAIMessageInput[], maxLength?: number): string | undefined {
  if (!messages || messages.length === 0) return undefined;

  const content = messages
    .map((m) => {
      let msgContent: string;
      if (typeof m.content === 'string') {
        msgContent = m.content;
      } else if (Array.isArray(m.content)) {
        msgContent = m.content
          .map((c) => (c.type === 'text' && c.text ? c.text : JSON.stringify(c)))
          .join('');
      } else {
        msgContent = '';
      }
      return `[${m.role}]: ${msgContent}`;
    })
    .join('\n');

  const max = maxLength || 10000;
  if (content.length > max) {
    return content.slice(0, max) + '... [truncated]';
  }
  return content;
}

/**
 * Extract response content from OpenAI completion
 */
function extractResponseContent(
  choices?: OpenAIChatCompletionChoice[],
  maxLength?: number
): string | undefined {
  if (!choices || choices.length === 0) return undefined;

  const content = choices[0]?.message?.content || '';
  const max = maxLength || 10000;
  if (content.length > max) {
    return content.slice(0, max) + '... [truncated]';
  }
  return content;
}

type CreateEmbeddingFn = (options: {
  model: string;
  [key: string]: unknown;
}) => Promise<OpenAIEmbeddingResponse>;

interface OpenAIClient {
  chat: {
    completions: {
      create: CreateChatCompletionFn;
    };
  };
  embeddings: {
    create: CreateEmbeddingFn;
  };
}

/**
 * Wrap an OpenAI client to automatically track LLM calls
 *
 * @example
 * ```typescript
 * import OpenAI from 'openai';
 * import { Diagnyx, wrapOpenAI } from '@diagnyx/node';
 *
 * const diagnyx = new Diagnyx({ apiKey: 'dx_live_xxx' });
 * const openai = wrapOpenAI(new OpenAI(), diagnyx);
 *
 * // All calls are now automatically tracked
 * const response = await openai.chat.completions.create({
 *   model: 'gpt-4',
 *   messages: [{ role: 'user', content: 'Hello!' }],
 * });
 * ```
 */
export function wrapOpenAI<T extends OpenAIClient>(
  client: T,
  diagnyx: Diagnyx,
  options?: WrapperOptions
): T {
  const wrappedClient = new Proxy(client, {
    get(target, prop, receiver) {
      if (prop === 'chat') {
        return wrapChat(target.chat, diagnyx, options);
      }
      if (prop === 'embeddings') {
        return wrapEmbeddings(target.embeddings, diagnyx, options);
      }
      return Reflect.get(target, prop, receiver);
    },
  });

  return wrappedClient;
}

/**
 * Wrap the chat completions API
 */
function wrapChat(
  chat: OpenAIClient['chat'],
  diagnyx: Diagnyx,
  options?: WrapperOptions
): OpenAIClient['chat'] {
  return {
    completions: {
      create: async function (createOptions: Parameters<CreateChatCompletionFn>[0]) {
        const startTime = Date.now();
        let _ttft: number | undefined;

        try {
          const result = await chat.completions.create(createOptions);

          // Handle streaming response
          if (
            createOptions.stream &&
            result &&
            typeof result === 'object' &&
            Symbol.asyncIterator in result
          ) {
            return wrapStream(
              result as AsyncIterable<OpenAIChatCompletionChunk>,
              diagnyx,
              createOptions.model,
              startTime,
              options,
              createOptions.messages
            );
          }

          // Non-streaming response
          const response = result as OpenAIChatCompletion;
          const latencyMs = Date.now() - startTime;

          // Extract content if enabled
          let fullPrompt: string | undefined;
          let fullResponse: string | undefined;
          if (diagnyx.config.captureFullContent) {
            fullPrompt = extractPromptContent(
              createOptions.messages,
              diagnyx.config.contentMaxLength
            );
            fullResponse = extractResponseContent(
              response.choices,
              diagnyx.config.contentMaxLength
            );
          }

          void diagnyx.trackCall({
            provider: 'openai',
            model: response.model || createOptions.model,
            endpoint: 'chat.completions',
            inputTokens: response.usage?.prompt_tokens ?? 0,
            outputTokens: response.usage?.completion_tokens ?? 0,
            latencyMs,
            status: 'success',
            projectId: options?.projectId,
            environment: options?.environment,
            userIdentifier: options?.userIdentifier,
            fullPrompt,
            fullResponse,
          });

          return response;
        } catch (error) {
          const latencyMs = Date.now() - startTime;

          void diagnyx.trackCall({
            provider: 'openai',
            model: createOptions.model,
            endpoint: 'chat.completions',
            inputTokens: 0,
            outputTokens: 0,
            latencyMs,
            status: 'error',
            errorCode: (error as { code?: string }).code,
            errorMessage: (error as Error).message,
            projectId: options?.projectId,
            environment: options?.environment,
            userIdentifier: options?.userIdentifier,
          });

          throw error;
        }
      },
    },
  };
}

/**
 * Wrap the embeddings API
 */
function wrapEmbeddings(
  embeddings: OpenAIClient['embeddings'],
  diagnyx: Diagnyx,
  options?: WrapperOptions
): OpenAIClient['embeddings'] {
  return {
    create: async function (createOptions: Parameters<CreateEmbeddingFn>[0]) {
      const startTime = Date.now();

      try {
        const result = await embeddings.create(createOptions);
        const latencyMs = Date.now() - startTime;

        void diagnyx.trackCall({
          provider: 'openai',
          model: result.model || createOptions.model,
          endpoint: 'embeddings',
          inputTokens: result.usage?.prompt_tokens ?? 0,
          outputTokens: 0,
          latencyMs,
          status: 'success',
          projectId: options?.projectId,
          environment: options?.environment,
          userIdentifier: options?.userIdentifier,
        });

        return result;
      } catch (error) {
        const latencyMs = Date.now() - startTime;

        void diagnyx.trackCall({
          provider: 'openai',
          model: createOptions.model,
          endpoint: 'embeddings',
          inputTokens: 0,
          outputTokens: 0,
          latencyMs,
          status: 'error',
          errorCode: (error as { code?: string }).code,
          errorMessage: (error as Error).message,
          projectId: options?.projectId,
          environment: options?.environment,
          userIdentifier: options?.userIdentifier,
        });

        throw error;
      }
    },
  };
}

/**
 * Wrap a streaming response to track metrics
 */
async function* wrapStream(
  stream: AsyncIterable<OpenAIChatCompletionChunk>,
  diagnyx: Diagnyx,
  model: string,
  startTime: number,
  options?: WrapperOptions,
  messages?: OpenAIMessageInput[]
): AsyncGenerator<OpenAIChatCompletionChunk, void, unknown> {
  let firstChunk = true;
  let ttft: number | undefined;
  let usage: OpenAIUsage | undefined;
  let responseModel = model;
  let accumulatedContent = '';

  try {
    for await (const chunk of stream) {
      if (firstChunk) {
        ttft = Date.now() - startTime;
        firstChunk = false;
      }

      // Last chunk often contains usage info
      if (chunk.usage) {
        usage = chunk.usage;
      }

      if (chunk.model) {
        responseModel = chunk.model;
      }

      // Accumulate response content from streaming chunks
      if (diagnyx.config.captureFullContent && chunk.choices?.[0]?.delta?.content) {
        accumulatedContent += chunk.choices[0].delta.content;
      }

      yield chunk;
    }

    const latencyMs = Date.now() - startTime;

    // Extract content if enabled
    let fullPrompt: string | undefined;
    let fullResponse: string | undefined;
    if (diagnyx.config.captureFullContent) {
      fullPrompt = extractPromptContent(messages, diagnyx.config.contentMaxLength);
      const maxLen = diagnyx.config.contentMaxLength || 10000;
      fullResponse =
        accumulatedContent.length > maxLen
          ? accumulatedContent.slice(0, maxLen) + '... [truncated]'
          : accumulatedContent || undefined;
    }

    void diagnyx.trackCall({
      provider: 'openai',
      model: responseModel,
      endpoint: 'chat.completions',
      inputTokens: usage?.prompt_tokens ?? 0,
      outputTokens: usage?.completion_tokens ?? 0,
      latencyMs,
      ttftMs: ttft,
      status: 'success',
      projectId: options?.projectId,
      environment: options?.environment,
      userIdentifier: options?.userIdentifier,
      fullPrompt,
      fullResponse,
    });
  } catch (error) {
    const latencyMs = Date.now() - startTime;

    void diagnyx.trackCall({
      provider: 'openai',
      model: responseModel,
      endpoint: 'chat.completions',
      inputTokens: 0,
      outputTokens: 0,
      latencyMs,
      ttftMs: ttft,
      status: 'error',
      errorCode: (error as { code?: string }).code,
      errorMessage: (error as Error).message,
      projectId: options?.projectId,
      environment: options?.environment,
      userIdentifier: options?.userIdentifier,
    });

    throw error;
  }
}
