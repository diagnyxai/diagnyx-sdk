/**
 * Streaming guardrails for LLM responses
 */

export { GuardrailViolationError, StreamingGuardrails } from './client';
export { streamWithGuardrails, wrapStreamingResponse } from './wrappers';
export type {
  EarlyTerminationEvent,
  EnforcementLevel,
  ErrorEvent,
  EvaluateTokenOptions,
  GuardrailSession,
  GuardrailViolation,
  SessionCompleteEvent,
  SessionStartedEvent,
  StartSessionOptions,
  StreamingEvaluationEvent,
  StreamingEventType,
  StreamingGuardrailsConfig,
  TokenAllowedEvent,
  ViolationDetectedEvent,
} from './types';
export type { StreamGuardrailsOptions, StreamGuardrailsOptions as StreamWithGuardrailsOptions } from './wrappers';

// New streaming guardrail (token-by-token)
export {
  StreamingGuardrail,
  GuardrailViolationError as StreamingViolationError,
  streamWithGuardrails as streamWithGuardrail,
} from './streaming';
export type {
  StreamingGuardrailConfig,
  StreamingSession,
  EvaluateOptions,
} from './streaming';
