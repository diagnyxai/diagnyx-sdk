"""LangChain callback handler for Diagnyx cost tracking and tracing."""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from uuid import UUID

from ..types import CallStatus, LLMCallData, LLMProvider

if TYPE_CHECKING:
    from ..client import Diagnyx

# Model to provider mapping
MODEL_PROVIDER_MAP: Dict[str, LLMProvider] = {
    "gpt-": LLMProvider.OPENAI,
    "o1-": LLMProvider.OPENAI,
    "claude-": LLMProvider.ANTHROPIC,
    "gemini-": LLMProvider.GOOGLE,
    "command": LLMProvider.COHERE,
    "mistral": LLMProvider.MISTRAL,
    "mixtral": LLMProvider.MISTRAL,
    "llama": LLMProvider.GROQ,
    "groq": LLMProvider.GROQ,
}


def _detect_provider(model: str) -> LLMProvider:
    """Detect the LLM provider from the model name."""
    model_lower = model.lower()
    for prefix, provider in MODEL_PROVIDER_MAP.items():
        if model_lower.startswith(prefix):
            return provider
    return LLMProvider.CUSTOM


def _extract_token_usage(
    response: Any,
) -> tuple[int, int]:
    """Extract token usage from LangChain LLMResult.

    Args:
        response: LangChain LLMResult object

    Returns:
        Tuple of (input_tokens, output_tokens)
    """
    input_tokens = 0
    output_tokens = 0

    # Try to get from llm_output
    llm_output = getattr(response, "llm_output", None) or {}

    # OpenAI style token usage
    token_usage = llm_output.get("token_usage", {})
    if token_usage:
        input_tokens = token_usage.get("prompt_tokens", 0)
        output_tokens = token_usage.get("completion_tokens", 0)
        return input_tokens, output_tokens

    # Anthropic style
    usage = llm_output.get("usage", {})
    if usage:
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        return input_tokens, output_tokens

    # Try generations
    generations = getattr(response, "generations", [])
    if generations:
        for gen_list in generations:
            for gen in gen_list:
                gen_info = getattr(gen, "generation_info", {}) or {}
                if "finish_reason" in gen_info:
                    # Estimate tokens from text length if no usage info
                    text = getattr(gen, "text", "")
                    output_tokens += len(text) // 4  # Rough estimate

    return input_tokens, output_tokens


def _extract_model_name(
    serialized: Dict[str, Any],
    kwargs: Dict[str, Any],
) -> str:
    """Extract model name from serialized data or kwargs."""
    # Try kwargs first (invocation params)
    invocation_params = kwargs.get("invocation_params", {})
    if "model" in invocation_params:
        return invocation_params["model"]
    if "model_name" in invocation_params:
        return invocation_params["model_name"]

    # Try serialized data
    if "kwargs" in serialized:
        serialized_kwargs = serialized["kwargs"]
        if "model" in serialized_kwargs:
            return serialized_kwargs["model"]
        if "model_name" in serialized_kwargs:
            return serialized_kwargs["model_name"]

    # Try name from serialized
    if "name" in serialized:
        return serialized["name"]

    return "unknown"


class DiagnyxCallbackHandler:
    """LangChain callback handler for Diagnyx cost tracking and tracing.

    This handler automatically tracks LLM calls made through LangChain,
    capturing token usage, latency, and errors.

    Example:
        >>> from diagnyx import Diagnyx
        >>> from diagnyx.callbacks import DiagnyxCallbackHandler
        >>> from langchain_openai import ChatOpenAI
        >>>
        >>> dx = Diagnyx(api_key="dx_...")
        >>> handler = DiagnyxCallbackHandler(dx, project_id="my-project")
        >>>
        >>> llm = ChatOpenAI(model="gpt-4", callbacks=[handler])
        >>> response = llm.invoke("Hello, world!")

    Note:
        This class is designed to work with both sync and async LangChain operations.
        For async support, use the async callback methods (on_llm_start, etc.).
    """

    def __init__(
        self,
        diagnyx: "Diagnyx",
        project_id: Optional[str] = None,
        environment: Optional[str] = None,
        user_identifier: Optional[str] = None,
        capture_content: bool = False,
    ):
        """Initialize the Diagnyx LangChain callback handler.

        Args:
            diagnyx: Diagnyx client instance for tracking
            project_id: Optional project ID for categorizing calls
            environment: Optional environment name (production, staging, etc.)
            user_identifier: Optional user identifier for tracking
            capture_content: Whether to capture prompt/response content (default: False)
        """
        self.diagnyx = diagnyx
        self.project_id = project_id
        self.environment = environment
        self.user_identifier = user_identifier
        self.capture_content = capture_content
        self._call_starts: Dict[str, float] = {}
        self._call_metadata: Dict[str, Dict[str, Any]] = {}

    @property
    def raise_error(self) -> bool:
        """Whether to raise errors from callbacks."""
        return False

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Track LLM call start time.

        Args:
            serialized: Serialized LLM data
            prompts: List of prompts
            run_id: Unique run identifier
            parent_run_id: Parent run identifier if nested
            tags: Optional tags
            metadata: Optional metadata
            **kwargs: Additional arguments
        """
        run_id_str = str(run_id)
        self._call_starts[run_id_str] = time.time()

        # Store metadata for later use
        self._call_metadata[run_id_str] = {
            "serialized": serialized,
            "prompts": prompts,
            "tags": tags,
            "metadata": metadata,
            "kwargs": kwargs,
        }

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Track chat model call start time.

        Args:
            serialized: Serialized chat model data
            messages: List of message lists
            run_id: Unique run identifier
            parent_run_id: Parent run identifier if nested
            tags: Optional tags
            metadata: Optional metadata
            **kwargs: Additional arguments
        """
        run_id_str = str(run_id)
        self._call_starts[run_id_str] = time.time()

        # Convert messages to prompts for storage
        prompts = []
        for msg_list in messages:
            prompt_parts = []
            for msg in msg_list:
                if hasattr(msg, "content"):
                    content = msg.content
                    role = getattr(msg, "type", "unknown")
                    prompt_parts.append(f"[{role}]: {content}")
                elif isinstance(msg, dict):
                    content = msg.get("content", "")
                    role = msg.get("role", msg.get("type", "unknown"))
                    prompt_parts.append(f"[{role}]: {content}")
            prompts.append("\n".join(prompt_parts))

        self._call_metadata[run_id_str] = {
            "serialized": serialized,
            "prompts": prompts,
            "messages": messages,
            "tags": tags,
            "metadata": metadata,
            "kwargs": kwargs,
        }

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Track successful LLM completion with tokens and cost.

        Args:
            response: LangChain LLMResult
            run_id: Unique run identifier
            parent_run_id: Parent run identifier if nested
            **kwargs: Additional arguments
        """
        run_id_str = str(run_id)
        start_time = self._call_starts.pop(run_id_str, None)
        call_metadata = self._call_metadata.pop(run_id_str, {})

        latency_ms = int((time.time() - start_time) * 1000) if start_time else None

        # Extract model name
        serialized = call_metadata.get("serialized", {})
        model = _extract_model_name(serialized, call_metadata.get("kwargs", {}))

        # Try to get model from llm_output
        llm_output = getattr(response, "llm_output", None) or {}
        if "model_name" in llm_output:
            model = llm_output["model_name"]
        elif "model" in llm_output:
            model = llm_output["model"]

        # Detect provider
        provider = _detect_provider(model)

        # Extract token usage
        input_tokens, output_tokens = _extract_token_usage(response)

        # Extract content if enabled
        full_prompt = None
        full_response = None
        if self.capture_content or self.diagnyx.config.capture_full_content:
            prompts = call_metadata.get("prompts", [])
            if prompts:
                full_prompt = "\n---\n".join(prompts)
                if len(full_prompt) > self.diagnyx.config.content_max_length:
                    full_prompt = (
                        full_prompt[: self.diagnyx.config.content_max_length]
                        + "... [truncated]"
                    )

            # Extract response text
            generations = getattr(response, "generations", [])
            if generations:
                response_parts = []
                for gen_list in generations:
                    for gen in gen_list:
                        text = getattr(gen, "text", "")
                        if text:
                            response_parts.append(text)
                        # Try message content for chat models
                        message = getattr(gen, "message", None)
                        if message:
                            content = getattr(message, "content", "")
                            if content:
                                response_parts.append(content)
                full_response = "\n".join(response_parts)
                if len(full_response) > self.diagnyx.config.content_max_length:
                    full_response = (
                        full_response[: self.diagnyx.config.content_max_length]
                        + "... [truncated]"
                    )

        call_data = LLMCallData(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            status=CallStatus.SUCCESS,
            latency_ms=latency_ms,
            project_id=self.project_id,
            environment=self.environment,
            user_identifier=self.user_identifier,
            timestamp=datetime.utcnow(),
            full_prompt=full_prompt,
            full_response=full_response,
        )
        self.diagnyx.track_call(call_data)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Track LLM errors.

        Args:
            error: The exception that occurred
            run_id: Unique run identifier
            parent_run_id: Parent run identifier if nested
            **kwargs: Additional arguments
        """
        run_id_str = str(run_id)
        start_time = self._call_starts.pop(run_id_str, None)
        call_metadata = self._call_metadata.pop(run_id_str, {})

        latency_ms = int((time.time() - start_time) * 1000) if start_time else None

        # Extract model name
        serialized = call_metadata.get("serialized", {})
        model = _extract_model_name(serialized, call_metadata.get("kwargs", {}))

        # Detect provider
        provider = _detect_provider(model)

        # Extract error details
        error_message = str(error)
        error_code = getattr(error, "code", None) or getattr(error, "status_code", None)
        if error_code:
            error_code = str(error_code)

        call_data = LLMCallData(
            provider=provider,
            model=model,
            input_tokens=0,
            output_tokens=0,
            status=CallStatus.ERROR,
            latency_ms=latency_ms,
            error_code=error_code,
            error_message=error_message[:500] if error_message else None,
            project_id=self.project_id,
            environment=self.environment,
            user_identifier=self.user_identifier,
            timestamp=datetime.utcnow(),
        )
        self.diagnyx.track_call(call_data)

    # Chain callbacks (for tracing chain executions)
    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain starts. Currently a no-op for cost tracking."""
        pass

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain ends. Currently a no-op for cost tracking."""
        pass

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain errors. Currently a no-op for cost tracking."""
        pass

    # Tool callbacks (for future agentic tracing)
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts. Currently a no-op for cost tracking."""
        pass

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool ends. Currently a no-op for cost tracking."""
        pass

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool errors. Currently a no-op for cost tracking."""
        pass

    # Text callbacks
    def on_text(
        self,
        text: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when text is streamed. Currently a no-op."""
        pass

    # Retry callback
    def on_retry(
        self,
        retry_state: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called on retry. Currently a no-op."""
        pass
