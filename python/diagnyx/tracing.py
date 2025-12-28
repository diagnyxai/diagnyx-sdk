"""Tracing context and span management for Diagnyx SDK."""

import contextvars
import functools
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from .tracing_types import (
    IngestResult,
    SpanData,
    SpanEvent,
    SpanStatus,
    SpanType,
    TraceData,
    TraceStatus,
)

T = TypeVar("T")

# Context variables for tracing
_current_trace: contextvars.ContextVar[Optional["Trace"]] = contextvars.ContextVar(
    "current_trace", default=None
)
_current_span: contextvars.ContextVar[Optional["Span"]] = contextvars.ContextVar(
    "current_span", default=None
)


def _generate_id() -> str:
    """Generate a unique ID for traces and spans."""
    return uuid.uuid4().hex[:16]


def _now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class Span:
    """A span represents a single operation within a trace."""

    def __init__(
        self,
        trace: "Trace",
        name: str,
        span_type: SpanType = SpanType.FUNCTION,
        parent: Optional["Span"] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.trace = trace
        self.span_id = _generate_id()
        self.name = name
        self.span_type = span_type
        self.parent = parent
        self.parent_span_id = parent.span_id if parent else None
        self.start_time = _now_iso()
        self.start_timestamp = time.time()
        self.end_time: Optional[str] = None
        self.duration_ms: Optional[int] = None
        self.ttft_ms: Optional[int] = None
        self.provider: Optional[str] = None
        self.model: Optional[str] = None
        self.input_tokens: Optional[int] = None
        self.output_tokens: Optional[int] = None
        self.total_tokens: Optional[int] = None
        self.cost_usd: Optional[float] = None
        self.input_preview: Optional[str] = None
        self.output_preview: Optional[str] = None
        self.input: Optional[Any] = None
        self.output: Optional[Any] = None
        self.status: SpanStatus = SpanStatus.RUNNING
        self.error_type: Optional[str] = None
        self.error_message: Optional[str] = None
        self.metadata: Dict[str, Any] = metadata or {}
        self.events: List[SpanEvent] = []
        self._token: Optional[contextvars.Token] = None
        self._ended = False

    def set_input(
        self,
        input_data: Any,
        preview: Optional[str] = None,
        max_preview_length: int = 500,
    ) -> "Span":
        """Set the input for this span."""
        self.input = input_data
        if preview:
            self.input_preview = preview[:max_preview_length]
        elif isinstance(input_data, str):
            self.input_preview = input_data[:max_preview_length]
        elif isinstance(input_data, (dict, list)):
            import json
            preview_str = json.dumps(input_data)[:max_preview_length]
            self.input_preview = preview_str
        return self

    def set_output(
        self,
        output_data: Any,
        preview: Optional[str] = None,
        max_preview_length: int = 500,
    ) -> "Span":
        """Set the output for this span."""
        self.output = output_data
        if preview:
            self.output_preview = preview[:max_preview_length]
        elif isinstance(output_data, str):
            self.output_preview = output_data[:max_preview_length]
        elif isinstance(output_data, (dict, list)):
            import json
            preview_str = json.dumps(output_data)[:max_preview_length]
            self.output_preview = preview_str
        return self

    def set_llm_info(
        self,
        provider: str,
        model: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        cost_usd: Optional[float] = None,
        ttft_ms: Optional[int] = None,
    ) -> "Span":
        """Set LLM-specific information for this span."""
        self.provider = provider
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        if input_tokens is not None and output_tokens is not None:
            self.total_tokens = input_tokens + output_tokens
        self.cost_usd = cost_usd
        self.ttft_ms = ttft_ms
        return self

    def set_metadata(self, key: str, value: Any) -> "Span":
        """Set a metadata key-value pair."""
        self.metadata[key] = value
        return self

    def add_event(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> "Span":
        """Add an event to this span."""
        event = SpanEvent(
            name=name,
            timestamp=_now_iso(),
            attributes=attributes,
        )
        self.events.append(event)
        return self

    def set_error(
        self,
        error: Union[Exception, str],
        error_type: Optional[str] = None,
    ) -> "Span":
        """Mark this span as errored."""
        self.status = SpanStatus.ERROR
        if isinstance(error, Exception):
            self.error_type = error_type or type(error).__name__
            self.error_message = str(error)
        else:
            self.error_type = error_type or "Error"
            self.error_message = error
        return self

    def end(self, status: Optional[SpanStatus] = None) -> "Span":
        """End this span."""
        if self._ended:
            return self

        self._ended = True
        self.end_time = _now_iso()
        self.duration_ms = int((time.time() - self.start_timestamp) * 1000)

        if status:
            self.status = status
        elif self.status == SpanStatus.RUNNING:
            self.status = SpanStatus.SUCCESS

        # Restore parent span context
        if self._token:
            _current_span.reset(self._token)

        # Add span to trace
        self.trace._add_span(self)

        return self

    def to_data(self) -> SpanData:
        """Convert to SpanData for serialization."""
        return SpanData(
            span_id=self.span_id,
            name=self.name,
            span_type=self.span_type,
            parent_span_id=self.parent_span_id,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_ms=self.duration_ms,
            ttft_ms=self.ttft_ms,
            provider=self.provider,
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.total_tokens,
            cost_usd=self.cost_usd,
            input_preview=self.input_preview,
            output_preview=self.output_preview,
            input=self.input,
            output=self.output,
            status=self.status,
            error_type=self.error_type,
            error_message=self.error_message,
            metadata=self.metadata if self.metadata else None,
            events=self.events if self.events else None,
        )

    def __enter__(self) -> "Span":
        """Context manager entry."""
        self._token = _current_span.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_val:
            self.set_error(exc_val)
        self.end()
        return False


class Trace:
    """A trace represents a complete request flow with multiple spans."""

    def __init__(
        self,
        tracer: "Tracer",
        name: Optional[str] = None,
        trace_id: Optional[str] = None,
        environment: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ):
        self.tracer = tracer
        self.trace_id = trace_id or _generate_id()
        self.name = name
        self.start_time = _now_iso()
        self.start_timestamp = time.time()
        self.end_time: Optional[str] = None
        self.duration_ms: Optional[int] = None
        self.status: TraceStatus = TraceStatus.RUNNING
        self.environment = environment
        self.user_id = user_id
        self.session_id = session_id
        self.metadata: Dict[str, Any] = metadata or {}
        self.tags: List[str] = tags or []
        self._spans: List[SpanData] = []
        self._token: Optional[contextvars.Token] = None
        self._ended = False

    def span(
        self,
        name: str,
        span_type: SpanType = SpanType.FUNCTION,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """Create a new span within this trace."""
        parent = _current_span.get()
        span = Span(
            trace=self,
            name=name,
            span_type=span_type,
            parent=parent,
            metadata=metadata,
        )
        return span

    def set_metadata(self, key: str, value: Any) -> "Trace":
        """Set a metadata key-value pair."""
        self.metadata[key] = value
        return self

    def add_tag(self, tag: str) -> "Trace":
        """Add a tag to this trace."""
        if tag not in self.tags:
            self.tags.append(tag)
        return self

    def set_user(self, user_id: str) -> "Trace":
        """Set the user ID for this trace."""
        self.user_id = user_id
        return self

    def set_session(self, session_id: str) -> "Trace":
        """Set the session ID for this trace."""
        self.session_id = session_id
        return self

    def _add_span(self, span: Span) -> None:
        """Add a completed span to this trace."""
        self._spans.append(span.to_data())

    def end(self, status: Optional[TraceStatus] = None) -> "Trace":
        """End this trace and send to backend."""
        if self._ended:
            return self

        self._ended = True
        self.end_time = _now_iso()
        self.duration_ms = int((time.time() - self.start_timestamp) * 1000)

        if status:
            self.status = status
        elif self.status == TraceStatus.RUNNING:
            # Determine status from spans
            has_error = any(s.status == SpanStatus.ERROR for s in self._spans)
            self.status = TraceStatus.ERROR if has_error else TraceStatus.SUCCESS

        # Restore trace context
        if self._token:
            _current_trace.reset(self._token)

        # Send trace to backend
        self.tracer._send_trace(self)

        return self

    def to_data(self) -> TraceData:
        """Convert to TraceData for serialization."""
        return TraceData(
            trace_id=self.trace_id,
            name=self.name,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_ms=self.duration_ms,
            status=self.status,
            environment=self.environment,
            user_id=self.user_id,
            session_id=self.session_id,
            metadata=self.metadata if self.metadata else None,
            tags=self.tags if self.tags else None,
            sdk_name="diagnyx-python",
            sdk_version="0.1.0",
            spans=self._spans,
        )

    def __enter__(self) -> "Trace":
        """Context manager entry."""
        self._token = _current_trace.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_val:
            self.status = TraceStatus.ERROR
        self.end()
        return False


class Tracer:
    """Tracer for creating and managing traces."""

    def __init__(
        self,
        client: Any,  # Diagnyx client
        organization_id: str,
        environment: Optional[str] = None,
        default_metadata: Optional[Dict[str, Any]] = None,
    ):
        self.client = client
        self.organization_id = organization_id
        self.environment = environment
        self.default_metadata = default_metadata or {}
        self._pending_traces: List[TraceData] = []

    def trace(
        self,
        name: Optional[str] = None,
        trace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Trace:
        """Create a new trace."""
        merged_metadata = {**self.default_metadata, **(metadata or {})}
        return Trace(
            tracer=self,
            name=name,
            trace_id=trace_id,
            environment=self.environment,
            user_id=user_id,
            session_id=session_id,
            metadata=merged_metadata,
            tags=tags,
        )

    def span(
        self,
        name: str,
        span_type: SpanType = SpanType.FUNCTION,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """Create a span in the current trace context.

        If no trace is active, creates a new trace automatically.
        """
        trace = _current_trace.get()
        if trace is None:
            # Auto-create a trace
            trace = self.trace(name=name)
            trace._token = _current_trace.set(trace)
        return trace.span(name=name, span_type=span_type, metadata=metadata)

    def _send_trace(self, trace: Trace) -> None:
        """Send a completed trace to the backend."""
        trace_data = trace.to_data()
        self._pending_traces.append(trace_data)

        # Flush if we have enough traces
        if len(self._pending_traces) >= self.client.config.batch_size:
            self.flush()
        else:
            # Always send immediately for now (can be batched later)
            self.flush()

    def flush(self) -> Optional[IngestResult]:
        """Flush pending traces to the backend."""
        if not self._pending_traces:
            return None

        traces = self._pending_traces.copy()
        self._pending_traces.clear()

        return self.client._send_traces(self.organization_id, traces)

    def get_current_trace(self) -> Optional[Trace]:
        """Get the current trace from context."""
        return _current_trace.get()

    def get_current_span(self) -> Optional[Span]:
        """Get the current span from context."""
        return _current_span.get()


def trace(
    name: Optional[str] = None,
    span_type: SpanType = SpanType.FUNCTION,
    capture_input: bool = False,
    capture_output: bool = False,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to trace a function.

    Usage:
        @trace(name="my_function")
        def my_function(x, y):
            return x + y
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            current_trace = _current_trace.get()
            if current_trace is None:
                # No trace context, just run the function
                return func(*args, **kwargs)

            span_name = name or func.__name__
            span = current_trace.span(span_name, span_type=span_type)

            with span:
                if capture_input:
                    span.set_input({"args": args, "kwargs": kwargs})

                result = func(*args, **kwargs)

                if capture_output:
                    span.set_output(result)

                return result

        return wrapper

    return decorator
