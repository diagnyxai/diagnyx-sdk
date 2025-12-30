"""Tests for LLM client wrappers."""

import pytest
import httpx
import respx
from datetime import datetime

from diagnyx import Diagnyx, LLMProvider, CallStatus
from diagnyx.wrappers import (
    wrap_openai,
    wrap_anthropic,
    track_with_timing,
    _extract_openai_prompt,
    _extract_openai_response,
    _extract_anthropic_prompt,
    _extract_anthropic_response,
)


class TestWrapOpenAI:
    """Tests for wrap_openai function."""

    def test_wrap_openai_tracks_successful_call(
        self, diagnyx_client, mock_openai_client, mock_api
    ):
        """Should track successful OpenAI calls."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(
                200,
                json={"tracked": 1, "total_cost": 0.001, "total_tokens": 150, "ids": ["id-1"]},
            )
        )

        wrapped_client = wrap_openai(mock_openai_client, diagnyx_client)

        result = wrapped_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.id == "chatcmpl-123"
        assert diagnyx_client.buffer_size == 1

    def test_wrap_openai_tracks_error_call(self, diagnyx_client, mock_api):
        """Should track OpenAI errors."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(200, json={"tracked": 1})
        )

        class FailingOpenAI:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        raise Exception("API Error")

        wrapped_client = wrap_openai(FailingOpenAI(), diagnyx_client)

        with pytest.raises(Exception, match="API Error"):
            wrapped_client.chat.completions.create(model="gpt-4", messages=[])

        # Error should still be tracked
        assert diagnyx_client.buffer_size == 1

    def test_wrap_openai_with_project_id(
        self, diagnyx_client, mock_openai_client, mock_api
    ):
        """Should include project_id in tracked data."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(200, json={"tracked": 1})
        )

        wrapped_client = wrap_openai(
            mock_openai_client, diagnyx_client, project_id="proj-123"
        )

        wrapped_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert diagnyx_client.buffer_size == 1


class TestWrapAnthropic:
    """Tests for wrap_anthropic function."""

    def test_wrap_anthropic_tracks_successful_call(
        self, diagnyx_client, mock_anthropic_client, mock_api
    ):
        """Should track successful Anthropic calls."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(
                200,
                json={"tracked": 1, "total_cost": 0.002, "total_tokens": 150, "ids": ["id-1"]},
            )
        )

        wrapped_client = wrap_anthropic(mock_anthropic_client, diagnyx_client)

        result = wrapped_client.messages.create(
            model="claude-3-opus",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.id == "msg-123"
        assert diagnyx_client.buffer_size == 1

    def test_wrap_anthropic_tracks_error_call(self, diagnyx_client, mock_api):
        """Should track Anthropic errors."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(200, json={"tracked": 1})
        )

        class FailingAnthropic:
            class messages:
                @staticmethod
                def create(**kwargs):
                    raise Exception("API Error")

        wrapped_client = wrap_anthropic(FailingAnthropic(), diagnyx_client)

        with pytest.raises(Exception, match="API Error"):
            wrapped_client.messages.create(model="claude-3-opus", messages=[])

        assert diagnyx_client.buffer_size == 1

    def test_wrap_anthropic_with_environment(
        self, diagnyx_client, mock_anthropic_client, mock_api
    ):
        """Should include environment in tracked data."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(200, json={"tracked": 1})
        )

        wrapped_client = wrap_anthropic(
            mock_anthropic_client, diagnyx_client, environment="production"
        )

        wrapped_client.messages.create(
            model="claude-3-opus",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert diagnyx_client.buffer_size == 1


class TestTrackWithTiming:
    """Tests for track_with_timing decorator."""

    def test_track_with_timing_success(self, diagnyx_client, mock_api):
        """Should track function execution with timing."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(200, json={"tracked": 1})
        )

        @track_with_timing(diagnyx_client, LLMProvider.OPENAI, "gpt-4")
        def my_llm_call():
            return "result"

        result = my_llm_call()

        assert result == "result"
        assert diagnyx_client.buffer_size == 1

    def test_track_with_timing_error(self, diagnyx_client, mock_api):
        """Should track errors with timing."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(200, json={"tracked": 1})
        )

        @track_with_timing(diagnyx_client, LLMProvider.OPENAI, "gpt-4")
        def failing_call():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_call()

        assert diagnyx_client.buffer_size == 1

    def test_track_with_timing_extracts_usage(self, diagnyx_client, mock_api):
        """Should extract usage from result if available."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(200, json={"tracked": 1})
        )

        class MockResult:
            class usage:
                prompt_tokens = 100
                completion_tokens = 50

        @track_with_timing(diagnyx_client, LLMProvider.OPENAI, "gpt-4")
        def call_with_usage():
            return MockResult()

        result = call_with_usage()

        assert diagnyx_client.buffer_size == 1


class TestExtractOpenAIPrompt:
    """Tests for _extract_openai_prompt helper."""

    def test_extract_simple_messages(self):
        """Should extract simple message content."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello!"},
        ]

        result = _extract_openai_prompt(messages)

        assert "[system]: You are helpful." in result
        assert "[user]: Hello!" in result

    def test_extract_content_blocks(self):
        """Should handle content block format."""
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Describe this image"}],
            }
        ]

        result = _extract_openai_prompt(messages)

        assert "Describe this image" in result

    def test_truncates_long_content(self):
        """Should truncate content that exceeds max_length."""
        messages = [{"role": "user", "content": "a" * 20000}]

        result = _extract_openai_prompt(messages, max_length=100)

        assert len(result) <= 120  # Some overhead for role prefix
        assert "[truncated]" in result

    def test_returns_none_for_empty(self):
        """Should return None for empty messages."""
        assert _extract_openai_prompt(None) is None
        assert _extract_openai_prompt([]) is None


class TestExtractOpenAIResponse:
    """Tests for _extract_openai_response helper."""

    def test_extract_response_content(self):
        """Should extract response content from completion."""

        class MockMessage:
            content = "Hello! I'm here to help."

        class MockChoice:
            message = MockMessage()

        class MockResponse:
            choices = [MockChoice()]

        result = _extract_openai_response(MockResponse())

        assert result == "Hello! I'm here to help."

    def test_returns_none_for_no_choices(self):
        """Should return None when no choices."""

        class MockResponse:
            choices = []

        assert _extract_openai_response(MockResponse()) is None


class TestExtractAnthropicPrompt:
    """Tests for _extract_anthropic_prompt helper."""

    def test_extract_with_system(self):
        """Should extract system and messages."""
        system = "You are Claude."
        messages = [{"role": "user", "content": "Hello!"}]

        result = _extract_anthropic_prompt(system, messages)

        assert "[system]: You are Claude." in result
        assert "[user]: Hello!" in result

    def test_extract_without_system(self):
        """Should work without system prompt."""
        messages = [{"role": "user", "content": "Hello!"}]

        result = _extract_anthropic_prompt(None, messages)

        assert "[user]: Hello!" in result
        assert "[system]" not in result

    def test_returns_none_for_empty(self):
        """Should return None when no content."""
        assert _extract_anthropic_prompt(None, None) is None
        assert _extract_anthropic_prompt(None, []) is None


class TestExtractAnthropicResponse:
    """Tests for _extract_anthropic_response helper."""

    def test_extract_text_content(self):
        """Should extract text content blocks."""

        class MockBlock:
            type = "text"
            text = "Hello! How can I help?"

        class MockResponse:
            content = [MockBlock()]

        result = _extract_anthropic_response(MockResponse())

        assert result == "Hello! How can I help?"

    def test_returns_none_for_empty(self):
        """Should return None when no content."""

        class MockResponse:
            content = []

        assert _extract_anthropic_response(MockResponse()) is None
