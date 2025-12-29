"""Type definitions for Diagnyx tracing."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SpanType(str, Enum):
    """Type of span in a trace."""

    LLM = "llm"
    EMBEDDING = "embedding"
    RETRIEVAL = "retrieval"
    TOOL = "tool"
    AGENT = "agent"
    CHAIN = "chain"
    FUNCTION = "function"
    CUSTOM = "custom"


class SpanStatus(str, Enum):
    """Status of a span."""

    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class TraceStatus(str, Enum):
    """Status of a trace."""

    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class SpanEvent:
    """An event that occurred during a span."""

    name: str
    timestamp: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = {"name": self.name}
        if self.timestamp:
            data["timestamp"] = self.timestamp
        if self.attributes:
            data["attributes"] = self.attributes
        return data


@dataclass
class SpanData:
    """Data for a single span."""

    span_id: str
    name: str
    span_type: SpanType
    start_time: str  # ISO 8601
    parent_span_id: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    ttft_ms: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    input_preview: Optional[str] = None
    output_preview: Optional[str] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    status: SpanStatus = SpanStatus.RUNNING
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    events: Optional[List[SpanEvent]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API request."""
        data = {
            "spanId": self.span_id,
            "name": self.name,
            "spanType": self.span_type.value
            if isinstance(self.span_type, SpanType)
            else self.span_type,
            "startTime": self.start_time,
            "status": self.status.value if isinstance(self.status, SpanStatus) else self.status,
        }

        if self.parent_span_id:
            data["parentSpanId"] = self.parent_span_id
        if self.end_time:
            data["endTime"] = self.end_time
        if self.duration_ms is not None:
            data["durationMs"] = self.duration_ms
        if self.ttft_ms is not None:
            data["ttftMs"] = self.ttft_ms
        if self.provider:
            data["provider"] = self.provider
        if self.model:
            data["model"] = self.model
        if self.input_tokens is not None:
            data["inputTokens"] = self.input_tokens
        if self.output_tokens is not None:
            data["outputTokens"] = self.output_tokens
        if self.total_tokens is not None:
            data["totalTokens"] = self.total_tokens
        if self.cost_usd is not None:
            data["costUsd"] = self.cost_usd
        if self.input_preview:
            data["inputPreview"] = self.input_preview
        if self.output_preview:
            data["outputPreview"] = self.output_preview
        if self.input is not None:
            data["input"] = self.input
        if self.output is not None:
            data["output"] = self.output
        if self.error_type:
            data["errorType"] = self.error_type
        if self.error_message:
            data["errorMessage"] = self.error_message
        if self.metadata:
            data["metadata"] = self.metadata
        if self.events:
            data["events"] = [e.to_dict() for e in self.events]

        return data


@dataclass
class TraceData:
    """Data for a trace."""

    trace_id: str
    name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    status: TraceStatus = TraceStatus.RUNNING
    environment: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    sdk_name: str = "diagnyx-python"
    sdk_version: str = "0.1.0"
    spans: List[SpanData] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for API request."""
        data = {
            "traceId": self.trace_id,
            "sdkName": self.sdk_name,
            "sdkVersion": self.sdk_version,
            "status": self.status.value if isinstance(self.status, TraceStatus) else self.status,
        }

        if self.name:
            data["name"] = self.name
        if self.start_time:
            data["startTime"] = self.start_time
        if self.end_time:
            data["endTime"] = self.end_time
        if self.duration_ms is not None:
            data["durationMs"] = self.duration_ms
        if self.environment:
            data["environment"] = self.environment
        if self.user_id:
            data["userId"] = self.user_id
        if self.session_id:
            data["sessionId"] = self.session_id
        if self.metadata:
            data["metadata"] = self.metadata
        if self.tags:
            data["tags"] = self.tags
        if self.spans:
            data["spans"] = [s.to_dict() for s in self.spans]

        return data


@dataclass
class IngestResult:
    """Result of ingesting traces."""

    accepted: int
    failed: int
    errors: Optional[List[str]] = None
