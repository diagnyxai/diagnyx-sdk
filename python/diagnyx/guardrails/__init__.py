"""Streaming guardrails for LLM responses."""

from .client import StreamingGuardrails
from .types import (
    EnforcementLevel,
    GuardrailSession,
    GuardrailViolation,
    SessionCompleteEvent,
    SessionStartedEvent,
    StreamingEvent,
    StreamingEventType,
    TokenAllowedEvent,
    ViolationDetectedEvent,
)
from .wrappers import stream_with_guardrails, wrap_streaming_response
from .streaming import (
    StreamingGuardrail,
    StreamingGuardrailConfig,
    StreamingSession,
    GuardrailViolationError,
    stream_with_guardrails as stream_with_guardrail,
)

__all__ = [
    # Client (legacy)
    "StreamingGuardrails",
    # Streaming Guardrail (new)
    "StreamingGuardrail",
    "StreamingGuardrailConfig",
    "StreamingSession",
    "GuardrailViolationError",
    "stream_with_guardrail",
    # Types
    "StreamingEvent",
    "StreamingEventType",
    "EnforcementLevel",
    "SessionStartedEvent",
    "TokenAllowedEvent",
    "ViolationDetectedEvent",
    "SessionCompleteEvent",
    "GuardrailViolation",
    "GuardrailSession",
    # Wrappers
    "stream_with_guardrails",
    "wrap_streaming_response",
]
