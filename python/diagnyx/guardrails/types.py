"""Type definitions for streaming guardrails."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StreamingEventType(str, Enum):
    """Types of streaming evaluation events."""

    SESSION_STARTED = "session_started"
    TOKEN_ALLOWED = "token_allowed"
    VIOLATION_DETECTED = "violation_detected"
    EARLY_TERMINATION = "early_termination"
    SESSION_COMPLETE = "session_complete"
    ERROR = "error"


class EnforcementLevel(str, Enum):
    """Policy enforcement levels."""

    ADVISORY = "advisory"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass
class StreamingEvent:
    """Base streaming event."""

    type: StreamingEventType
    session_id: str
    timestamp: int


@dataclass
class SessionStartedEvent(StreamingEvent):
    """Event emitted when a streaming session starts."""

    active_policies: List[str] = field(default_factory=list)


@dataclass
class TokenAllowedEvent(StreamingEvent):
    """Event emitted when a token passes guardrail checks."""

    token_index: int = 0
    accumulated_length: int = 0


@dataclass
class GuardrailViolation:
    """Details of a guardrail violation."""

    policy_id: str
    policy_name: str
    policy_type: str
    violation_type: str
    message: str
    severity: str
    enforcement_level: EnforcementLevel
    details: Optional[Dict[str, Any]] = None


@dataclass
class ViolationDetectedEvent(StreamingEvent):
    """Event emitted when a guardrail violation is detected."""

    policy_id: str = ""
    policy_name: str = ""
    policy_type: str = ""
    violation_type: str = ""
    message: str = ""
    severity: str = ""
    enforcement_level: str = ""
    details: Optional[Dict[str, Any]] = None

    def to_violation(self) -> GuardrailViolation:
        """Convert to GuardrailViolation."""
        return GuardrailViolation(
            policy_id=self.policy_id,
            policy_name=self.policy_name,
            policy_type=self.policy_type,
            violation_type=self.violation_type,
            message=self.message,
            severity=self.severity,
            enforcement_level=EnforcementLevel(self.enforcement_level)
            if self.enforcement_level
            else EnforcementLevel.ADVISORY,
            details=self.details,
        )


@dataclass
class EarlyTerminationEvent(StreamingEvent):
    """Event emitted when stream is terminated early due to blocking violation."""

    reason: str = ""
    blocking_violation: Optional[ViolationDetectedEvent] = None
    tokens_processed: int = 0


@dataclass
class SessionCompleteEvent(StreamingEvent):
    """Event emitted when a streaming session completes."""

    total_tokens: int = 0
    total_violations: int = 0
    allowed: bool = True
    latency_ms: int = 0


@dataclass
class ErrorEvent(StreamingEvent):
    """Event emitted when an error occurs."""

    error: str = ""
    code: Optional[str] = None


@dataclass
class GuardrailSession:
    """State of a streaming guardrails session."""

    session_id: str
    organization_id: str
    project_id: str
    active_policies: List[str] = field(default_factory=list)
    tokens_processed: int = 0
    violations: List[GuardrailViolation] = field(default_factory=list)
    terminated: bool = False
    termination_reason: Optional[str] = None
    allowed: bool = True


def parse_event(data: Dict[str, Any]) -> StreamingEvent:
    """Parse a raw event dictionary into the appropriate event type."""
    event_type = StreamingEventType(data.get("type", "error"))
    session_id = data.get("sessionId", data.get("session_id", ""))
    timestamp = data.get("timestamp", 0)

    base = {
        "type": event_type,
        "session_id": session_id,
        "timestamp": timestamp,
    }

    if event_type == StreamingEventType.SESSION_STARTED:
        return SessionStartedEvent(
            **base,
            active_policies=data.get("activePolicies", data.get("active_policies", [])),
        )
    elif event_type == StreamingEventType.TOKEN_ALLOWED:
        return TokenAllowedEvent(
            **base,
            token_index=data.get("tokenIndex", data.get("token_index", 0)),
            accumulated_length=data.get("accumulatedLength", data.get("accumulated_length", 0)),
        )
    elif event_type == StreamingEventType.VIOLATION_DETECTED:
        return ViolationDetectedEvent(
            **base,
            policy_id=data.get("policyId", data.get("policy_id", "")),
            policy_name=data.get("policyName", data.get("policy_name", "")),
            policy_type=data.get("policyType", data.get("policy_type", "")),
            violation_type=data.get("violationType", data.get("violation_type", "")),
            message=data.get("message", ""),
            severity=data.get("severity", ""),
            enforcement_level=data.get("enforcementLevel", data.get("enforcement_level", "")),
            details=data.get("details"),
        )
    elif event_type == StreamingEventType.EARLY_TERMINATION:
        blocking_data = data.get("blockingViolation", data.get("blocking_violation"))
        blocking_violation = None
        if blocking_data:
            blocking_violation = ViolationDetectedEvent(
                type=StreamingEventType.VIOLATION_DETECTED,
                session_id=session_id,
                timestamp=blocking_data.get("timestamp", timestamp),
                policy_id=blocking_data.get("policyId", blocking_data.get("policy_id", "")),
                policy_name=blocking_data.get("policyName", blocking_data.get("policy_name", "")),
                policy_type=blocking_data.get("policyType", blocking_data.get("policy_type", "")),
                violation_type=blocking_data.get(
                    "violationType", blocking_data.get("violation_type", "")
                ),
                message=blocking_data.get("message", ""),
                severity=blocking_data.get("severity", ""),
                enforcement_level=blocking_data.get(
                    "enforcementLevel", blocking_data.get("enforcement_level", "")
                ),
                details=blocking_data.get("details"),
            )
        return EarlyTerminationEvent(
            **base,
            reason=data.get("reason", ""),
            blocking_violation=blocking_violation,
            tokens_processed=data.get("tokensProcessed", data.get("tokens_processed", 0)),
        )
    elif event_type == StreamingEventType.SESSION_COMPLETE:
        return SessionCompleteEvent(
            **base,
            total_tokens=data.get("totalTokens", data.get("total_tokens", 0)),
            total_violations=data.get("totalViolations", data.get("total_violations", 0)),
            allowed=data.get("allowed", True),
            latency_ms=data.get("latencyMs", data.get("latency_ms", 0)),
        )
    elif event_type == StreamingEventType.ERROR:
        return ErrorEvent(
            **base,
            error=data.get("error", "Unknown error"),
            code=data.get("code"),
        )
    else:
        return StreamingEvent(**base)
