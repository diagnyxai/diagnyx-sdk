"""Tests for LangChain callback handler."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from diagnyx import Diagnyx, DiagnyxCallbackHandler
from diagnyx.callbacks.langchain import _detect_provider, _extract_model_name, _extract_token_usage
from diagnyx.types import CallStatus, LLMCallData, LLMProvider


@pytest.fixture
def mock_diagnyx():
    """Create a mock Diagnyx client."""
    client = MagicMock(spec=Diagnyx)
    client.config = MagicMock()
    client.config.capture_full_content = False
    client.config.content_max_length = 10000
    return client


@pytest.fixture
def handler(mock_diagnyx):
    """Create a callback handler with mock client."""
    return DiagnyxCallbackHandler(
        diagnyx=mock_diagnyx,
        project_id="test-project",
        environment="test",
        user_identifier="test-user",
    )


class TestDetectProvider:
    """Tests for provider detection."""

    def test_detect_openai_gpt(self):
        assert _detect_provider("gpt-4") == LLMProvider.OPENAI
        assert _detect_provider("gpt-3.5-turbo") == LLMProvider.OPENAI
        assert _detect_provider("gpt-4o") == LLMProvider.OPENAI

    def test_detect_openai_o1(self):
        assert _detect_provider("o1-preview") == LLMProvider.OPENAI
        assert _detect_provider("o1-mini") == LLMProvider.OPENAI

    def test_detect_anthropic(self):
        assert _detect_provider("claude-3-opus") == LLMProvider.ANTHROPIC
        assert _detect_provider("claude-3-sonnet") == LLMProvider.ANTHROPIC
        assert _detect_provider("claude-2") == LLMProvider.ANTHROPIC

    def test_detect_google(self):
        assert _detect_provider("gemini-pro") == LLMProvider.GOOGLE
        assert _detect_provider("gemini-1.5-flash") == LLMProvider.GOOGLE

    def test_detect_mistral(self):
        assert _detect_provider("mistral-large") == LLMProvider.MISTRAL
        assert _detect_provider("mixtral-8x7b") == LLMProvider.MISTRAL

    def test_detect_custom(self):
        assert _detect_provider("unknown-model") == LLMProvider.CUSTOM
        assert _detect_provider("my-custom-llm") == LLMProvider.CUSTOM


class TestExtractModelName:
    """Tests for model name extraction."""

    def test_extract_from_invocation_params(self):
        serialized = {}
        kwargs = {"invocation_params": {"model": "gpt-4"}}
        assert _extract_model_name(serialized, kwargs) == "gpt-4"

    def test_extract_from_invocation_params_model_name(self):
        serialized = {}
        kwargs = {"invocation_params": {"model_name": "claude-3"}}
        assert _extract_model_name(serialized, kwargs) == "claude-3"

    def test_extract_from_serialized_kwargs(self):
        serialized = {"kwargs": {"model": "gpt-3.5-turbo"}}
        kwargs = {}
        assert _extract_model_name(serialized, kwargs) == "gpt-3.5-turbo"

    def test_extract_from_serialized_name(self):
        serialized = {"name": "ChatOpenAI"}
        kwargs = {}
        assert _extract_model_name(serialized, kwargs) == "ChatOpenAI"

    def test_unknown_model(self):
        serialized = {}
        kwargs = {}
        assert _extract_model_name(serialized, kwargs) == "unknown"


class TestExtractTokenUsage:
    """Tests for token usage extraction."""

    def test_extract_openai_style(self):
        response = MagicMock()
        response.llm_output = {
            "token_usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
            }
        }
        response.generations = []

        input_tokens, output_tokens = _extract_token_usage(response)
        assert input_tokens == 100
        assert output_tokens == 50

    def test_extract_anthropic_style(self):
        response = MagicMock()
        response.llm_output = {
            "usage": {
                "input_tokens": 80,
                "output_tokens": 40,
            }
        }
        response.generations = []

        input_tokens, output_tokens = _extract_token_usage(response)
        assert input_tokens == 80
        assert output_tokens == 40

    def test_extract_no_usage(self):
        response = MagicMock()
        response.llm_output = {}
        response.generations = []

        input_tokens, output_tokens = _extract_token_usage(response)
        assert input_tokens == 0
        assert output_tokens == 0


class TestDiagnyxCallbackHandler:
    """Tests for DiagnyxCallbackHandler."""

    def test_init(self, mock_diagnyx):
        handler = DiagnyxCallbackHandler(
            diagnyx=mock_diagnyx,
            project_id="proj-123",
            environment="production",
            user_identifier="user-456",
            capture_content=True,
        )

        assert handler.diagnyx == mock_diagnyx
        assert handler.project_id == "proj-123"
        assert handler.environment == "production"
        assert handler.user_identifier == "user-456"
        assert handler.capture_content is True

    def test_raise_error_property(self, handler):
        assert handler.raise_error is False

    def test_on_llm_start_records_time(self, handler):
        run_id = uuid4()

        handler.on_llm_start(
            serialized={"name": "ChatOpenAI"},
            prompts=["Hello"],
            run_id=run_id,
        )

        assert str(run_id) in handler._call_starts
        assert str(run_id) in handler._call_metadata

    def test_on_chat_model_start_records_time(self, handler):
        run_id = uuid4()
        messages = [[MagicMock(content="Hello", type="human")]]

        handler.on_chat_model_start(
            serialized={"name": "ChatOpenAI", "kwargs": {"model": "gpt-4"}},
            messages=messages,
            run_id=run_id,
        )

        assert str(run_id) in handler._call_starts
        assert str(run_id) in handler._call_metadata

    def test_on_llm_end_tracks_call(self, handler, mock_diagnyx):
        run_id = uuid4()

        # Simulate start
        handler.on_llm_start(
            serialized={"kwargs": {"model": "gpt-4"}},
            prompts=["Hello"],
            run_id=run_id,
        )

        # Simulate end
        response = MagicMock()
        response.llm_output = {
            "model_name": "gpt-4",
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
            }
        }
        response.generations = [[MagicMock(text="Hi there!")]]

        handler.on_llm_end(response=response, run_id=run_id)

        # Verify track_call was called
        mock_diagnyx.track_call.assert_called_once()
        call_data = mock_diagnyx.track_call.call_args[0][0]

        assert isinstance(call_data, LLMCallData)
        assert call_data.model == "gpt-4"
        assert call_data.provider == LLMProvider.OPENAI
        assert call_data.input_tokens == 10
        assert call_data.output_tokens == 20
        assert call_data.status == CallStatus.SUCCESS
        assert call_data.project_id == "test-project"
        assert call_data.environment == "test"
        assert call_data.user_identifier == "test-user"
        assert call_data.latency_ms is not None

    def test_on_llm_end_with_content_capture(self, mock_diagnyx):
        handler = DiagnyxCallbackHandler(
            diagnyx=mock_diagnyx,
            capture_content=True,
        )
        run_id = uuid4()

        # Simulate start
        handler.on_llm_start(
            serialized={"kwargs": {"model": "gpt-4"}},
            prompts=["Hello, how are you?"],
            run_id=run_id,
        )

        # Simulate end
        response = MagicMock()
        response.llm_output = {"model_name": "gpt-4", "token_usage": {"prompt_tokens": 5, "completion_tokens": 10}}
        gen = MagicMock()
        gen.text = "I'm doing well!"
        gen.message = None
        response.generations = [[gen]]

        handler.on_llm_end(response=response, run_id=run_id)

        call_data = mock_diagnyx.track_call.call_args[0][0]
        assert call_data.full_prompt == "Hello, how are you?"
        assert call_data.full_response == "I'm doing well!"

    def test_on_llm_error_tracks_error(self, handler, mock_diagnyx):
        run_id = uuid4()

        # Simulate start
        handler.on_llm_start(
            serialized={"kwargs": {"model": "gpt-4"}},
            prompts=["Hello"],
            run_id=run_id,
        )

        # Simulate error
        error = Exception("API rate limit exceeded")
        error.code = "rate_limit_error"

        handler.on_llm_error(error=error, run_id=run_id)

        # Verify track_call was called with error
        mock_diagnyx.track_call.assert_called_once()
        call_data = mock_diagnyx.track_call.call_args[0][0]

        assert isinstance(call_data, LLMCallData)
        assert call_data.status == CallStatus.ERROR
        assert call_data.error_message == "API rate limit exceeded"
        assert call_data.error_code == "rate_limit_error"
        assert call_data.input_tokens == 0
        assert call_data.output_tokens == 0

    def test_on_llm_end_without_start(self, handler, mock_diagnyx):
        """Test handling on_llm_end without a corresponding on_llm_start."""
        run_id = uuid4()

        response = MagicMock()
        response.llm_output = {"model_name": "gpt-4", "token_usage": {"prompt_tokens": 10, "completion_tokens": 20}}
        response.generations = []

        handler.on_llm_end(response=response, run_id=run_id)

        mock_diagnyx.track_call.assert_called_once()
        call_data = mock_diagnyx.track_call.call_args[0][0]
        assert call_data.latency_ms is None  # No start time recorded

    def test_chain_callbacks_are_noop(self, handler):
        """Test that chain callbacks don't raise errors."""
        run_id = uuid4()

        # These should not raise
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=run_id,
        )
        handler.on_chain_end(outputs={}, run_id=run_id)
        handler.on_chain_error(error=Exception("test"), run_id=run_id)

    def test_tool_callbacks_are_noop(self, handler):
        """Test that tool callbacks don't raise errors."""
        run_id = uuid4()

        # These should not raise
        handler.on_tool_start(
            serialized={},
            input_str="test",
            run_id=run_id,
        )
        handler.on_tool_end(output="test", run_id=run_id)
        handler.on_tool_error(error=Exception("test"), run_id=run_id)

    def test_text_callback_is_noop(self, handler):
        """Test that text callback doesn't raise errors."""
        run_id = uuid4()
        handler.on_text(text="streaming text", run_id=run_id)

    def test_retry_callback_is_noop(self, handler):
        """Test that retry callback doesn't raise errors."""
        run_id = uuid4()
        handler.on_retry(retry_state=MagicMock(), run_id=run_id)


class TestCallbackIntegration:
    """Integration-style tests for the callback handler."""

    def test_multiple_concurrent_calls(self, handler, mock_diagnyx):
        """Test handling multiple concurrent LLM calls."""
        run_id_1 = uuid4()
        run_id_2 = uuid4()

        # Start both calls
        handler.on_llm_start(
            serialized={"kwargs": {"model": "gpt-4"}},
            prompts=["First prompt"],
            run_id=run_id_1,
        )
        handler.on_llm_start(
            serialized={"kwargs": {"model": "claude-3"}},
            prompts=["Second prompt"],
            run_id=run_id_2,
        )

        # End in reverse order
        response_2 = MagicMock()
        response_2.llm_output = {"model_name": "claude-3", "token_usage": {"prompt_tokens": 5, "completion_tokens": 10}}
        response_2.generations = []
        handler.on_llm_end(response=response_2, run_id=run_id_2)

        response_1 = MagicMock()
        response_1.llm_output = {"model_name": "gpt-4", "token_usage": {"prompt_tokens": 8, "completion_tokens": 15}}
        response_1.generations = []
        handler.on_llm_end(response=response_1, run_id=run_id_1)

        # Verify both calls were tracked correctly
        assert mock_diagnyx.track_call.call_count == 2

        calls = [call[0][0] for call in mock_diagnyx.track_call.call_args_list]
        models = {call.model for call in calls}
        assert models == {"claude-3", "gpt-4"}

    def test_call_with_chat_messages(self, handler, mock_diagnyx):
        """Test tracking a call with chat-style messages."""
        run_id = uuid4()

        # Create mock messages
        human_msg = MagicMock()
        human_msg.content = "What is 2+2?"
        human_msg.type = "human"

        ai_msg = MagicMock()
        ai_msg.content = "2+2 equals 4."
        ai_msg.type = "ai"

        messages = [[human_msg]]

        handler.on_chat_model_start(
            serialized={"kwargs": {"model": "gpt-4"}},
            messages=messages,
            run_id=run_id,
        )

        response = MagicMock()
        response.llm_output = {"model_name": "gpt-4", "token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        gen = MagicMock()
        gen.text = ""
        gen.message = ai_msg
        response.generations = [[gen]]

        handler.on_llm_end(response=response, run_id=run_id)

        mock_diagnyx.track_call.assert_called_once()
        call_data = mock_diagnyx.track_call.call_args[0][0]
        assert call_data.model == "gpt-4"
        assert call_data.status == CallStatus.SUCCESS
