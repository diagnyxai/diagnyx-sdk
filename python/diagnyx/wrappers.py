"""Wrappers for popular LLM libraries."""

import functools
import json
import time
from datetime import datetime
from typing import Any, Callable, List, Optional, TypeVar, Union

from .client import Diagnyx
from .types import CallStatus, LLMCallData, LLMProvider

T = TypeVar("T")


def _extract_openai_prompt(
    messages: Optional[List[dict]], max_length: int = 10000
) -> Optional[str]:
    """Extract prompt content from OpenAI messages."""
    if not messages:
        return None

    parts = []
    for m in messages:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}]: {content}")
        elif isinstance(content, list):
            # Handle content blocks (images, text, etc.)
            text_parts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    text_parts.append(c.get("text", ""))
                else:
                    text_parts.append(json.dumps(c))
            parts.append(f"[{role}]: {''.join(text_parts)}")

    result = "\n".join(parts)
    if len(result) > max_length:
        return result[:max_length] + "... [truncated]"
    return result


def _extract_openai_response(result: Any, max_length: int = 10000) -> Optional[str]:
    """Extract response content from OpenAI completion."""
    try:
        choices = getattr(result, "choices", [])
        if not choices:
            return None
        message = getattr(choices[0], "message", None)
        if not message:
            return None
        content = getattr(message, "content", "") or ""
        if len(content) > max_length:
            return content[:max_length] + "... [truncated]"
        return content
    except Exception:
        return None


def _extract_anthropic_prompt(
    system: Optional[Union[str, List[dict]]],
    messages: Optional[List[dict]],
    max_length: int = 10000,
) -> Optional[str]:
    """Extract prompt content from Anthropic messages."""
    parts = []

    # Extract system prompt
    if system:
        if isinstance(system, str):
            parts.append(f"[system]: {system}")
        elif isinstance(system, list):
            system_text = "".join(
                s.get("text", "") if s.get("type") == "text" else json.dumps(s)
                for s in system
            )
            parts.append(f"[system]: {system_text}")

    # Extract messages
    if messages:
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, str):
                parts.append(f"[{role}]: {content}")
            elif isinstance(content, list):
                text_parts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text_parts.append(c.get("text", ""))
                    else:
                        text_parts.append(json.dumps(c))
                parts.append(f"[{role}]: {''.join(text_parts)}")

    if not parts:
        return None

    result = "\n".join(parts)
    if len(result) > max_length:
        return result[:max_length] + "... [truncated]"
    return result


def _extract_anthropic_response(result: Any, max_length: int = 10000) -> Optional[str]:
    """Extract response content from Anthropic message."""
    try:
        content = getattr(result, "content", [])
        if not content:
            return None

        parts = []
        for block in content:
            if hasattr(block, "type") and block.type == "text":
                parts.append(getattr(block, "text", ""))
            else:
                parts.append(str(block))

        response = "".join(parts)
        if len(response) > max_length:
            return response[:max_length] + "... [truncated]"
        return response
    except Exception:
        return None


def wrap_openai(
    client: Any,
    diagnyx: Diagnyx,
    project_id: Optional[str] = None,
    environment: Optional[str] = None,
    user_identifier: Optional[str] = None,
) -> Any:
    """Wrap an OpenAI client to automatically track calls.

    Args:
        client: OpenAI client instance
        diagnyx: Diagnyx client instance
        project_id: Optional project ID for tracking
        environment: Optional environment name
        user_identifier: Optional user identifier

    Returns:
        Wrapped client with automatic tracking
    """
    original_create = client.chat.completions.create

    @functools.wraps(original_create)
    def wrapped_create(*args, **kwargs):
        start_time = time.time()
        status = CallStatus.SUCCESS
        error_code = None
        error_message = None

        try:
            result = original_create(*args, **kwargs)
            latency_ms = int((time.time() - start_time) * 1000)

            model = kwargs.get("model", "unknown")
            usage = getattr(result, "usage", None)

            # Extract content if enabled
            full_prompt = None
            full_response = None
            if diagnyx.config.capture_full_content:
                messages = kwargs.get("messages")
                full_prompt = _extract_openai_prompt(
                    messages, diagnyx.config.content_max_length
                )
                full_response = _extract_openai_response(
                    result, diagnyx.config.content_max_length
                )

            if usage:
                call_data = LLMCallData(
                    provider=LLMProvider.OPENAI,
                    model=model,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    latency_ms=latency_ms,
                    status=status,
                    endpoint="/v1/chat/completions",
                    project_id=project_id,
                    environment=environment,
                    user_identifier=user_identifier,
                    timestamp=datetime.utcnow(),
                    full_prompt=full_prompt,
                    full_response=full_response,
                )
                diagnyx.track_call(call_data)

            return result

        except Exception as e:
            status = CallStatus.ERROR
            error_message = str(e)
            error_code = getattr(e, "code", None)

            latency_ms = int((time.time() - start_time) * 1000)
            model = kwargs.get("model", "unknown")

            call_data = LLMCallData(
                provider=LLMProvider.OPENAI,
                model=model,
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
                error_message=error_message,
                endpoint="/v1/chat/completions",
                project_id=project_id,
                environment=environment,
                user_identifier=user_identifier,
                timestamp=datetime.utcnow(),
            )
            diagnyx.track_call(call_data)
            raise

    client.chat.completions.create = wrapped_create
    return client


def wrap_anthropic(
    client: Any,
    diagnyx: Diagnyx,
    project_id: Optional[str] = None,
    environment: Optional[str] = None,
    user_identifier: Optional[str] = None,
) -> Any:
    """Wrap an Anthropic client to automatically track calls.

    Args:
        client: Anthropic client instance
        diagnyx: Diagnyx client instance
        project_id: Optional project ID for tracking
        environment: Optional environment name
        user_identifier: Optional user identifier

    Returns:
        Wrapped client with automatic tracking
    """
    original_create = client.messages.create

    @functools.wraps(original_create)
    def wrapped_create(*args, **kwargs):
        start_time = time.time()
        status = CallStatus.SUCCESS
        error_code = None
        error_message = None

        try:
            result = original_create(*args, **kwargs)
            latency_ms = int((time.time() - start_time) * 1000)

            model = kwargs.get("model", "unknown")
            usage = getattr(result, "usage", None)

            # Extract content if enabled
            full_prompt = None
            full_response = None
            if diagnyx.config.capture_full_content:
                system = kwargs.get("system")
                messages = kwargs.get("messages")
                full_prompt = _extract_anthropic_prompt(
                    system, messages, diagnyx.config.content_max_length
                )
                full_response = _extract_anthropic_response(
                    result, diagnyx.config.content_max_length
                )

            if usage:
                call_data = LLMCallData(
                    provider=LLMProvider.ANTHROPIC,
                    model=model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    latency_ms=latency_ms,
                    status=status,
                    endpoint="/v1/messages",
                    project_id=project_id,
                    environment=environment,
                    user_identifier=user_identifier,
                    timestamp=datetime.utcnow(),
                    full_prompt=full_prompt,
                    full_response=full_response,
                )
                diagnyx.track_call(call_data)

            return result

        except Exception as e:
            status = CallStatus.ERROR
            error_message = str(e)
            error_code = getattr(e, "code", None)

            latency_ms = int((time.time() - start_time) * 1000)
            model = kwargs.get("model", "unknown")

            call_data = LLMCallData(
                provider=LLMProvider.ANTHROPIC,
                model=model,
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
                error_message=error_message,
                endpoint="/v1/messages",
                project_id=project_id,
                environment=environment,
                user_identifier=user_identifier,
                timestamp=datetime.utcnow(),
            )
            diagnyx.track_call(call_data)
            raise

    client.messages.create = wrapped_create
    return client


def track_with_timing(
    diagnyx: Diagnyx,
    provider: LLMProvider,
    model: str,
    project_id: Optional[str] = None,
    environment: Optional[str] = None,
    user_identifier: Optional[str] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to track a function call with timing.

    Args:
        diagnyx: Diagnyx client instance
        provider: LLM provider
        model: Model name
        project_id: Optional project ID
        environment: Optional environment name
        user_identifier: Optional user identifier

    Returns:
        Decorator function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                latency_ms = int((time.time() - start_time) * 1000)

                # Try to extract usage from result
                input_tokens = 0
                output_tokens = 0

                if hasattr(result, "usage"):
                    usage = result.usage
                    if hasattr(usage, "prompt_tokens"):
                        input_tokens = usage.prompt_tokens
                        output_tokens = usage.completion_tokens
                    elif hasattr(usage, "input_tokens"):
                        input_tokens = usage.input_tokens
                        output_tokens = usage.output_tokens

                call_data = LLMCallData(
                    provider=provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    status=CallStatus.SUCCESS,
                    project_id=project_id,
                    environment=environment,
                    user_identifier=user_identifier,
                    timestamp=datetime.utcnow(),
                )
                diagnyx.track_call(call_data)

                return result

            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)

                call_data = LLMCallData(
                    provider=provider,
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=latency_ms,
                    status=CallStatus.ERROR,
                    error_message=str(e),
                    project_id=project_id,
                    environment=environment,
                    user_identifier=user_identifier,
                    timestamp=datetime.utcnow(),
                )
                diagnyx.track_call(call_data)
                raise

        return wrapper

    return decorator
