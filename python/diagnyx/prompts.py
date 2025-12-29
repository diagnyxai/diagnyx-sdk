"""Diagnyx Prompt Management SDK."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class PromptVariable:
    """Definition of a variable in a prompt template."""

    name: str
    type: str  # string, number, boolean, array, object
    required: bool = True
    default: Any = None
    description: Optional[str] = None


@dataclass
class RenderedPrompt:
    """A rendered prompt ready for use with an LLM."""

    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    assistant_prompt: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop_sequences: List[str] = field(default_factory=list)
    response_format: Optional[Dict[str, Any]] = None
    other_params: Dict[str, Any] = field(default_factory=dict)
    version_id: Optional[str] = None
    version: Optional[int] = None
    template_id: Optional[str] = None
    template_slug: Optional[str] = None

    def to_openai_messages(
        self,
        user_content: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Convert to OpenAI messages format.

        Args:
            user_content: Override user message content (if not using template)

        Returns:
            List of message dicts for OpenAI API
        """
        messages = []

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        if user_content:
            messages.append({"role": "user", "content": user_content})
        elif self.user_prompt:
            messages.append({"role": "user", "content": self.user_prompt})

        if self.assistant_prompt:
            messages.append({"role": "assistant", "content": self.assistant_prompt})

        return messages

    def to_anthropic_messages(
        self,
        user_content: Optional[str] = None,
    ) -> tuple[Optional[str], List[Dict[str, str]]]:
        """Convert to Anthropic messages format.

        Args:
            user_content: Override user message content (if not using template)

        Returns:
            Tuple of (system_prompt, messages) for Anthropic API
        """
        messages = []

        if user_content:
            messages.append({"role": "user", "content": user_content})
        elif self.user_prompt:
            messages.append({"role": "user", "content": self.user_prompt})

        if self.assistant_prompt:
            messages.append({"role": "assistant", "content": self.assistant_prompt})

        return self.system_prompt, messages

    def get_model_params(self) -> Dict[str, Any]:
        """Get model configuration parameters.

        Returns:
            Dict of model parameters (temperature, max_tokens, etc.)
        """
        params = {}

        if self.model:
            params["model"] = self.model
        if self.temperature is not None:
            params["temperature"] = self.temperature
        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            params["top_p"] = self.top_p
        if self.frequency_penalty is not None:
            params["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty is not None:
            params["presence_penalty"] = self.presence_penalty
        if self.stop_sequences:
            params["stop"] = self.stop_sequences
        if self.response_format:
            params["response_format"] = self.response_format

        params.update(self.other_params)
        return params


@dataclass
class PromptVersion:
    """A version of a prompt template."""

    id: str
    version: int
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    assistant_prompt: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    variables: List[PromptVariable] = field(default_factory=list)
    commit_message: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class PromptDeployment:
    """A deployment of a prompt version to an environment."""

    id: str
    environment: str
    version: PromptVersion
    deployed_at: Optional[datetime] = None


@dataclass
class PromptTemplate:
    """A prompt template in the registry."""

    id: str
    slug: str
    name: str
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    versions: List[PromptVersion] = field(default_factory=list)
    deployments: List[PromptDeployment] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PromptsClient:
    """Client for managing prompts with Diagnyx."""

    def __init__(
        self,
        api_key: str,
        organization_id: str,
        base_url: str = "https://api.diagnyx.io",
        max_retries: int = 3,
        debug: bool = False,
    ):
        """Initialize the Prompts client.

        Args:
            api_key: Diagnyx API key
            organization_id: Organization ID
            base_url: API base URL
            max_retries: Maximum retry attempts
            debug: Enable debug logging
        """
        self._api_key = api_key
        self._organization_id = organization_id
        self._base_url = base_url
        self._max_retries = max_retries
        self._debug = debug
        self._client = httpx.Client(timeout=30.0)
        self._cache: Dict[str, tuple[RenderedPrompt, float]] = {}
        self._cache_ttl = 300  # 5 minutes

    def get(
        self,
        slug: str,
        variables: Optional[Dict[str, Any]] = None,
        environment: Optional[str] = None,
        version: Optional[int] = None,
        use_cache: bool = True,
    ) -> RenderedPrompt:
        """Get and render a prompt template.

        Args:
            slug: Prompt template slug
            variables: Variables to substitute in the prompt
            environment: Environment to get deployment from (production, staging, development)
            version: Specific version number to get (overrides environment)
            use_cache: Whether to use cached prompt (default True)

        Returns:
            RenderedPrompt ready for use with LLM

        Example:
            >>> prompt = dx.prompts.get(
            ...     "summarize-article",
            ...     variables={"article": article_text, "max_words": 100},
            ...     environment="production"
            ... )
            >>> response = openai.chat.completions.create(
            ...     model=prompt.model or "gpt-4",
            ...     messages=prompt.to_openai_messages(),
            ...     **prompt.get_model_params()
            ... )
        """
        cache_key = f"{slug}:{environment or ''}:{version or ''}"

        if use_cache and cache_key in self._cache:
            cached, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                # Re-render with new variables
                return self._render_cached(cached, variables)

        payload = {
            "variables": variables or {},
        }
        if environment:
            payload["environment"] = environment
        if version:
            payload["version"] = version

        data = self._request(
            "POST",
            f"/api/v1/organizations/{self._organization_id}/prompts/{slug}/render",
            json=payload,
        )

        prompt = RenderedPrompt(
            system_prompt=data.get("systemPrompt"),
            user_prompt=data.get("userPrompt"),
            assistant_prompt=data.get("assistantPrompt"),
            model=data.get("model"),
            provider=data.get("provider"),
            temperature=data.get("temperature"),
            max_tokens=data.get("maxTokens"),
            top_p=data.get("topP"),
            frequency_penalty=data.get("frequencyPenalty"),
            presence_penalty=data.get("presencePenalty"),
            stop_sequences=data.get("stopSequences") or [],
            response_format=data.get("responseFormat"),
            other_params=data.get("otherParams") or {},
            version_id=data.get("versionId"),
            version=data.get("version"),
            template_id=data.get("templateId"),
            template_slug=data.get("templateSlug"),
        )

        # Cache the result
        self._cache[cache_key] = (prompt, time.time())

        return prompt

    def _render_cached(
        self,
        prompt: RenderedPrompt,
        variables: Optional[Dict[str, Any]],
    ) -> RenderedPrompt:
        """Re-render a cached prompt with new variables.

        Note: For cached prompts, variables were already substituted on the server.
        This method returns the cached prompt as-is. For fresh variable substitution,
        use use_cache=False.
        """
        return prompt

    def list(
        self,
        search: Optional[str] = None,
        tags: Optional[List[str]] = None,
        include_archived: bool = False,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """List prompt templates.

        Args:
            search: Search query
            tags: Filter by tags
            include_archived: Include archived prompts
            page: Page number
            limit: Items per page

        Returns:
            Dict with data and pagination
        """
        params = {
            "page": page,
            "limit": limit,
            "includeArchived": include_archived,
        }
        if search:
            params["search"] = search
        if tags:
            params["tags"] = ",".join(tags)

        return self._request(
            "GET",
            f"/api/v1/organizations/{self._organization_id}/prompts",
            params=params,
        )

    def get_template(self, slug: str) -> PromptTemplate:
        """Get a prompt template with all versions and deployments.

        Args:
            slug: Prompt template slug

        Returns:
            PromptTemplate object
        """
        data = self._request(
            "GET",
            f"/api/v1/organizations/{self._organization_id}/prompts/{slug}",
        )

        versions = [
            PromptVersion(
                id=v["id"],
                version=v["version"],
                system_prompt=v.get("systemPrompt"),
                user_prompt_template=v.get("userPromptTemplate"),
                assistant_prompt=v.get("assistantPrompt"),
                model=v.get("model"),
                provider=v.get("provider"),
                temperature=v.get("temperature"),
                max_tokens=v.get("maxTokens"),
                variables=[PromptVariable(**var) for var in (v.get("variables") or [])],
                commit_message=v.get("commitMessage"),
            )
            for v in data.get("versions", [])
        ]

        return PromptTemplate(
            id=data["id"],
            slug=data["slug"],
            name=data["name"],
            description=data.get("description"),
            tags=data.get("tags", []),
            versions=versions,
        )

    def log_usage(
        self,
        slug: str,
        version: int,
        environment: str,
        success: bool = True,
        variables: Optional[Dict[str, Any]] = None,
        latency_ms: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        cost_usd: Optional[float] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        variant_id: Optional[str] = None,
        feedback_score: Optional[int] = None,
        feedback_text: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log prompt usage for analytics.

        Args:
            slug: Prompt template slug
            version: Version number used
            environment: Environment (production, staging, development)
            success: Whether the call succeeded
            variables: Variables used in the prompt
            latency_ms: Response latency in milliseconds
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost_usd: Cost in USD
            user_id: End-user identifier
            request_id: Request correlation ID
            experiment_id: A/B test experiment ID
            variant_id: A/B test variant ID
            feedback_score: User feedback score (1-5)
            feedback_text: User feedback text
            error_message: Error message if failed

        Returns:
            Created usage log
        """
        payload: Dict[str, Any] = {
            "environment": environment,
            "success": success,
        }

        if variables:
            payload["variables"] = variables
        if latency_ms is not None:
            payload["latencyMs"] = latency_ms
        if input_tokens is not None:
            payload["inputTokens"] = input_tokens
        if output_tokens is not None:
            payload["outputTokens"] = output_tokens
        if cost_usd is not None:
            payload["costUsd"] = cost_usd
        if user_id:
            payload["userId"] = user_id
        if request_id:
            payload["requestId"] = request_id
        if experiment_id:
            payload["experimentId"] = experiment_id
        if variant_id:
            payload["variantId"] = variant_id
        if feedback_score is not None:
            payload["feedbackScore"] = feedback_score
        if feedback_text:
            payload["feedbackText"] = feedback_text
        if error_message:
            payload["errorMessage"] = error_message

        return self._request(
            "POST",
            f"/api/v1/organizations/{self._organization_id}/prompts/{slug}/versions/{version}/usage",
            json=payload,
        )

    def select_experiment_variant(
        self,
        slug: str,
        experiment_id: str,
    ) -> Dict[str, Any]:
        """Select a variant for an A/B test experiment.

        Args:
            slug: Prompt template slug
            experiment_id: Experiment ID

        Returns:
            Selected variant info with version details
        """
        return self._request(
            "POST",
            f"/api/v1/organizations/{self._organization_id}/prompts/{slug}/experiments/{experiment_id}/select-variant",
        )

    def record_conversion(
        self,
        slug: str,
        experiment_id: str,
        variant_id: str,
        latency_ms: Optional[int] = None,
        tokens: Optional[int] = None,
        cost_usd: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Record a conversion for an A/B test variant.

        Args:
            slug: Prompt template slug
            experiment_id: Experiment ID
            variant_id: Variant ID
            latency_ms: Response latency
            tokens: Total tokens used
            cost_usd: Cost in USD

        Returns:
            Updated variant stats
        """
        payload = {}
        if latency_ms is not None:
            payload["latencyMs"] = latency_ms
        if tokens is not None:
            payload["tokens"] = tokens
        if cost_usd is not None:
            payload["costUsd"] = cost_usd

        return self._request(
            "POST",
            f"/api/v1/organizations/{self._organization_id}/prompts/{slug}/experiments/{experiment_id}/variants/{variant_id}/convert",
            json=payload,
        )

    def clear_cache(self, slug: Optional[str] = None) -> None:
        """Clear the prompt cache.

        Args:
            slug: Optional slug to clear specific prompt cache, or None to clear all
        """
        if slug:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{slug}:")]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            self._cache.clear()

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the API."""
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                response = self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json,
                    params=params,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._api_key}",
                    },
                )
                response.raise_for_status()
                return response.json()

            except Exception as e:
                last_error = e
                self._log(f"Request attempt {attempt + 1} failed: {e}")
                if attempt < self._max_retries - 1:
                    time.sleep(2**attempt)

        raise last_error or Exception("Request failed")

    def _log(self, message: str) -> None:
        """Log a message if debug is enabled."""
        if self._debug:
            print(f"[Diagnyx.prompts] {message}")

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()
