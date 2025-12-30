"""Pytest configuration and fixtures for Diagnyx SDK tests."""

import pytest
import httpx
import respx
from typing import Any, Dict
from datetime import datetime

from diagnyx import Diagnyx, LLMCallData, LLMProvider, CallStatus


@pytest.fixture
def mock_api():
    """Create a mock API responder."""
    with respx.mock(assert_all_called=False) as respx_mock:
        yield respx_mock


@pytest.fixture
def diagnyx_client(mock_api):
    """Create a Diagnyx client with mocked API."""
    # Mock the batch endpoint
    mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
        return_value=httpx.Response(
            200,
            json={
                "tracked": 1,
                "total_cost": 0.001,
                "total_tokens": 100,
                "ids": ["test-id-1"],
            },
        )
    )

    client = Diagnyx(
        api_key="test-api-key",
        base_url="https://api.diagnyx.io",
        batch_size=10,
        flush_interval_ms=60000,  # Long interval to prevent auto-flush during tests
        debug=False,
    )
    yield client
    client.shutdown()


@pytest.fixture
def sample_call_data():
    """Create sample LLM call data."""
    return LLMCallData(
        provider=LLMProvider.OPENAI,
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        status=CallStatus.SUCCESS,
        latency_ms=500,
        timestamp=datetime.utcnow(),
    )


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""

    class MockUsage:
        def __init__(self):
            self.prompt_tokens = 100
            self.completion_tokens = 50

    class MockMessage:
        def __init__(self):
            self.content = "Hello! How can I help you?"
            self.role = "assistant"

    class MockChoice:
        def __init__(self):
            self.message = MockMessage()
            self.index = 0
            self.finish_reason = "stop"

    class MockCompletion:
        def __init__(self):
            self.id = "chatcmpl-123"
            self.model = "gpt-4"
            self.choices = [MockChoice()]
            self.usage = MockUsage()

    class MockChatCompletions:
        def __init__(self):
            self._create_called = False

        def create(self, **kwargs) -> MockCompletion:
            self._create_called = True
            return MockCompletion()

    class MockChat:
        def __init__(self):
            self.completions = MockChatCompletions()

    class MockOpenAI:
        def __init__(self):
            self.chat = MockChat()

    return MockOpenAI()


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client."""

    class MockUsage:
        def __init__(self):
            self.input_tokens = 100
            self.output_tokens = 50

    class MockContentBlock:
        def __init__(self):
            self.type = "text"
            self.text = "Hello! How can I help you?"

    class MockMessage:
        def __init__(self):
            self.id = "msg-123"
            self.model = "claude-3-opus"
            self.content = [MockContentBlock()]
            self.usage = MockUsage()
            self.stop_reason = "end_turn"

    class MockMessages:
        def __init__(self):
            self._create_called = False

        def create(self, **kwargs) -> MockMessage:
            self._create_called = True
            return MockMessage()

    class MockAnthropic:
        def __init__(self):
            self.messages = MockMessages()

    return MockAnthropic()
