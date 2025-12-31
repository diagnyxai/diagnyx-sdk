"""Tests for Diagnyx streaming guardrails module."""

import pytest
import httpx
import respx
from typing import AsyncIterator, Iterator, List
from unittest.mock import MagicMock, patch

from diagnyx.guardrails import (
    StreamingGuardrails,
    GuardrailViolationError,
    stream_with_guardrails,
    stream_with_guardrails_async,
    wrap_streaming_response,
)
from diagnyx.guardrails.types import (
    StreamingEventType,
    SessionStartedEvent,
    TokenAllowedEvent,
    ViolationDetectedEvent,
    EarlyTerminationEvent,
    SessionCompleteEvent,
    StreamingErrorEvent,
    GuardrailViolation,
    EnforcementLevel,
)


# Test fixtures


@pytest.fixture
def mock_guardrails_api():
    """Create a mock guardrails API responder."""
    with respx.mock(assert_all_called=False) as respx_mock:
        yield respx_mock


@pytest.fixture
def streaming_guardrails(mock_guardrails_api):
    """Create a StreamingGuardrails client with mocked API."""
    # Mock session start endpoint
    mock_guardrails_api.post(
        "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/start"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "type": "session_started",
                "sessionId": "session_123",
                "timestamp": 1704067200000,
                "activePolicies": ["content_filter", "pii_detection"],
            },
        )
    )

    # Mock token evaluation endpoint
    mock_guardrails_api.post(
        "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/token"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "events": [
                    {
                        "type": "token_allowed",
                        "sessionId": "session_123",
                        "timestamp": 1704067200100,
                        "tokenIndex": 0,
                        "accumulatedLength": 5,
                    }
                ]
            },
        )
    )

    # Mock session complete endpoint
    mock_guardrails_api.post(
        "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/complete"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "events": [
                    {
                        "type": "session_complete",
                        "sessionId": "session_123",
                        "timestamp": 1704067200500,
                        "totalTokens": 10,
                        "totalViolations": 0,
                        "allowed": True,
                        "latencyMs": 500,
                    }
                ]
            },
        )
    )

    client = StreamingGuardrails(
        api_key="test-api-key",
        base_url="https://api.diagnyx.io",
        organization_id="org_123",
        project_id="proj_456",
    )
    yield client


@pytest.fixture
def mock_openai_stream():
    """Create a mock OpenAI streaming response."""

    class MockDelta:
        def __init__(self, content: str):
            self.content = content

    class MockChoice:
        def __init__(self, delta: MockDelta, finish_reason: str = None):
            self.delta = delta
            self.finish_reason = finish_reason
            self.index = 0

    class MockChunk:
        def __init__(self, content: str, finish_reason: str = None):
            self.choices = [MockChoice(MockDelta(content), finish_reason)]

    def create_stream() -> Iterator:
        yield MockChunk("Hello")
        yield MockChunk(" there")
        yield MockChunk("!", "stop")

    return create_stream()


@pytest.fixture
def mock_openai_stream_async():
    """Create a mock async OpenAI streaming response."""

    class MockDelta:
        def __init__(self, content: str):
            self.content = content

    class MockChoice:
        def __init__(self, delta: MockDelta, finish_reason: str = None):
            self.delta = delta
            self.finish_reason = finish_reason
            self.index = 0

    class MockChunk:
        def __init__(self, content: str, finish_reason: str = None):
            self.choices = [MockChoice(MockDelta(content), finish_reason)]

    async def create_stream() -> AsyncIterator:
        yield MockChunk("Hello")
        yield MockChunk(" there")
        yield MockChunk("!", "stop")

    return create_stream()


# Tests for StreamingGuardrails client


class TestStreamingGuardrails:
    """Tests for StreamingGuardrails client."""

    def test_init(self):
        """Test client initialization."""
        client = StreamingGuardrails(
            api_key="test-key",
            organization_id="org_123",
            project_id="proj_456",
        )
        assert client.organization_id == "org_123"
        assert client.project_id == "proj_456"

    def test_init_with_base_url(self):
        """Test client initialization with custom base URL."""
        client = StreamingGuardrails(
            api_key="test-key",
            base_url="https://custom.api.com",
            organization_id="org_123",
            project_id="proj_456",
        )
        assert client._base_url == "https://custom.api.com"

    def test_start_session(self, streaming_guardrails):
        """Test starting a streaming session."""
        event = streaming_guardrails.start_session()
        assert isinstance(event, SessionStartedEvent)
        assert event.session_id == "session_123"
        assert "content_filter" in event.active_policies

    def test_start_session_with_input(self, streaming_guardrails):
        """Test starting a session with input text."""
        event = streaming_guardrails.start_session(input_text="Hello world")
        assert isinstance(event, SessionStartedEvent)
        assert event.session_id == "session_123"

    def test_evaluate_token(self, streaming_guardrails):
        """Test evaluating a token."""
        # Start session first
        streaming_guardrails.start_session()

        events = list(streaming_guardrails.evaluate_token("session_123", "Hello"))
        assert len(events) == 1
        assert isinstance(events[0], TokenAllowedEvent)

    def test_complete_session(self, streaming_guardrails):
        """Test completing a session."""
        # Start session first
        streaming_guardrails.start_session()

        events = list(streaming_guardrails.complete_session("session_123"))
        assert len(events) == 1
        assert isinstance(events[0], SessionCompleteEvent)
        assert events[0].allowed is True

    def test_get_session(self, streaming_guardrails):
        """Test getting session state."""
        streaming_guardrails.start_session()
        session = streaming_guardrails.get_session("session_123")
        assert session is not None
        assert session.session_id == "session_123"

    def test_get_nonexistent_session(self, streaming_guardrails):
        """Test getting a nonexistent session."""
        session = streaming_guardrails.get_session("nonexistent")
        assert session is None

    def test_cancel_session(self, streaming_guardrails):
        """Test cancelling a session."""
        streaming_guardrails.start_session()
        result = streaming_guardrails.cancel_session("session_123")
        assert result is True

    def test_cancel_nonexistent_session(self, streaming_guardrails):
        """Test cancelling a nonexistent session."""
        result = streaming_guardrails.cancel_session("nonexistent")
        assert result is False


class TestStreamingGuardrailsViolations:
    """Tests for violation handling."""

    def test_violation_event_parsing(self, mock_guardrails_api):
        """Test parsing violation events from API."""
        mock_guardrails_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/start"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "type": "session_started",
                    "sessionId": "session_123",
                    "timestamp": 1704067200000,
                    "activePolicies": ["content_filter"],
                },
            )
        )

        mock_guardrails_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/token"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "type": "violation_detected",
                            "sessionId": "session_123",
                            "timestamp": 1704067200100,
                            "policyId": "policy_123",
                            "policyName": "Content Filter",
                            "policyType": "content_filter",
                            "violationType": "blocked_content",
                            "message": "Blocked content detected",
                            "severity": "high",
                            "enforcementLevel": "blocking",
                            "details": {"matched_term": "bad_word"},
                        }
                    ]
                },
            )
        )

        client = StreamingGuardrails(
            api_key="test-key",
            base_url="https://api.diagnyx.io",
            organization_id="org_123",
            project_id="proj_456",
        )

        client.start_session()
        events = list(client.evaluate_token("session_123", "bad_word"))

        assert len(events) == 1
        assert isinstance(events[0], ViolationDetectedEvent)
        assert events[0].policy_name == "Content Filter"
        assert events[0].enforcement_level == EnforcementLevel.BLOCKING

    def test_early_termination_event(self, mock_guardrails_api):
        """Test early termination event parsing."""
        mock_guardrails_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/start"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "type": "session_started",
                    "sessionId": "session_123",
                    "timestamp": 1704067200000,
                    "activePolicies": ["content_filter"],
                },
            )
        )

        mock_guardrails_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/token"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "type": "early_termination",
                            "sessionId": "session_123",
                            "timestamp": 1704067200100,
                            "reason": "Blocking violation detected",
                            "tokensProcessed": 5,
                            "blockingViolation": {
                                "type": "violation_detected",
                                "sessionId": "session_123",
                                "timestamp": 1704067200100,
                                "policyId": "policy_123",
                                "policyName": "Content Filter",
                                "policyType": "content_filter",
                                "violationType": "blocked_content",
                                "message": "Blocked content",
                                "severity": "critical",
                                "enforcementLevel": "blocking",
                            },
                        }
                    ]
                },
            )
        )

        client = StreamingGuardrails(
            api_key="test-key",
            base_url="https://api.diagnyx.io",
            organization_id="org_123",
            project_id="proj_456",
        )

        client.start_session()
        events = list(client.evaluate_token("session_123", "bad content"))

        assert len(events) == 1
        assert isinstance(events[0], EarlyTerminationEvent)
        assert events[0].reason == "Blocking violation detected"
        assert events[0].blocking_violation is not None


# Tests for stream wrappers


class TestStreamWithGuardrails:
    """Tests for stream_with_guardrails wrapper."""

    def test_stream_with_guardrails_success(
        self, streaming_guardrails, mock_openai_stream
    ):
        """Test wrapping a stream with guardrails successfully."""
        chunks = list(
            stream_with_guardrails(mock_openai_stream, streaming_guardrails)
        )
        assert len(chunks) == 3
        assert chunks[0].choices[0].delta.content == "Hello"
        assert chunks[1].choices[0].delta.content == " there"
        assert chunks[2].choices[0].delta.content == "!"

    def test_stream_with_guardrails_with_input(
        self, streaming_guardrails, mock_openai_stream
    ):
        """Test wrapping with input text evaluation."""
        chunks = list(
            stream_with_guardrails(
                mock_openai_stream,
                streaming_guardrails,
                input_text="User message",
            )
        )
        assert len(chunks) == 3

    def test_stream_with_guardrails_violation_callback(
        self, streaming_guardrails, mock_guardrails_api
    ):
        """Test violation callback is called."""
        # Override token endpoint to return violation
        mock_guardrails_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/token"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "type": "violation_detected",
                            "sessionId": "session_123",
                            "timestamp": 1704067200100,
                            "policyId": "policy_123",
                            "policyName": "PII Detection",
                            "policyType": "pii_detection",
                            "violationType": "pii_detected",
                            "message": "PII detected",
                            "severity": "medium",
                            "enforcementLevel": "advisory",
                        },
                        {
                            "type": "token_allowed",
                            "sessionId": "session_123",
                            "timestamp": 1704067200101,
                            "tokenIndex": 0,
                            "accumulatedLength": 5,
                        },
                    ]
                },
            )
        )

        violations = []

        def on_violation(violation, session):
            violations.append(violation)

        class MockChunk:
            def __init__(self, content, finish_reason=None):
                self.choices = [
                    MagicMock(delta=MagicMock(content=content), finish_reason=finish_reason)
                ]

        stream = iter([MockChunk("Hello", "stop")])
        chunks = list(
            stream_with_guardrails(
                stream,
                streaming_guardrails,
                on_violation=on_violation,
            )
        )

        assert len(violations) == 1
        assert violations[0].policy_name == "PII Detection"

    def test_stream_with_guardrails_early_termination(
        self, streaming_guardrails, mock_guardrails_api
    ):
        """Test early termination raises error."""
        # Override token endpoint to return early termination
        mock_guardrails_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/token"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "type": "early_termination",
                            "sessionId": "session_123",
                            "timestamp": 1704067200100,
                            "reason": "Blocking violation",
                            "tokensProcessed": 1,
                            "blockingViolation": {
                                "type": "violation_detected",
                                "sessionId": "session_123",
                                "timestamp": 1704067200100,
                                "policyId": "policy_123",
                                "policyName": "Content Filter",
                                "policyType": "content_filter",
                                "violationType": "blocked",
                                "message": "Blocked",
                                "severity": "critical",
                                "enforcementLevel": "blocking",
                            },
                        }
                    ]
                },
            )
        )

        class MockChunk:
            def __init__(self, content):
                self.choices = [MagicMock(delta=MagicMock(content=content), finish_reason=None)]

        stream = iter([MockChunk("bad")])

        with pytest.raises(GuardrailViolationError) as exc_info:
            list(stream_with_guardrails(stream, streaming_guardrails))

        assert exc_info.value.violation.policy_name == "Content Filter"

    def test_stream_with_guardrails_no_raise(
        self, streaming_guardrails, mock_guardrails_api
    ):
        """Test early termination without raising when raise_on_blocking=False."""
        mock_guardrails_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org_123/tracing/guardrails/stream/token"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "type": "early_termination",
                            "sessionId": "session_123",
                            "timestamp": 1704067200100,
                            "reason": "Blocking violation",
                            "tokensProcessed": 1,
                            "blockingViolation": {
                                "type": "violation_detected",
                                "sessionId": "session_123",
                                "timestamp": 1704067200100,
                                "policyId": "policy_123",
                                "policyName": "Content Filter",
                                "policyType": "content_filter",
                                "violationType": "blocked",
                                "message": "Blocked",
                                "severity": "critical",
                                "enforcementLevel": "blocking",
                            },
                        }
                    ]
                },
            )
        )

        class MockChunk:
            def __init__(self, content):
                self.choices = [MagicMock(delta=MagicMock(content=content), finish_reason=None)]

        stream = iter([MockChunk("bad")])

        # Should not raise
        chunks = list(
            stream_with_guardrails(
                stream, streaming_guardrails, raise_on_blocking=False
            )
        )
        assert len(chunks) == 0  # Stream terminated early

    def test_custom_token_extractor(self, streaming_guardrails):
        """Test using custom token content extractor."""

        class CustomChunk:
            def __init__(self, text):
                self.text = text
                self.done = False

        stream = iter([CustomChunk("Hello"), CustomChunk("World")])

        def get_token(chunk):
            return chunk.text

        def is_last(chunk):
            return chunk.done

        chunks = list(
            stream_with_guardrails(
                stream,
                streaming_guardrails,
                get_token_content=get_token,
                get_is_last=is_last,
            )
        )
        assert len(chunks) == 2


class TestStreamWithGuardrailsAsync:
    """Tests for stream_with_guardrails_async wrapper."""

    @pytest.mark.asyncio
    async def test_async_stream_success(self, streaming_guardrails):
        """Test async stream wrapping."""

        async def mock_stream():
            class MockChunk:
                def __init__(self, content, finish_reason=None):
                    self.choices = [
                        MagicMock(delta=MagicMock(content=content), finish_reason=finish_reason)
                    ]

            yield MockChunk("Hello")
            yield MockChunk(" World", "stop")

        chunks = []
        async for chunk in stream_with_guardrails_async(
            mock_stream(), streaming_guardrails
        ):
            chunks.append(chunk)

        assert len(chunks) == 2


class TestWrapStreamingResponse:
    """Tests for wrap_streaming_response decorator."""

    def test_wrap_function(self, streaming_guardrails):
        """Test wrapping a function that returns a stream."""

        class MockChunk:
            def __init__(self, content, finish_reason=None):
                self.choices = [
                    MagicMock(delta=MagicMock(content=content), finish_reason=finish_reason)
                ]

        def get_completion(prompt: str):
            return iter([MockChunk("Hello"), MockChunk("!", "stop")])

        wrapped = wrap_streaming_response(streaming_guardrails)(get_completion)
        chunks = list(wrapped("test prompt"))

        assert len(chunks) == 2


class TestGuardrailViolation:
    """Tests for GuardrailViolation type."""

    def test_violation_from_event(self):
        """Test creating violation from event."""
        event = ViolationDetectedEvent(
            type=StreamingEventType.VIOLATION_DETECTED,
            session_id="session_123",
            timestamp=1704067200000,
            policy_id="policy_123",
            policy_name="Test Policy",
            policy_type="content_filter",
            violation_type="blocked_content",
            message="Content blocked",
            severity="high",
            enforcement_level=EnforcementLevel.BLOCKING,
        )

        violation = event.to_violation()
        assert violation.policy_id == "policy_123"
        assert violation.policy_name == "Test Policy"
        assert violation.is_blocking is True

    def test_violation_str(self):
        """Test violation string representation."""
        violation = GuardrailViolation(
            policy_id="policy_123",
            policy_name="Test Policy",
            policy_type="content_filter",
            violation_type="blocked",
            message="Test message",
            severity="high",
            enforcement_level=EnforcementLevel.BLOCKING,
        )
        assert "Test Policy" in str(violation)
        assert "Test message" in str(violation)


class TestGuardrailViolationError:
    """Tests for GuardrailViolationError exception."""

    def test_error_properties(self, streaming_guardrails):
        """Test error has correct properties."""
        streaming_guardrails.start_session()
        session = streaming_guardrails.get_session("session_123")

        violation = GuardrailViolation(
            policy_id="policy_123",
            policy_name="Test Policy",
            policy_type="content_filter",
            violation_type="blocked",
            message="Blocked",
            severity="critical",
            enforcement_level=EnforcementLevel.BLOCKING,
        )

        error = GuardrailViolationError(violation, session)

        assert error.violation == violation
        assert error.session == session
        assert "Test Policy" in str(error)

    def test_error_raises(self):
        """Test error can be raised and caught."""
        violation = GuardrailViolation(
            policy_id="policy_123",
            policy_name="Test Policy",
            policy_type="content_filter",
            violation_type="blocked",
            message="Blocked",
            severity="critical",
            enforcement_level=EnforcementLevel.BLOCKING,
        )

        with pytest.raises(GuardrailViolationError) as exc_info:
            raise GuardrailViolationError(violation, None)

        assert exc_info.value.violation.policy_name == "Test Policy"
