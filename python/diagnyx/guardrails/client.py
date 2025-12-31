"""Streaming guardrails client for real-time LLM response validation."""

import json
from typing import Any, AsyncIterator, Dict, Iterator, Optional

import httpx

from .types import (
    EarlyTerminationEvent,
    EnforcementLevel,
    ErrorEvent,
    GuardrailSession,
    GuardrailViolation,
    SessionCompleteEvent,
    SessionStartedEvent,
    StreamingEvent,
    StreamingEventType,
    ViolationDetectedEvent,
    parse_event,
)


class GuardrailViolationError(Exception):
    """Raised when a blocking guardrail violation terminates the stream."""

    def __init__(self, violation: GuardrailViolation, session: GuardrailSession):
        self.violation = violation
        self.session = session
        super().__init__(f"Guardrail violation: {violation.message}")


class StreamingGuardrails:
    """Client for streaming guardrails evaluation.

    Provides real-time validation of LLM response tokens against configured
    guardrail policies with support for early termination on blocking violations.

    Example:
        >>> from diagnyx.guardrails import StreamingGuardrails
        >>>
        >>> guardrails = StreamingGuardrails(
        ...     api_key="dx_...",
        ...     organization_id="org_123",
        ...     project_id="proj_456",
        ... )
        >>>
        >>> # Start a session and evaluate streaming tokens
        >>> async for token in openai_stream:
        ...     async for event in guardrails.evaluate_token_async(
        ...         session_id, token.content, is_last=token.finish_reason is not None
        ...     ):
        ...         if event.type == StreamingEventType.EARLY_TERMINATION:
        ...             print(f"Stream terminated: {event.reason}")
        ...             break
        ...     yield token
    """

    def __init__(
        self,
        api_key: str,
        organization_id: str,
        project_id: str,
        base_url: str = "https://api.diagnyx.io",
        timeout: float = 30.0,
        evaluate_every_n_tokens: int = 10,
        enable_early_termination: bool = True,
        debug: bool = False,
    ):
        """Initialize the streaming guardrails client.

        Args:
            api_key: Diagnyx API key
            organization_id: Organization ID
            project_id: Project ID for policy lookup
            base_url: API base URL
            timeout: Request timeout in seconds
            evaluate_every_n_tokens: Evaluate policies every N tokens
            enable_early_termination: Stop stream on blocking violations
            debug: Enable debug logging
        """
        self.api_key = api_key
        self.organization_id = organization_id
        self.project_id = project_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.evaluate_every_n_tokens = evaluate_every_n_tokens
        self.enable_early_termination = enable_early_termination
        self.debug = debug

        self._client = httpx.Client(timeout=timeout)
        self._async_client: Optional[httpx.AsyncClient] = None
        self._sessions: Dict[str, GuardrailSession] = {}

    def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client

    def _log(self, message: str) -> None:
        """Log a debug message."""
        if self.debug:
            print(f"[DiagnyxGuardrails] {message}")

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream",
        }

    def _base_endpoint(self) -> str:
        """Get the base guardrails endpoint."""
        return f"{self.base_url}/api/v1/organizations/{self.organization_id}/guardrails"

    def start_session(
        self,
        session_id: Optional[str] = None,
        input_text: Optional[str] = None,
    ) -> SessionStartedEvent:
        """Start a new streaming guardrails session.

        Args:
            session_id: Optional session ID (generated if not provided)
            input_text: Optional input text to pre-evaluate

        Returns:
            SessionStartedEvent with session details
        """
        payload = {
            "projectId": self.project_id,
            "evaluateEveryNTokens": self.evaluate_every_n_tokens,
            "enableEarlyTermination": self.enable_early_termination,
        }
        if session_id:
            payload["sessionId"] = session_id
        if input_text:
            payload["input"] = input_text

        response = self._client.post(
            f"{self._base_endpoint()}/evaluate/stream/start",
            json=payload,
            headers=self._get_headers(),
        )
        response.raise_for_status()
        data = response.json()

        event = parse_event(data)
        if isinstance(event, SessionStartedEvent):
            # Store session state
            self._sessions[event.session_id] = GuardrailSession(
                session_id=event.session_id,
                organization_id=self.organization_id,
                project_id=self.project_id,
                active_policies=event.active_policies,
            )
            self._log(f"Session started: {event.session_id}")
            return event
        elif isinstance(event, ErrorEvent):
            raise RuntimeError(f"Failed to start session: {event.error}")
        else:
            raise RuntimeError(f"Unexpected response: {data}")

    async def start_session_async(
        self,
        session_id: Optional[str] = None,
        input_text: Optional[str] = None,
    ) -> SessionStartedEvent:
        """Start a new streaming guardrails session (async).

        Args:
            session_id: Optional session ID (generated if not provided)
            input_text: Optional input text to pre-evaluate

        Returns:
            SessionStartedEvent with session details
        """
        payload = {
            "projectId": self.project_id,
            "evaluateEveryNTokens": self.evaluate_every_n_tokens,
            "enableEarlyTermination": self.enable_early_termination,
        }
        if session_id:
            payload["sessionId"] = session_id
        if input_text:
            payload["input"] = input_text

        client = self._get_async_client()
        response = await client.post(
            f"{self._base_endpoint()}/evaluate/stream/start",
            json=payload,
            headers=self._get_headers(),
        )
        response.raise_for_status()
        data = response.json()

        event = parse_event(data)
        if isinstance(event, SessionStartedEvent):
            self._sessions[event.session_id] = GuardrailSession(
                session_id=event.session_id,
                organization_id=self.organization_id,
                project_id=self.project_id,
                active_policies=event.active_policies,
            )
            self._log(f"Session started: {event.session_id}")
            return event
        elif isinstance(event, ErrorEvent):
            raise RuntimeError(f"Failed to start session: {event.error}")
        else:
            raise RuntimeError(f"Unexpected response: {data}")

    def evaluate_token(
        self,
        session_id: str,
        token: str,
        token_index: Optional[int] = None,
        is_last: bool = False,
    ) -> Iterator[StreamingEvent]:
        """Evaluate a token against guardrail policies.

        Args:
            session_id: The session ID from start_session
            token: The token text to evaluate
            token_index: Optional token index
            is_last: Whether this is the last token

        Yields:
            StreamingEvent objects (violations, allowed, termination, complete)

        Raises:
            GuardrailViolationError: If a blocking violation occurs and early termination is enabled
        """
        session = self._sessions.get(session_id)
        if not session:
            yield ErrorEvent(
                type=StreamingEventType.ERROR,
                session_id=session_id,
                timestamp=0,
                error="Session not found",
                code="SESSION_NOT_FOUND",
            )
            return

        payload = {
            "sessionId": session_id,
            "token": token,
            "isLast": is_last,
        }
        if token_index is not None:
            payload["tokenIndex"] = token_index

        with self._client.stream(
            "POST",
            f"{self._base_endpoint()}/evaluate/stream",
            json=payload,
            headers=self._get_headers(),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])  # Remove "data: " prefix
                    event = parse_event(data)

                    # Update session state
                    self._update_session(session, event)

                    yield event

                    # Check for early termination
                    if isinstance(event, EarlyTerminationEvent):
                        if event.blocking_violation:
                            violation = event.blocking_violation.to_violation()
                            raise GuardrailViolationError(violation, session)
                        break
                    elif isinstance(event, SessionCompleteEvent):
                        break
                    elif isinstance(event, ErrorEvent):
                        break

                except json.JSONDecodeError as e:
                    self._log(f"Failed to parse event: {e}")
                    continue

    async def evaluate_token_async(
        self,
        session_id: str,
        token: str,
        token_index: Optional[int] = None,
        is_last: bool = False,
    ) -> AsyncIterator[StreamingEvent]:
        """Evaluate a token against guardrail policies (async).

        Args:
            session_id: The session ID from start_session
            token: The token text to evaluate
            token_index: Optional token index
            is_last: Whether this is the last token

        Yields:
            StreamingEvent objects (violations, allowed, termination, complete)

        Raises:
            GuardrailViolationError: If a blocking violation occurs and early termination is enabled
        """
        session = self._sessions.get(session_id)
        if not session:
            yield ErrorEvent(
                type=StreamingEventType.ERROR,
                session_id=session_id,
                timestamp=0,
                error="Session not found",
                code="SESSION_NOT_FOUND",
            )
            return

        payload = {
            "sessionId": session_id,
            "token": token,
            "isLast": is_last,
        }
        if token_index is not None:
            payload["tokenIndex"] = token_index

        client = self._get_async_client()
        async with client.stream(
            "POST",
            f"{self._base_endpoint()}/evaluate/stream",
            json=payload,
            headers=self._get_headers(),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    event = parse_event(data)

                    self._update_session(session, event)

                    yield event

                    if isinstance(event, EarlyTerminationEvent):
                        if event.blocking_violation:
                            violation = event.blocking_violation.to_violation()
                            raise GuardrailViolationError(violation, session)
                        break
                    elif isinstance(event, SessionCompleteEvent):
                        break
                    elif isinstance(event, ErrorEvent):
                        break

                except json.JSONDecodeError as e:
                    self._log(f"Failed to parse event: {e}")
                    continue

    def complete_session(self, session_id: str) -> Iterator[StreamingEvent]:
        """Complete a streaming session manually.

        Args:
            session_id: The session ID to complete

        Yields:
            Final evaluation events
        """
        with self._client.stream(
            "POST",
            f"{self._base_endpoint()}/evaluate/stream/{session_id}/complete",
            headers=self._get_headers(),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    event = parse_event(data)
                    yield event
                except json.JSONDecodeError:
                    continue

        # Cleanup session
        self._sessions.pop(session_id, None)

    async def complete_session_async(self, session_id: str) -> AsyncIterator[StreamingEvent]:
        """Complete a streaming session manually (async).

        Args:
            session_id: The session ID to complete

        Yields:
            Final evaluation events
        """
        client = self._get_async_client()
        async with client.stream(
            "POST",
            f"{self._base_endpoint()}/evaluate/stream/{session_id}/complete",
            headers=self._get_headers(),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    event = parse_event(data)
                    yield event
                except json.JSONDecodeError:
                    continue

        self._sessions.pop(session_id, None)

    def cancel_session(self, session_id: str) -> bool:
        """Cancel a streaming session.

        Args:
            session_id: The session ID to cancel

        Returns:
            True if cancelled, False otherwise
        """
        response = self._client.delete(
            f"{self._base_endpoint()}/evaluate/stream/{session_id}",
            headers=self._get_headers(),
        )
        response.raise_for_status()
        data = response.json()
        self._sessions.pop(session_id, None)
        return data.get("cancelled", False)

    async def cancel_session_async(self, session_id: str) -> bool:
        """Cancel a streaming session (async).

        Args:
            session_id: The session ID to cancel

        Returns:
            True if cancelled, False otherwise
        """
        client = self._get_async_client()
        response = await client.delete(
            f"{self._base_endpoint()}/evaluate/stream/{session_id}",
            headers=self._get_headers(),
        )
        response.raise_for_status()
        data = response.json()
        self._sessions.pop(session_id, None)
        return data.get("cancelled", False)

    def get_session(self, session_id: str) -> Optional[GuardrailSession]:
        """Get the current state of a session.

        Args:
            session_id: The session ID

        Returns:
            GuardrailSession or None if not found
        """
        return self._sessions.get(session_id)

    def _update_session(self, session: GuardrailSession, event: StreamingEvent) -> None:
        """Update session state based on event."""
        if isinstance(event, ViolationDetectedEvent):
            session.violations.append(event.to_violation())
            if event.enforcement_level == EnforcementLevel.BLOCKING.value:
                session.allowed = False
        elif isinstance(event, EarlyTerminationEvent):
            session.terminated = True
            session.termination_reason = event.reason
            session.allowed = False
            session.tokens_processed = event.tokens_processed
        elif isinstance(event, SessionCompleteEvent):
            session.tokens_processed = event.total_tokens
            session.allowed = event.allowed

    def close(self) -> None:
        """Close the client and release resources."""
        self._client.close()
        if self._async_client:
            # Note: async client should be closed with await in async context
            pass

    async def aclose(self) -> None:
        """Close the client and release resources (async)."""
        self._client.close()
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()
        return False
