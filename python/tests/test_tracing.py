"""Tests for tracing module."""

import pytest
import httpx
import respx
from unittest.mock import MagicMock, patch

from diagnyx import Diagnyx, Trace, Span, Tracer
from diagnyx.tracing_types import SpanType, SpanStatus, TraceStatus


@pytest.fixture
def mock_diagnyx_client(mock_api):
    """Create a Diagnyx client with mocked API."""
    mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
        return_value=httpx.Response(200, json={"tracked": 0})
    )
    mock_api.post(
        url__regex=r"https://api\.diagnyx\.io/api/v1/organizations/.+/tracing/ingest"
    ).mock(return_value=httpx.Response(200, json={"accepted": 1, "failed": 0}))

    client = Diagnyx(
        api_key="test-api-key",
        base_url="https://api.diagnyx.io",
        flush_interval_ms=60000,
    )
    yield client
    client.shutdown()


class TestSpan:
    """Tests for Span class."""

    def test_span_creation(self, mock_diagnyx_client):
        """Should create span with required properties."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace(name="test-trace")
        span = trace.span("test-span")

        assert span.name == "test-span"
        assert span.span_type == SpanType.FUNCTION
        assert span.span_id is not None
        assert span.trace is trace
        assert span.start_time is not None
        assert span.parent_span_id is None

    def test_span_with_type(self, mock_diagnyx_client):
        """Should create span with custom type."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace(name="test-trace")
        span = trace.span("llm-call", span_type=SpanType.LLM)

        assert span.span_type == SpanType.LLM

    def test_set_input(self, mock_diagnyx_client):
        """Should set input with preview."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.set_input("Hello, World!")

        assert span.input == "Hello, World!"
        assert span.input_preview == "Hello, World!"

    def test_set_input_object(self, mock_diagnyx_client):
        """Should set object input with JSON preview."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.set_input({"messages": [{"role": "user", "content": "Hello"}]})

        assert span.input == {"messages": [{"role": "user", "content": "Hello"}]}
        assert "messages" in span.input_preview

    def test_set_output(self, mock_diagnyx_client):
        """Should set output with preview."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.set_output("Response text")

        assert span.output == "Response text"
        assert span.output_preview == "Response text"

    def test_set_llm_info(self, mock_diagnyx_client):
        """Should set LLM info."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test", span_type=SpanType.LLM)
        span.set_llm_info(
            provider="openai",
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
        )

        assert span.provider == "openai"
        assert span.model == "gpt-4"
        assert span.input_tokens == 100
        assert span.output_tokens == 50
        assert span.total_tokens == 150
        assert span.cost_usd == 0.01

    def test_set_metadata(self, mock_diagnyx_client):
        """Should set metadata."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.set_metadata("key", "value")

        assert span.metadata["key"] == "value"

    def test_add_event(self, mock_diagnyx_client):
        """Should add events."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.add_event("checkpoint", {"progress": 50})

        assert len(span.events) == 1
        assert span.events[0].name == "checkpoint"

    def test_set_error(self, mock_diagnyx_client):
        """Should set error state."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.set_error(ValueError("Something went wrong"))

        assert span.status == SpanStatus.ERROR
        assert span.error_type == "ValueError"
        assert span.error_message == "Something went wrong"

    def test_set_error_string(self, mock_diagnyx_client):
        """Should set error from string."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.set_error("Custom error", error_type="CustomError")

        assert span.status == SpanStatus.ERROR
        assert span.error_type == "CustomError"
        assert span.error_message == "Custom error"

    def test_end_span(self, mock_diagnyx_client):
        """Should end span with success status."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.end()

        assert span.end_time is not None
        assert span.duration_ms is not None
        assert span.status == SpanStatus.SUCCESS

    def test_end_span_with_status(self, mock_diagnyx_client):
        """Should end span with custom status."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.end(status=SpanStatus.CANCELLED)

        assert span.status == SpanStatus.CANCELLED

    def test_end_idempotent(self, mock_diagnyx_client):
        """Should be idempotent."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")
        span.end()
        end_time1 = span.end_time
        span.end(status=SpanStatus.ERROR)

        assert span.end_time == end_time1
        assert span.status == SpanStatus.SUCCESS

    def test_context_manager(self, mock_diagnyx_client):
        """Should work as context manager."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()

        with trace.span("test") as span:
            pass

        assert span.status == SpanStatus.SUCCESS
        assert span.end_time is not None

    def test_context_manager_error(self, mock_diagnyx_client):
        """Should capture errors in context manager."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()

        with pytest.raises(ValueError):
            with trace.span("test") as span:
                raise ValueError("Test error")

        assert span.status == SpanStatus.ERROR
        assert span.error_message == "Test error"

    def test_chainable_methods(self, mock_diagnyx_client):
        """Methods should be chainable."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        span = trace.span("test")

        result = span.set_input("input").set_output("output").set_metadata("key", "value")

        assert result is span


class TestTrace:
    """Tests for Trace class."""

    def test_trace_creation(self, mock_diagnyx_client):
        """Should create trace with properties."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace(name="test-trace")

        assert trace.trace_id is not None
        assert trace.name == "test-trace"
        assert trace.start_time is not None

    def test_trace_with_custom_id(self, mock_diagnyx_client):
        """Should use provided trace ID."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace(trace_id="custom-id")

        assert trace.trace_id == "custom-id"

    def test_trace_with_options(self, mock_diagnyx_client):
        """Should initialize with options."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace(
            name="test",
            user_id="user-123",
            session_id="session-456",
            metadata={"key": "value"},
            tags=["tag1"],
        )

        assert trace.user_id == "user-123"
        assert trace.session_id == "session-456"
        assert trace.metadata == {"key": "value"}
        assert "tag1" in trace.tags

    def test_set_metadata(self, mock_diagnyx_client):
        """Should set metadata."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        trace.set_metadata("key", "value")

        assert trace.metadata["key"] == "value"

    def test_add_tag(self, mock_diagnyx_client):
        """Should add tags."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        trace.add_tag("important")

        assert "important" in trace.tags

    def test_add_tag_no_duplicates(self, mock_diagnyx_client):
        """Should not add duplicate tags."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        trace.add_tag("tag1").add_tag("tag1")

        assert trace.tags.count("tag1") == 1

    def test_set_user(self, mock_diagnyx_client):
        """Should set user ID."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        trace.set_user("user-abc")

        assert trace.user_id == "user-abc"

    def test_set_session(self, mock_diagnyx_client):
        """Should set session ID."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        trace.set_session("session-xyz")

        assert trace.session_id == "session-xyz"

    def test_end_trace(self, mock_diagnyx_client, mock_api):
        """Should end trace and send to backend."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()
        trace.end()

        assert trace.end_time is not None
        assert trace.duration_ms is not None
        assert trace.status == TraceStatus.SUCCESS

    def test_end_trace_error_status_from_spans(self, mock_diagnyx_client):
        """Should set error status if any span has error."""
        tracer = mock_diagnyx_client.tracer("org-123")
        trace = tracer.trace()

        with trace.span("failing") as span:
            span.set_error("failed")

        trace.end()

        assert trace.status == TraceStatus.ERROR

    def test_context_manager(self, mock_diagnyx_client):
        """Should work as context manager."""
        tracer = mock_diagnyx_client.tracer("org-123")

        with tracer.trace(name="test") as trace:
            pass

        assert trace.status == TraceStatus.SUCCESS

    def test_to_data(self, mock_diagnyx_client):
        """Should serialize to data."""
        tracer = mock_diagnyx_client.tracer("org-123", environment="production")
        trace = tracer.trace(name="test", metadata={"key": "value"})

        with trace.span("child") as span:
            pass

        trace.end()
        data = trace.to_data()

        assert data.trace_id == trace.trace_id
        assert data.name == "test"
        assert data.environment == "production"
        assert data.sdk_name == "diagnyx-python"
        assert len(data.spans) == 1


class TestTracer:
    """Tests for Tracer class."""

    def test_tracer_creation(self, mock_diagnyx_client):
        """Should create tracer with config."""
        tracer = mock_diagnyx_client.tracer(
            "org-123", environment="staging", default_metadata={"version": "1.0"}
        )

        assert tracer.organization_id == "org-123"
        assert tracer.environment == "staging"
        assert tracer.default_metadata == {"version": "1.0"}

    def test_trace_inherits_environment(self, mock_diagnyx_client):
        """Should inherit environment from tracer."""
        tracer = mock_diagnyx_client.tracer("org-123", environment="production")
        trace = tracer.trace(name="test")

        assert trace.environment == "production"

    def test_trace_merges_metadata(self, mock_diagnyx_client):
        """Should merge default and trace metadata."""
        tracer = mock_diagnyx_client.tracer(
            "org-123", default_metadata={"default": "value"}
        )
        trace = tracer.trace(name="test", metadata={"custom": "data"})

        assert trace.metadata["default"] == "value"
        assert trace.metadata["custom"] == "data"

    def test_standalone_span(self, mock_diagnyx_client):
        """Should create span with auto-created trace."""
        tracer = mock_diagnyx_client.tracer("org-123")
        span = tracer.span("standalone")

        assert span is not None
        assert span.trace is not None

    def test_get_current_trace(self, mock_diagnyx_client):
        """Should return current trace in context."""
        tracer = mock_diagnyx_client.tracer("org-123")

        with tracer.trace(name="test") as trace:
            current = tracer.get_current_trace()
            assert current is trace

    def test_get_current_span(self, mock_diagnyx_client):
        """Should return current span in context."""
        tracer = mock_diagnyx_client.tracer("org-123")

        with tracer.trace(name="test") as trace:
            with trace.span("child") as span:
                current = tracer.get_current_span()
                assert current is span

    def test_flush(self, mock_diagnyx_client, mock_api):
        """Should flush pending traces."""
        tracer = mock_diagnyx_client.tracer("org-123")

        with tracer.trace(name="test"):
            pass

        # Trace was sent
        assert mock_api.calls.call_count >= 1


class TestTracerWrapOpenAI:
    """Tests for Tracer.wrap_openai method."""

    def test_wrap_openai(self, mock_diagnyx_client, mock_openai_client, mock_api):
        """Should wrap OpenAI client."""
        tracer = mock_diagnyx_client.tracer("org-123")
        wrapped = tracer.wrap_openai(mock_openai_client)

        result = wrapped.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.id == "chatcmpl-123"

    def test_wrap_openai_traces_call(self, mock_diagnyx_client, mock_openai_client, mock_api):
        """Should trace OpenAI calls."""
        tracer = mock_diagnyx_client.tracer("org-123")
        wrapped = tracer.wrap_openai(mock_openai_client)

        with tracer.trace(name="parent") as trace:
            wrapped.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello"}],
            )

        data = trace.to_data()
        assert len(data.spans) == 1
        assert data.spans[0].name == "openai.chat.completions.create"
        assert data.spans[0].provider == "openai"


class TestTracerWrapAnthropic:
    """Tests for Tracer.wrap_anthropic method."""

    def test_wrap_anthropic(self, mock_diagnyx_client, mock_anthropic_client, mock_api):
        """Should wrap Anthropic client."""
        tracer = mock_diagnyx_client.tracer("org-123")
        wrapped = tracer.wrap_anthropic(mock_anthropic_client)

        result = wrapped.messages.create(
            model="claude-3-opus",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.id == "msg-123"

    def test_wrap_anthropic_traces_call(
        self, mock_diagnyx_client, mock_anthropic_client, mock_api
    ):
        """Should trace Anthropic calls."""
        tracer = mock_diagnyx_client.tracer("org-123")
        wrapped = tracer.wrap_anthropic(mock_anthropic_client)

        with tracer.trace(name="parent") as trace:
            wrapped.messages.create(
                model="claude-3-opus",
                messages=[{"role": "user", "content": "Hello"}],
            )

        data = trace.to_data()
        assert len(data.spans) == 1
        assert data.spans[0].name == "anthropic.messages.create"
        assert data.spans[0].provider == "anthropic"
