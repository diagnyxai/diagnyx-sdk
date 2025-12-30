"""Tests for Diagnyx client."""

import pytest
import httpx
import respx
import time
from datetime import datetime

from diagnyx import Diagnyx, LLMCallData, LLMProvider, CallStatus


class TestDiagnyxInit:
    """Tests for Diagnyx client initialization."""

    def test_init_with_required_params(self):
        """Should initialize with just API key."""
        client = Diagnyx(api_key="test-key")
        assert client.config.api_key == "test-key"
        assert client.config.base_url == "https://api.diagnyx.io"
        client.shutdown()

    def test_init_with_custom_params(self):
        """Should initialize with custom parameters."""
        client = Diagnyx(
            api_key="test-key",
            base_url="https://custom.api.com",
            batch_size=50,
            flush_interval_ms=10000,
            max_retries=5,
            debug=True,
        )
        assert client.config.api_key == "test-key"
        assert client.config.base_url == "https://custom.api.com"
        assert client.config.batch_size == 50
        assert client.config.flush_interval_ms == 10000
        assert client.config.max_retries == 5
        assert client.config.debug is True
        client.shutdown()

    def test_init_without_api_key_raises_error(self):
        """Should raise ValueError when api_key is missing."""
        with pytest.raises(ValueError, match="api_key is required"):
            Diagnyx(api_key="")

    def test_context_manager(self, mock_api):
        """Should work as a context manager."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(200, json={"tracked": 0})
        )

        with Diagnyx(api_key="test-key") as client:
            assert client.config.api_key == "test-key"


class TestTrackCall:
    """Tests for track_call method."""

    def test_track_single_call(self, diagnyx_client, sample_call_data):
        """Should add call to buffer."""
        diagnyx_client.track_call(sample_call_data)
        assert diagnyx_client.buffer_size == 1

    def test_track_call_sets_timestamp_if_missing(self, diagnyx_client):
        """Should set timestamp if not provided."""
        call_data = LLMCallData(
            provider=LLMProvider.OPENAI,
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            status=CallStatus.SUCCESS,
        )
        diagnyx_client.track_call(call_data)
        assert call_data.timestamp is not None

    def test_track_call_auto_flushes_on_batch_size(self, diagnyx_client, mock_api, sample_call_data):
        """Should auto-flush when batch size is reached."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(
                200,
                json={"tracked": 10, "total_cost": 0.01, "total_tokens": 1000, "ids": []},
            )
        )

        # Track calls up to batch_size
        for _ in range(10):
            diagnyx_client.track_call(sample_call_data)

        # Buffer should be empty after auto-flush
        assert diagnyx_client.buffer_size == 0


class TestTrackCalls:
    """Tests for track_calls method."""

    def test_track_multiple_calls(self, diagnyx_client, sample_call_data):
        """Should add multiple calls to buffer."""
        calls = [sample_call_data for _ in range(5)]
        diagnyx_client.track_calls(calls)
        assert diagnyx_client.buffer_size == 5


class TestFlush:
    """Tests for flush method."""

    def test_flush_sends_batch(self, diagnyx_client, mock_api, sample_call_data):
        """Should send batch to API."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(
                200,
                json={"tracked": 1, "total_cost": 0.001, "total_tokens": 150, "ids": ["id-1"]},
            )
        )

        diagnyx_client.track_call(sample_call_data)
        result = diagnyx_client.flush()

        assert result is not None
        assert result.tracked == 1
        assert result.total_tokens == 150
        assert diagnyx_client.buffer_size == 0

    def test_flush_empty_buffer_returns_none(self, diagnyx_client):
        """Should return None when buffer is empty."""
        result = diagnyx_client.flush()
        assert result is None

    def test_flush_restores_buffer_on_error(self, diagnyx_client, mock_api, sample_call_data):
        """Should restore buffer on API error."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(500, json={"error": "Server error"})
        )

        diagnyx_client.track_call(sample_call_data)

        with pytest.raises(Exception):
            diagnyx_client.flush()

        # Buffer should be restored
        assert diagnyx_client.buffer_size == 1


class TestRetry:
    """Tests for retry logic."""

    def test_retry_on_failure(self, mock_api):
        """Should retry on API failure."""
        # First call fails, second succeeds
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            side_effect=[
                httpx.Response(500, json={"error": "Server error"}),
                httpx.Response(200, json={"tracked": 1, "total_cost": 0, "total_tokens": 100, "ids": []}),
            ]
        )

        client = Diagnyx(
            api_key="test-key",
            max_retries=3,
            flush_interval_ms=60000,
        )

        call_data = LLMCallData(
            provider=LLMProvider.OPENAI,
            model="gpt-4",
            input_tokens=50,
            output_tokens=50,
            status=CallStatus.SUCCESS,
        )
        client.track_call(call_data)
        result = client.flush()

        assert result is not None
        assert result.tracked == 1
        client.shutdown()

    def test_max_retries_exceeded(self, mock_api):
        """Should raise exception after max retries."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(500, json={"error": "Server error"})
        )

        client = Diagnyx(
            api_key="test-key",
            max_retries=2,
            flush_interval_ms=60000,
        )

        call_data = LLMCallData(
            provider=LLMProvider.OPENAI,
            model="gpt-4",
            input_tokens=50,
            output_tokens=50,
            status=CallStatus.SUCCESS,
        )
        client.track_call(call_data)

        with pytest.raises(Exception):
            client.flush()

        client.shutdown()


class TestShutdown:
    """Tests for shutdown method."""

    def test_shutdown_flushes_remaining_calls(self, mock_api, sample_call_data):
        """Should flush remaining calls on shutdown."""
        mock_api.post("https://api.diagnyx.io/api/v1/ingest/llm/batch").mock(
            return_value=httpx.Response(200, json={"tracked": 1, "total_cost": 0, "total_tokens": 100, "ids": []})
        )

        client = Diagnyx(api_key="test-key", flush_interval_ms=60000)
        client.track_call(sample_call_data)
        client.shutdown()

        assert client.buffer_size == 0


class TestTracer:
    """Tests for tracer functionality."""

    def test_get_tracer(self, diagnyx_client):
        """Should return a tracer instance."""
        tracer = diagnyx_client.tracer("org-123")
        assert tracer is not None
        assert tracer._organization_id == "org-123"

    def test_tracer_caching(self, diagnyx_client):
        """Should return same tracer for same org."""
        tracer1 = diagnyx_client.tracer("org-123")
        tracer2 = diagnyx_client.tracer("org-123")
        assert tracer1 is tracer2

    def test_tracer_different_environments(self, diagnyx_client):
        """Should return different tracers for different environments."""
        tracer1 = diagnyx_client.tracer("org-123", environment="production")
        tracer2 = diagnyx_client.tracer("org-123", environment="staging")
        assert tracer1 is not tracer2


class TestPrompts:
    """Tests for prompts client."""

    def test_get_prompts_client(self, diagnyx_client):
        """Should return a prompts client."""
        prompts = diagnyx_client.prompts("org-123")
        assert prompts is not None

    def test_prompts_client_caching(self, diagnyx_client):
        """Should return same prompts client for same org."""
        prompts1 = diagnyx_client.prompts("org-123")
        prompts2 = diagnyx_client.prompts("org-123")
        assert prompts1 is prompts2
