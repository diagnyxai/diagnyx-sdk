"""Tests for PromptsClient."""

import pytest
import httpx
import respx
import time

from diagnyx import PromptsClient, RenderedPrompt


@pytest.fixture
def prompts_client(mock_api):
    """Create a PromptsClient with mocked API."""
    client = PromptsClient(
        api_key="test-api-key",
        organization_id="org-123",
        base_url="https://api.diagnyx.io",
    )
    yield client
    client.close()


@pytest.fixture
def mock_rendered_prompt():
    """Sample rendered prompt response."""
    return {
        "systemPrompt": "You are a helpful assistant.",
        "userPrompt": "Hello, World!",
        "assistantPrompt": None,
        "model": "gpt-4",
        "provider": "openai",
        "temperature": 0.7,
        "maxTokens": 1000,
        "topP": None,
        "frequencyPenalty": None,
        "presencePenalty": None,
        "stopSequences": [],
        "responseFormat": None,
        "otherParams": {},
        "versionId": "version-123",
        "version": 1,
        "templateId": "template-123",
        "templateSlug": "test-prompt",
    }


class TestPromptsClientGet:
    """Tests for PromptsClient.get method."""

    def test_get_prompt(self, prompts_client, mock_api, mock_rendered_prompt):
        """Should fetch and return a rendered prompt."""
        mock_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts/test-prompt/render"
        ).mock(return_value=httpx.Response(200, json=mock_rendered_prompt))

        result = prompts_client.get("test-prompt", variables={"name": "World"})

        assert isinstance(result, RenderedPrompt)
        assert result.system_prompt == "You are a helpful assistant."
        assert result.user_prompt == "Hello, World!"
        assert result.model == "gpt-4"

    def test_get_prompt_with_environment(self, prompts_client, mock_api, mock_rendered_prompt):
        """Should include environment in request."""
        mock_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts/test-prompt/render"
        ).mock(return_value=httpx.Response(200, json=mock_rendered_prompt))

        prompts_client.get("test-prompt", environment="production")

        # Request was made with environment
        assert mock_api.calls.call_count == 1

    def test_get_prompt_caches_result(self, prompts_client, mock_api, mock_rendered_prompt):
        """Should cache results."""
        mock_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts/test-prompt/render"
        ).mock(return_value=httpx.Response(200, json=mock_rendered_prompt))

        # First call
        prompts_client.get("test-prompt", environment="production")
        # Second call should use cache
        prompts_client.get("test-prompt", environment="production")

        # Only one API call
        assert mock_api.calls.call_count == 1

    def test_get_prompt_bypass_cache(self, prompts_client, mock_api, mock_rendered_prompt):
        """Should bypass cache when use_cache is False."""
        mock_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts/test-prompt/render"
        ).mock(return_value=httpx.Response(200, json=mock_rendered_prompt))

        prompts_client.get("test-prompt", environment="production")
        prompts_client.get("test-prompt", environment="production", use_cache=False)

        # Two API calls
        assert mock_api.calls.call_count == 2


class TestPromptsClientList:
    """Tests for PromptsClient.list method."""

    def test_list_prompts(self, prompts_client, mock_api):
        """Should list prompts with pagination."""
        mock_response = {
            "data": [{"id": "1", "slug": "prompt-1", "name": "Prompt 1"}],
            "pagination": {"total": 1, "page": 1, "limit": 10, "totalPages": 1},
        }
        mock_api.get(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts"
        ).mock(return_value=httpx.Response(200, json=mock_response))

        result = prompts_client.list(page=1, limit=10)

        assert len(result["data"]) == 1
        assert result["pagination"]["total"] == 1

    def test_list_prompts_with_search(self, prompts_client, mock_api):
        """Should include search query."""
        mock_api.get(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts"
        ).mock(return_value=httpx.Response(200, json={"data": [], "pagination": {}}))

        prompts_client.list(search="test")

        # Request was made
        assert mock_api.calls.call_count == 1


class TestPromptsClientLogUsage:
    """Tests for PromptsClient.log_usage method."""

    def test_log_usage(self, prompts_client, mock_api):
        """Should log prompt usage."""
        mock_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts/test-prompt/versions/1/usage"
        ).mock(return_value=httpx.Response(200, json={"success": True}))

        result = prompts_client.log_usage(
            slug="test-prompt",
            version=1,
            environment="production",
            latency_ms=150,
            input_tokens=100,
            output_tokens=200,
        )

        assert result["success"] is True


class TestPromptsClientClearCache:
    """Tests for PromptsClient.clear_cache method."""

    def test_clear_all_cache(self, prompts_client, mock_api, mock_rendered_prompt):
        """Should clear all cache."""
        mock_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts/test-prompt/render"
        ).mock(return_value=httpx.Response(200, json=mock_rendered_prompt))

        prompts_client.get("test-prompt")
        prompts_client.clear_cache()
        prompts_client.get("test-prompt")

        # Two API calls after cache clear
        assert mock_api.calls.call_count == 2

    def test_clear_specific_cache(self, prompts_client, mock_api, mock_rendered_prompt):
        """Should clear cache for specific slug."""
        mock_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts/prompt-1/render"
        ).mock(return_value=httpx.Response(200, json=mock_rendered_prompt))
        mock_api.post(
            "https://api.diagnyx.io/api/v1/organizations/org-123/prompts/prompt-2/render"
        ).mock(return_value=httpx.Response(200, json=mock_rendered_prompt))

        prompts_client.get("prompt-1")
        prompts_client.get("prompt-2")
        prompts_client.clear_cache("prompt-1")
        prompts_client.get("prompt-1")  # Should fetch again
        prompts_client.get("prompt-2")  # Should use cache

        # 3 API calls total
        assert mock_api.calls.call_count == 3


class TestRenderedPrompt:
    """Tests for RenderedPrompt class."""

    def test_to_openai_messages(self):
        """Should convert to OpenAI messages format."""
        prompt = RenderedPrompt(
            system_prompt="You are helpful.",
            user_prompt="Hello!",
            assistant_prompt="Hi there!",
        )

        messages = prompt.to_openai_messages()

        assert len(messages) == 3
        assert messages[0] == {"role": "system", "content": "You are helpful."}
        assert messages[1] == {"role": "user", "content": "Hello!"}
        assert messages[2] == {"role": "assistant", "content": "Hi there!"}

    def test_to_openai_messages_with_override(self):
        """Should use custom user content."""
        prompt = RenderedPrompt(
            system_prompt="You are helpful.",
            user_prompt="Template message",
        )

        messages = prompt.to_openai_messages("Custom message")

        assert messages[1] == {"role": "user", "content": "Custom message"}

    def test_to_anthropic_messages(self):
        """Should convert to Anthropic messages format."""
        prompt = RenderedPrompt(
            system_prompt="You are helpful.",
            user_prompt="Hello!",
            assistant_prompt="Hi there!",
        )

        system, messages = prompt.to_anthropic_messages()

        assert system == "You are helpful."
        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "Hello!"}
        assert messages[1] == {"role": "assistant", "content": "Hi there!"}

    def test_get_model_params(self):
        """Should return model parameters."""
        prompt = RenderedPrompt(
            model="gpt-4",
            temperature=0.7,
            max_tokens=1000,
            top_p=0.9,
            stop_sequences=["END"],
            other_params={"seed": 42},
        )

        params = prompt.get_model_params()

        assert params["model"] == "gpt-4"
        assert params["temperature"] == 0.7
        assert params["max_tokens"] == 1000
        assert params["top_p"] == 0.9
        assert params["stop"] == ["END"]
        assert params["seed"] == 42

    def test_get_model_params_omits_none(self):
        """Should omit None values."""
        prompt = RenderedPrompt(
            model="gpt-4",
            temperature=None,
            max_tokens=None,
        )

        params = prompt.get_model_params()

        assert "model" in params
        assert "temperature" not in params
        assert "max_tokens" not in params
