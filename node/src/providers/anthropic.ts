import type { Diagnyx } from '../client';
import type { WrapperOptions } from '../types';

/**
 * Type definitions for Anthropic SDK
 * We use minimal types to avoid requiring @anthropic-ai/sdk as a dependency
 */
interface AnthropicUsage {
  input_tokens: number;
  output_tokens: number;
}

interface AnthropicMessage {
  id: string;
  model: string;
  type: 'message';
  role: 'assistant';
  content: unknown[];
  stop_reason: string | null;
  usage: AnthropicUsage;
}

interface AnthropicMessageStreamEvent {
  type: string;
  message?: AnthropicMessage;
  index?: number;
  delta?: {
    type: string;
    text?: string;
    stop_reason?: string;
  };
  usage?: AnthropicUsage;
}

interface AnthropicStream {
  [Symbol.asyncIterator](): AsyncIterator<AnthropicMessageStreamEvent>;
  finalMessage(): Promise<AnthropicMessage>;
}

type CreateMessageFn = (options: {
  model: string;
  stream?: boolean;
  [key: string]: unknown;
}) => Promise<AnthropicMessage | AnthropicStream>;

interface AnthropicClient {
  messages: {
    create: CreateMessageFn;
  };
}

/**
 * Wrap an Anthropic client to automatically track LLM calls
 *
 * @example
 * ```typescript
 * import Anthropic from '@anthropic-ai/sdk';
 * import { Diagnyx, wrapAnthropic } from '@diagnyx/node';
 *
 * const diagnyx = new Diagnyx({ apiKey: 'dx_live_xxx' });
 * const anthropic = wrapAnthropic(new Anthropic(), diagnyx);
 *
 * // All calls are now automatically tracked
 * const message = await anthropic.messages.create({
 *   model: 'claude-3-sonnet-20240229',
 *   max_tokens: 1024,
 *   messages: [{ role: 'user', content: 'Hello!' }],
 * });
 * ```
 */
export function wrapAnthropic<T extends AnthropicClient>(
  client: T,
  diagnyx: Diagnyx,
  options?: WrapperOptions
): T {
  const wrappedClient = new Proxy(client, {
    get(target, prop, receiver) {
      if (prop === 'messages') {
        return wrapMessages(target.messages, diagnyx, options);
      }
      return Reflect.get(target, prop, receiver);
    },
  });

  return wrappedClient;
}

/**
 * Wrap the messages API
 */
function wrapMessages(
  messages: AnthropicClient['messages'],
  diagnyx: Diagnyx,
  options?: WrapperOptions
): AnthropicClient['messages'] {
  return {
    create: async function (createOptions: Parameters<CreateMessageFn>[0]) {
      const startTime = Date.now();

      try {
        const result = await messages.create(createOptions);

        // Handle streaming response
        if (createOptions.stream && isStream(result)) {
          return wrapStream(result, diagnyx, createOptions.model, startTime, options);
        }

        // Non-streaming response
        const response = result as AnthropicMessage;
        const latencyMs = Date.now() - startTime;

        void diagnyx.trackCall({
          provider: 'anthropic',
          model: response.model || createOptions.model,
          endpoint: 'messages',
          inputTokens: response.usage?.input_tokens ?? 0,
          outputTokens: response.usage?.output_tokens ?? 0,
          latencyMs,
          status: 'success',
          projectId: options?.projectId,
          environment: options?.environment,
          userIdentifier: options?.userIdentifier,
        });

        return response;
      } catch (error) {
        const latencyMs = Date.now() - startTime;

        void diagnyx.trackCall({
          provider: 'anthropic',
          model: createOptions.model,
          endpoint: 'messages',
          inputTokens: 0,
          outputTokens: 0,
          latencyMs,
          status: 'error',
          errorCode: (error as { error?: { type?: string } }).error?.type,
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
 * Check if the result is a stream
 */
function isStream(result: unknown): result is AnthropicStream {
  return result !== null && typeof result === 'object' && Symbol.asyncIterator in result;
}

/**
 * Wrap a streaming response to track metrics
 */
function wrapStream(
  stream: AnthropicStream,
  diagnyx: Diagnyx,
  model: string,
  startTime: number,
  options?: WrapperOptions
): AnthropicStream {
  let firstChunk = true;
  let ttft: number | undefined;
  let inputTokens = 0;
  let outputTokens = 0;
  let responseModel = model;
  let error: Error | undefined;

  const wrappedIterator = async function* (): AsyncGenerator<
    AnthropicMessageStreamEvent,
    void,
    unknown
  > {
    try {
      for await (const event of stream) {
        if (firstChunk) {
          ttft = Date.now() - startTime;
          firstChunk = false;
        }

        // Track token usage from events
        if (event.type === 'message_start' && event.message) {
          inputTokens = event.message.usage?.input_tokens ?? 0;
          responseModel = event.message.model || model;
        }

        if (event.type === 'message_delta' && event.usage) {
          outputTokens = event.usage.output_tokens ?? 0;
        }

        yield event;
      }
    } catch (err) {
      error = err as Error;
      throw err;
    } finally {
      const latencyMs = Date.now() - startTime;

      void diagnyx.trackCall({
        provider: 'anthropic',
        model: responseModel,
        endpoint: 'messages',
        inputTokens,
        outputTokens,
        latencyMs,
        ttftMs: ttft,
        status: error ? 'error' : 'success',
        errorCode: error ? (error as { error?: { type?: string } }).error?.type : undefined,
        errorMessage: error?.message,
        projectId: options?.projectId,
        environment: options?.environment,
        userIdentifier: options?.userIdentifier,
      });
    }
  };

  // Create a stream-like object
  const wrappedStream: AnthropicStream = {
    [Symbol.asyncIterator]: () => wrappedIterator(),
    finalMessage: async () => {
      // Consume the stream and get the final message
      let finalMessage: AnthropicMessage | undefined;

      for await (const event of wrappedIterator()) {
        if (event.type === 'message_start' && event.message) {
          finalMessage = event.message;
        }
        if (event.type === 'message_delta' && finalMessage && event.usage) {
          finalMessage.usage = {
            input_tokens: finalMessage.usage?.input_tokens ?? 0,
            output_tokens: event.usage.output_tokens ?? 0,
          };
        }
      }

      if (!finalMessage) {
        throw new Error('No message received from stream');
      }

      return finalMessage;
    },
  };

  return wrappedStream;
}
