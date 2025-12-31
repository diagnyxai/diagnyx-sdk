/**
 * Type definitions for streaming guardrails
 */

export type StreamingEventType =
  | 'session_started'
  | 'token_allowed'
  | 'violation_detected'
  | 'early_termination'
  | 'session_complete'
  | 'error';

export type EnforcementLevel = 'advisory' | 'warning' | 'blocking';

export interface StreamingEvent {
  type: StreamingEventType;
  sessionId: string;
  timestamp: number;
}

export interface SessionStartedEvent extends StreamingEvent {
  type: 'session_started';
  activePolicies: string[];
}

export interface TokenAllowedEvent extends StreamingEvent {
  type: 'token_allowed';
  tokenIndex: number;
  accumulatedLength: number;
}

export interface GuardrailViolation {
  policyId: string;
  policyName: string;
  policyType: string;
  violationType: string;
  message: string;
  severity: string;
  enforcementLevel: EnforcementLevel;
  details?: Record<string, unknown>;
}

export interface ViolationDetectedEvent extends StreamingEvent {
  type: 'violation_detected';
  policyId: string;
  policyName: string;
  policyType: string;
  violationType: string;
  message: string;
  severity: string;
  enforcementLevel: string;
  details?: Record<string, unknown>;
}

export interface EarlyTerminationEvent extends StreamingEvent {
  type: 'early_termination';
  reason: string;
  blockingViolation?: ViolationDetectedEvent;
  tokensProcessed: number;
}

export interface SessionCompleteEvent extends StreamingEvent {
  type: 'session_complete';
  totalTokens: number;
  totalViolations: number;
  allowed: boolean;
  latencyMs: number;
}

export interface ErrorEvent extends StreamingEvent {
  type: 'error';
  error: string;
  code?: string;
}

export type StreamingEvaluationEvent =
  | SessionStartedEvent
  | TokenAllowedEvent
  | ViolationDetectedEvent
  | EarlyTerminationEvent
  | SessionCompleteEvent
  | ErrorEvent;

export interface GuardrailSession {
  sessionId: string;
  organizationId: string;
  projectId: string;
  activePolicies: string[];
  tokensProcessed: number;
  violations: GuardrailViolation[];
  terminated: boolean;
  terminationReason?: string;
  allowed: boolean;
}

export interface StreamingGuardrailsConfig {
  apiKey: string;
  organizationId: string;
  projectId: string;
  baseUrl?: string;
  timeout?: number;
  evaluateEveryNTokens?: number;
  enableEarlyTermination?: boolean;
  debug?: boolean;
}

export interface StartSessionOptions {
  sessionId?: string;
  input?: string;
}

export interface EvaluateTokenOptions {
  tokenIndex?: number;
  isLast?: boolean;
}

/**
 * Parse a raw event object into a typed event
 */
export function parseEvent(data: Record<string, unknown>): StreamingEvaluationEvent {
  const type = data.type as StreamingEventType;
  const sessionId = (data.sessionId ?? data.session_id ?? '') as string;
  const timestamp = (data.timestamp ?? 0) as number;

  const base = { type, sessionId, timestamp };

  switch (type) {
    case 'session_started':
      return {
        ...base,
        type: 'session_started',
        activePolicies: (data.activePolicies ?? data.active_policies ?? []) as string[],
      };

    case 'token_allowed':
      return {
        ...base,
        type: 'token_allowed',
        tokenIndex: (data.tokenIndex ?? data.token_index ?? 0) as number,
        accumulatedLength: (data.accumulatedLength ?? data.accumulated_length ?? 0) as number,
      };

    case 'violation_detected':
      return {
        ...base,
        type: 'violation_detected',
        policyId: (data.policyId ?? data.policy_id ?? '') as string,
        policyName: (data.policyName ?? data.policy_name ?? '') as string,
        policyType: (data.policyType ?? data.policy_type ?? '') as string,
        violationType: (data.violationType ?? data.violation_type ?? '') as string,
        message: (data.message ?? '') as string,
        severity: (data.severity ?? '') as string,
        enforcementLevel: (data.enforcementLevel ?? data.enforcement_level ?? '') as string,
        details: data.details as Record<string, unknown> | undefined,
      };

    case 'early_termination': {
      const blockingData = (data.blockingViolation ?? data.blocking_violation) as
        | Record<string, unknown>
        | undefined;
      let blockingViolation: ViolationDetectedEvent | undefined;

      if (blockingData) {
        blockingViolation = {
          type: 'violation_detected',
          sessionId,
          timestamp: (blockingData.timestamp ?? timestamp) as number,
          policyId: (blockingData.policyId ?? blockingData.policy_id ?? '') as string,
          policyName: (blockingData.policyName ?? blockingData.policy_name ?? '') as string,
          policyType: (blockingData.policyType ?? blockingData.policy_type ?? '') as string,
          violationType: (blockingData.violationType ?? blockingData.violation_type ?? '') as string,
          message: (blockingData.message ?? '') as string,
          severity: (blockingData.severity ?? '') as string,
          enforcementLevel: (blockingData.enforcementLevel ??
            blockingData.enforcement_level ??
            '') as string,
          details: blockingData.details as Record<string, unknown> | undefined,
        };
      }

      return {
        ...base,
        type: 'early_termination',
        reason: (data.reason ?? '') as string,
        blockingViolation,
        tokensProcessed: (data.tokensProcessed ?? data.tokens_processed ?? 0) as number,
      };
    }

    case 'session_complete':
      return {
        ...base,
        type: 'session_complete',
        totalTokens: (data.totalTokens ?? data.total_tokens ?? 0) as number,
        totalViolations: (data.totalViolations ?? data.total_violations ?? 0) as number,
        allowed: (data.allowed ?? true) as boolean,
        latencyMs: (data.latencyMs ?? data.latency_ms ?? 0) as number,
      };

    case 'error':
      return {
        ...base,
        type: 'error',
        error: (data.error ?? 'Unknown error') as string,
        code: data.code as string | undefined,
      };

    default:
      return {
        ...base,
        type: 'error',
        error: 'Unknown event type',
      } as ErrorEvent;
  }
}

/**
 * Convert ViolationDetectedEvent to GuardrailViolation
 */
export function toViolation(event: ViolationDetectedEvent): GuardrailViolation {
  return {
    policyId: event.policyId,
    policyName: event.policyName,
    policyType: event.policyType,
    violationType: event.violationType,
    message: event.message,
    severity: event.severity,
    enforcementLevel: (event.enforcementLevel || 'advisory') as EnforcementLevel,
    details: event.details,
  };
}
