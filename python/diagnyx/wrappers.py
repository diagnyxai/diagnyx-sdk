"""Wrappers for popular LLM libraries."""

import functools
import time
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar

from .client import Diagnyx
from .types import LLMCallData, CallStatus, LLMProvider

T = TypeVar("T")


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
