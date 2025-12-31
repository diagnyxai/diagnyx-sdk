"""Wrapper functions for streaming guardrails."""

from typing import Any, AsyncIterator, Iterator, Optional, TypeVar

from .client import GuardrailViolationError, StreamingGuardrails
from .types import (
    EarlyTerminationEvent,
    SessionCompleteEvent,
    StreamingEvent,
    StreamingEventType,
    ViolationDetectedEvent,
)

T = TypeVar("T")


def stream_with_guardrails(
    stream: Iterator[T],
    guardrails: StreamingGuardrails,
    get_token_content: Optional[callable] = None,
    get_is_last: Optional[callable] = None,
    input_text: Optional[str] = None,
    on_violation: Optional[callable] = None,
    on_termination: Optional[callable] = None,
    raise_on_blocking: bool = True,
) -> Iterator[T]:
    """Wrap a streaming LLM response with guardrail validation.

    Args:
        stream: The streaming LLM response iterator
        guardrails: StreamingGuardrails client instance
        get_token_content: Function to extract token content from stream items.
            Default extracts .choices[0].delta.content for OpenAI format.
        get_is_last: Function to check if item is the last token.
            Default checks .choices[0].finish_reason is not None for OpenAI format.
        input_text: Optional input text to pre-evaluate
        on_violation: Callback for violations (violation, session)
        on_termination: Callback for early termination (event, session)
        raise_on_blocking: Raise GuardrailViolationError on blocking violations

    Yields:
        Stream items that pass guardrail validation

    Raises:
        GuardrailViolationError: If a blocking violation occurs and raise_on_blocking=True

    Example:
        >>> from openai import OpenAI
        >>> from diagnyx.guardrails import StreamingGuardrails, stream_with_guardrails
        >>>
        >>> client = OpenAI()
        >>> guardrails = StreamingGuardrails(
        ...     api_key="dx_...",
        ...     organization_id="org_123",
        ...     project_id="proj_456",
        ... )
        >>>
        >>> stream = client.chat.completions.create(
        ...     model="gpt-4",
        ...     messages=[{"role": "user", "content": "Hello!"}],
        ...     stream=True,
        ... )
        >>>
        >>> for chunk in stream_with_guardrails(stream, guardrails):
        ...     print(chunk.choices[0].delta.content, end="")
    """
    # Default extractors for OpenAI format
    if get_token_content is None:

        def get_token_content(item: Any) -> str:
            try:
                content = item.choices[0].delta.content
                return content if content else ""
            except (AttributeError, IndexError):
                return ""

    if get_is_last is None:

        def get_is_last(item: Any) -> bool:
            try:
                return item.choices[0].finish_reason is not None
            except (AttributeError, IndexError):
                return False

    # Start session
    session_event = guardrails.start_session(input_text=input_text)
    session_id = session_event.session_id
    session = guardrails.get_session(session_id)

    token_index = 0

    try:
        for item in stream:
            token_content = get_token_content(item)
            is_last = get_is_last(item)

            if token_content:
                # Evaluate token
                for event in guardrails.evaluate_token(
                    session_id,
                    token_content,
                    token_index=token_index,
                    is_last=is_last,
                ):
                    if isinstance(event, ViolationDetectedEvent):
                        if on_violation:
                            on_violation(event.to_violation(), session)

                    elif isinstance(event, EarlyTerminationEvent):
                        if on_termination:
                            on_termination(event, session)
                        if raise_on_blocking and event.blocking_violation:
                            raise GuardrailViolationError(
                                event.blocking_violation.to_violation(),
                                session,
                            )
                        return

                token_index += 1

            yield item

            if is_last:
                break

    except GuardrailViolationError:
        raise
    finally:
        # Complete session if not already terminated
        if session and not session.terminated:
            for _ in guardrails.complete_session(session_id):
                pass


async def stream_with_guardrails_async(
    stream: AsyncIterator[T],
    guardrails: StreamingGuardrails,
    get_token_content: Optional[callable] = None,
    get_is_last: Optional[callable] = None,
    input_text: Optional[str] = None,
    on_violation: Optional[callable] = None,
    on_termination: Optional[callable] = None,
    raise_on_blocking: bool = True,
) -> AsyncIterator[T]:
    """Wrap an async streaming LLM response with guardrail validation.

    Args:
        stream: The async streaming LLM response iterator
        guardrails: StreamingGuardrails client instance
        get_token_content: Function to extract token content from stream items
        get_is_last: Function to check if item is the last token
        input_text: Optional input text to pre-evaluate
        on_violation: Callback for violations (violation, session)
        on_termination: Callback for early termination (event, session)
        raise_on_blocking: Raise GuardrailViolationError on blocking violations

    Yields:
        Stream items that pass guardrail validation

    Example:
        >>> from openai import AsyncOpenAI
        >>> from diagnyx.guardrails import StreamingGuardrails, stream_with_guardrails_async
        >>>
        >>> client = AsyncOpenAI()
        >>> guardrails = StreamingGuardrails(...)
        >>>
        >>> stream = await client.chat.completions.create(
        ...     model="gpt-4",
        ...     messages=[{"role": "user", "content": "Hello!"}],
        ...     stream=True,
        ... )
        >>>
        >>> async for chunk in stream_with_guardrails_async(stream, guardrails):
        ...     print(chunk.choices[0].delta.content, end="")
    """
    # Default extractors for OpenAI format
    if get_token_content is None:

        def get_token_content(item: Any) -> str:
            try:
                content = item.choices[0].delta.content
                return content if content else ""
            except (AttributeError, IndexError):
                return ""

    if get_is_last is None:

        def get_is_last(item: Any) -> bool:
            try:
                return item.choices[0].finish_reason is not None
            except (AttributeError, IndexError):
                return False

    # Start session
    session_event = await guardrails.start_session_async(input_text=input_text)
    session_id = session_event.session_id
    session = guardrails.get_session(session_id)

    token_index = 0

    try:
        async for item in stream:
            token_content = get_token_content(item)
            is_last = get_is_last(item)

            if token_content:
                async for event in guardrails.evaluate_token_async(
                    session_id,
                    token_content,
                    token_index=token_index,
                    is_last=is_last,
                ):
                    if isinstance(event, ViolationDetectedEvent):
                        if on_violation:
                            on_violation(event.to_violation(), session)

                    elif isinstance(event, EarlyTerminationEvent):
                        if on_termination:
                            on_termination(event, session)
                        if raise_on_blocking and event.blocking_violation:
                            raise GuardrailViolationError(
                                event.blocking_violation.to_violation(),
                                session,
                            )
                        return

                token_index += 1

            yield item

            if is_last:
                break

    except GuardrailViolationError:
        raise
    finally:
        if session and not session.terminated:
            async for _ in guardrails.complete_session_async(session_id):
                pass


def wrap_streaming_response(
    guardrails: StreamingGuardrails,
    input_text: Optional[str] = None,
    get_token_content: Optional[callable] = None,
    get_is_last: Optional[callable] = None,
    on_violation: Optional[callable] = None,
    on_termination: Optional[callable] = None,
    raise_on_blocking: bool = True,
) -> callable:
    """Create a decorator to wrap streaming LLM responses with guardrails.

    Args:
        guardrails: StreamingGuardrails client instance
        input_text: Optional input text to pre-evaluate
        get_token_content: Function to extract token content from stream items
        get_is_last: Function to check if item is the last token
        on_violation: Callback for violations
        on_termination: Callback for early termination
        raise_on_blocking: Raise GuardrailViolationError on blocking violations

    Returns:
        Decorator function

    Example:
        >>> from diagnyx.guardrails import StreamingGuardrails, wrap_streaming_response
        >>>
        >>> guardrails = StreamingGuardrails(...)
        >>>
        >>> @wrap_streaming_response(guardrails)
        ... def get_completion(prompt: str):
        ...     return openai.chat.completions.create(
        ...         model="gpt-4",
        ...         messages=[{"role": "user", "content": prompt}],
        ...         stream=True,
        ...     )
        >>>
        >>> for chunk in get_completion("Hello!"):
        ...     print(chunk.choices[0].delta.content, end="")
    """

    def decorator(func: callable) -> callable:
        def wrapper(*args, **kwargs):
            stream = func(*args, **kwargs)
            return stream_with_guardrails(
                stream,
                guardrails,
                get_token_content=get_token_content,
                get_is_last=get_is_last,
                input_text=input_text,
                on_violation=on_violation,
                on_termination=on_termination,
                raise_on_blocking=raise_on_blocking,
            )

        return wrapper

    return decorator
