"""Diagnyx SDK for LLM tracking, tracing, and monitoring."""

from .callbacks import DiagnyxCallbackHandler
from .client import Diagnyx
from .prompts import (
    PromptsClient,
    PromptTemplate,
    PromptVariable,
    PromptVersion,
    RenderedPrompt,
)
from .tracing import Span, Trace, Tracer, trace
from .tracing_types import (
    IngestResult,
    SpanData,
    SpanEvent,
    SpanStatus,
    SpanType,
    TraceData,
    TraceStatus,
)
from .types import CallStatus, LLMCallData, LLMProvider
from .wrappers import track_with_timing, wrap_anthropic, wrap_openai

__version__ = "0.1.0"
__all__ = [
    # Client
    "Diagnyx",
    # Callbacks
    "DiagnyxCallbackHandler",
    # Tracing
    "Tracer",
    "Trace",
    "Span",
    "trace",
    # Tracing types
    "TraceData",
    "SpanData",
    "SpanEvent",
    "SpanType",
    "SpanStatus",
    "TraceStatus",
    "IngestResult",
    # Prompts
    "PromptsClient",
    "PromptTemplate",
    "PromptVersion",
    "PromptVariable",
    "RenderedPrompt",
    # Cost tracking types
    "LLMCallData",
    "CallStatus",
    "LLMProvider",
    # Wrappers
    "wrap_openai",
    "wrap_anthropic",
    "track_with_timing",
]
