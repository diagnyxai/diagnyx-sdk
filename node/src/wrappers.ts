import { Diagnyx } from './client';
import { LLMCallData, OpenAIUsage, AnthropicUsage, WrapperOptions } from './types';

/**
 * Wrap an OpenAI client to automatically track calls
 */
export function wrapOpenAI<T extends object>(
  client: T,
  diagnyx: Diagnyx,
  options: WrapperOptions = {}
): T {
  const wrapped = new Proxy(client, {
    get(target, prop) {
      const value = (target as Record<string | symbol, unknown>)[prop];

      if (prop === 'chat' && value && typeof value === 'object') {
        return wrapOpenAIChat(value as object, diagnyx, options);
      }

      return value;
    },
  });

  return wrapped;
}

function wrapOpenAIChat<T extends object>(chat: T, diagnyx: Diagnyx, options: WrapperOptions): T {
  return new Proxy(chat, {
    get(target, prop) {
      const value = (target as Record<string | symbol, unknown>)[prop];

      if (prop === 'completions' && value && typeof value === 'object') {
        return wrapOpenAICompletions(value as object, diagnyx, options);
      }

      return value;
    },
  });
}

function wrapOpenAICompletions<T extends object>(
  completions: T,
  diagnyx: Diagnyx,
  options: WrapperOptions
): T {
  return new Proxy(completions, {
    get(target, prop) {
      const value = (target as Record<string | symbol, unknown>)[prop];

      if (prop === 'create' && typeof value === 'function') {
        return async function (...args: unknown[]) {
          const startTime = Date.now();
          let status: 'success' | 'error' = 'success';
          let errorCode: string | undefined;
          let errorMessage: string | undefined;

          try {
            const result = await (value as (...args: unknown[]) => Promise<unknown>).apply(
              target,
              args
            );
            const latencyMs = Date.now() - startTime;

            const requestArgs = args[0] as { model?: string } | undefined;
            const model = requestArgs?.model || 'unknown';
            const usage = (result as { usage?: OpenAIUsage }).usage;

            if (usage) {
              const callData: LLMCallData = {
                provider: 'openai',
                model,
                inputTokens: usage.prompt_tokens,
                outputTokens: usage.completion_tokens,
                latencyMs,
                status,
                endpoint: '/v1/chat/completions',
                ...options,
              };

              diagnyx.trackCall(callData).catch(console.error);
            }

            return result;
          } catch (error) {
            status = 'error';
            errorMessage = (error as Error).message;
            errorCode = (error as { code?: string }).code;

            const latencyMs = Date.now() - startTime;
            const requestArgs = args[0] as { model?: string } | undefined;
            const model = requestArgs?.model || 'unknown';

            const callData: LLMCallData = {
              provider: 'openai',
              model,
              inputTokens: 0,
              outputTokens: 0,
              latencyMs,
              status,
              errorCode,
              errorMessage,
              endpoint: '/v1/chat/completions',
              ...options,
            };

            diagnyx.trackCall(callData).catch(console.error);

            throw error;
          }
        };
      }

      return value;
    },
  });
}

/**
 * Wrap an Anthropic client to automatically track calls
 */
export function wrapAnthropic<T extends object>(
  client: T,
  diagnyx: Diagnyx,
  options: WrapperOptions = {}
): T {
  const wrapped = new Proxy(client, {
    get(target, prop) {
      const value = (target as Record<string | symbol, unknown>)[prop];

      if (prop === 'messages' && value && typeof value === 'object') {
        return wrapAnthropicMessages(value as object, diagnyx, options);
      }

      return value;
    },
  });

  return wrapped;
}

function wrapAnthropicMessages<T extends object>(
  messages: T,
  diagnyx: Diagnyx,
  options: WrapperOptions
): T {
  return new Proxy(messages, {
    get(target, prop) {
      const value = (target as Record<string | symbol, unknown>)[prop];

      if (prop === 'create' && typeof value === 'function') {
        return async function (...args: unknown[]) {
          const startTime = Date.now();
          let status: 'success' | 'error' = 'success';
          let errorCode: string | undefined;
          let errorMessage: string | undefined;

          try {
            const result = await (value as (...args: unknown[]) => Promise<unknown>).apply(
              target,
              args
            );
            const latencyMs = Date.now() - startTime;

            const requestArgs = args[0] as { model?: string } | undefined;
            const model = requestArgs?.model || 'unknown';
            const usage = (result as { usage?: AnthropicUsage }).usage;

            if (usage) {
              const callData: LLMCallData = {
                provider: 'anthropic',
                model,
                inputTokens: usage.input_tokens,
                outputTokens: usage.output_tokens,
                latencyMs,
                status,
                endpoint: '/v1/messages',
                ...options,
              };

              diagnyx.trackCall(callData).catch(console.error);
            }

            return result;
          } catch (error) {
            status = 'error';
            errorMessage = (error as Error).message;
            errorCode = (error as { code?: string }).code;

            const latencyMs = Date.now() - startTime;
            const requestArgs = args[0] as { model?: string } | undefined;
            const model = requestArgs?.model || 'unknown';

            const callData: LLMCallData = {
              provider: 'anthropic',
              model,
              inputTokens: 0,
              outputTokens: 0,
              latencyMs,
              status,
              errorCode,
              errorMessage,
              endpoint: '/v1/messages',
              ...options,
            };

            diagnyx.trackCall(callData).catch(console.error);

            throw error;
          }
        };
      }

      return value;
    },
  });
}

/**
 * Helper to manually track a call with timing
 */
export async function trackWithTiming<T>(
  diagnyx: Diagnyx,
  provider: LLMCallData['provider'],
  model: string,
  fn: () => Promise<T>,
  getUsage: (result: T) => { inputTokens: number; outputTokens: number },
  options: WrapperOptions = {}
): Promise<T> {
  const startTime = Date.now();

  try {
    const result = await fn();
    const latencyMs = Date.now() - startTime;
    const usage = getUsage(result);

    await diagnyx.trackCall({
      provider,
      model,
      inputTokens: usage.inputTokens,
      outputTokens: usage.outputTokens,
      latencyMs,
      status: 'success',
      ...options,
    });

    return result;
  } catch (error) {
    const latencyMs = Date.now() - startTime;

    await diagnyx.trackCall({
      provider,
      model,
      inputTokens: 0,
      outputTokens: 0,
      latencyMs,
      status: 'error',
      errorMessage: (error as Error).message,
      ...options,
    });

    throw error;
  }
}
