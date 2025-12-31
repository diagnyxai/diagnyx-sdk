/**
 * Wrapper functions for streaming guardrails
 */

import { GuardrailViolationError, StreamingGuardrails } from './client';
import {
  EarlyTerminationEvent,
  GuardrailSession,
  GuardrailViolation,
  toViolation,
  ViolationDetectedEvent,
} from './types';

export interface StreamGuardrailsOptions<T> {
  /** StreamingGuardrails client instance */
  guardrails: StreamingGuardrails;
  /** Function to extract token content from stream items */
  getTokenContent?: (item: T) => string;
  /** Function to check if item is the last token */
  getIsLast?: (item: T) => boolean;
  /** Optional input text to pre-evaluate */
  inputText?: string;
  /** Callback for violations */
  onViolation?: (violation: GuardrailViolation, session: GuardrailSession) => void;
  /** Callback for early termination */
  onTermination?: (event: EarlyTerminationEvent, session: GuardrailSession) => void;
  /** Raise GuardrailViolationError on blocking violations. Default: true */
  raiseOnBlocking?: boolean;
}

/**
 * Default token content extractor for OpenAI streaming format
 */
function defaultGetTokenContent<T>(item: T): string {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const content = (item as any)?.choices?.[0]?.delta?.content;
    return content || '';
  } catch {
    return '';
  }
}

/**
 * Default isLast checker for OpenAI streaming format
 */
function defaultGetIsLast<T>(item: T): boolean {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const finishReason = (item as any)?.choices?.[0]?.finish_reason;
    return finishReason !== null && finishReason !== undefined;
  } catch {
    return false;
  }
}

/**
 * Wrap an async iterable stream with guardrail validation.
 *
 * @example
 * ```typescript
 * import { OpenAI } from 'openai';
 * import { StreamingGuardrails, streamWithGuardrails } from '@diagnyx/node';
 *
 * const openai = new OpenAI();
 * const guardrails = new StreamingGuardrails({
 *   apiKey: 'dx_...',
 *   organizationId: 'org_123',
 *   projectId: 'proj_456',
 * });
 *
 * const stream = await openai.chat.completions.create({
 *   model: 'gpt-4',
 *   messages: [{ role: 'user', content: 'Hello!' }],
 *   stream: true,
 * });
 *
 * for await (const chunk of streamWithGuardrails(stream, { guardrails })) {
 *   process.stdout.write(chunk.choices[0]?.delta?.content || '');
 * }
 * ```
 */
export async function* streamWithGuardrails<T>(
  stream: AsyncIterable<T>,
  options: StreamGuardrailsOptions<T>,
): AsyncGenerator<T> {
  const {
    guardrails,
    getTokenContent = defaultGetTokenContent,
    getIsLast = defaultGetIsLast,
    inputText,
    onViolation,
    onTermination,
    raiseOnBlocking = true,
  } = options;

  // Start session
  const sessionEvent = await guardrails.startSession({ input: inputText });
  const sessionId = sessionEvent.sessionId;
  const session = guardrails.getSession(sessionId);

  if (!session) {
    throw new Error('Failed to get session after starting');
  }

  let tokenIndex = 0;

  try {
    for await (const item of stream) {
      const tokenContent = getTokenContent(item);
      const isLast = getIsLast(item);

      if (tokenContent) {
        // Evaluate token
        for await (const event of guardrails.evaluateToken(sessionId, tokenContent, {
          tokenIndex,
          isLast,
        })) {
          if (event.type === 'violation_detected') {
            const violation = toViolation(event as ViolationDetectedEvent);
            onViolation?.(violation, session);
          } else if (event.type === 'early_termination') {
            const termEvent = event as EarlyTerminationEvent;
            onTermination?.(termEvent, session);
            if (raiseOnBlocking && termEvent.blockingViolation) {
              throw new GuardrailViolationError(toViolation(termEvent.blockingViolation), session);
            }
            return;
          }
        }
        tokenIndex++;
      }

      yield item;

      if (isLast) {
        break;
      }
    }
  } catch (e) {
    if (e instanceof GuardrailViolationError) throw e;
    throw e;
  } finally {
    // Complete session if not already terminated
    if (session && !session.terminated) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      for await (const _ of guardrails.completeSession(sessionId)) {
        // Consume all events
      }
    }
  }
}

/**
 * Create a wrapper function that applies guardrails to streaming responses.
 *
 * @example
 * ```typescript
 * import { StreamingGuardrails, wrapStreamingResponse } from '@diagnyx/node';
 *
 * const guardrails = new StreamingGuardrails({
 *   apiKey: 'dx_...',
 *   organizationId: 'org_123',
 *   projectId: 'proj_456',
 * });
 *
 * const getCompletion = wrapStreamingResponse(guardrails, async (prompt: string) => {
 *   return openai.chat.completions.create({
 *     model: 'gpt-4',
 *     messages: [{ role: 'user', content: prompt }],
 *     stream: true,
 *   });
 * });
 *
 * for await (const chunk of await getCompletion('Hello!')) {
 *   process.stdout.write(chunk.choices[0]?.delta?.content || '');
 * }
 * ```
 */
export function wrapStreamingResponse<T, Args extends unknown[]>(
  guardrails: StreamingGuardrails,
  fn: (...args: Args) => Promise<AsyncIterable<T>>,
  options: Omit<StreamGuardrailsOptions<T>, 'guardrails'> = {},
): (...args: Args) => Promise<AsyncGenerator<T>> {
  return async (...args: Args): Promise<AsyncGenerator<T>> => {
    const stream = await fn(...args);
    return streamWithGuardrails(stream, { ...options, guardrails });
  };
}
