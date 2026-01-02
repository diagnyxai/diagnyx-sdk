"""Streaming guardrails for real-time token-by-token LLM output validation.

This module provides the StreamingGuardrail class for evaluating LLM output
tokens as they are generated, enabling early termination on policy violations.

Example:
    >>> from diagnyx.guardrails.streaming import StreamingGuardrail
    >>>
    >>> guardrail = StreamingGuardrail(
    ...     api_key="dx_...",
    ...     organization_id="org_123",
    ...     project_id="proj_456",
    ... )
    >>>
    >>> async def protected_stream():
    ...     async with guardrail:
    ...         session = await guardrail.start_session_async()
    ...         async for chunk in openai_stream:
    ...             token = chunk.choices[0].delta.content or ""
    ...             is_last = chunk.choices[0].finish_reason is not None
    ...             # Evaluate and yield filtered token
    ...             async for filtered_token in guardrail.evaluate_async(
    ...                 token, is_last=is_last
    ...             ):
    ...                 yield filtered_token
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    TypeVar,
    Union,
)

try:
    import httpx
except ImportError:
    httpx = None

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    websockets = None


class EnforcementLevel(str, Enum):
    """Policy enforcement levels."""

    ADVISORY = "advisory"
    WARNING = "warning"
    BLOCKING = "blocking"


class StreamingEventType(str, Enum):
    """Types of streaming evaluation events."""

    SESSION_STARTED = "session_started"
    TOKEN_ALLOWED = "token_allowed"
    VIOLATION_DETECTED = "violation_detected"
    EARLY_TERMINATION = "early_termination"
    SESSION_COMPLETE = "session_complete"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


@dataclass
class GuardrailViolation:
    """Details of a guardrail policy violation."""

    policy_id: str
    policy_name: str
    policy_type: str
    violation_type: str
    message: str
    severity: str
    enforcement_level: EnforcementLevel
    details: Optional[Dict[str, Any]] = None


@dataclass
class StreamingSession:
    """State of a streaming guardrail session."""

    session_id: str
    organization_id: str
    project_id: str
    active_policies: List[str] = field(default_factory=list)
    tokens_processed: int = 0
    violations: List[GuardrailViolation] = field(default_factory=list)
    terminated: bool = False
    termination_reason: Optional[str] = None
    allowed: bool = True
    accumulated_text: str = ""


class GuardrailViolationError(Exception):
    """Raised when a blocking guardrail violation terminates the stream."""

    def __init__(self, violation: GuardrailViolation, session: StreamingSession):
        self.violation = violation
        self.session = session
        super().__init__(f"Guardrail violation: {violation.message}")


@dataclass
class StreamingGuardrailConfig:
    """Configuration for StreamingGuardrail."""

    api_key: str
    organization_id: str
    project_id: str
    base_url: str = "https://api.diagnyx.io"
    ws_url: Optional[str] = None
    timeout: float = 30.0
    evaluate_every_n_tokens: int = 10
    enable_early_termination: bool = True
    use_websocket: bool = False
    debug: bool = False

    def __post_init__(self):
        if self.ws_url is None:
            # Derive WebSocket URL from base URL
            if self.base_url.startswith("https://"):
                self.ws_url = self.base_url.replace("https://", "wss://") + "/guardrails"
            else:
                self.ws_url = self.base_url.replace("http://", "ws://") + "/guardrails"


class StreamingGuardrail:
    """Token-by-token streaming guardrail for LLM output validation.

    Provides real-time evaluation of LLM response tokens against configured
    guardrail policies with support for early termination on blocking violations.

    This class supports both HTTP SSE and WebSocket connections for streaming
    evaluation.

    Args:
        api_key: Diagnyx API key
        organization_id: Organization ID
        project_id: Project ID for policy lookup
        base_url: API base URL
        timeout: Request timeout in seconds
        evaluate_every_n_tokens: Evaluate policies every N tokens
        enable_early_termination: Stop stream on blocking violations
        use_websocket: Use WebSocket instead of HTTP SSE
        debug: Enable debug logging

    Example:
        >>> guardrail = StreamingGuardrail(
        ...     api_key="dx_live_...",
        ...     organization_id="org_123",
        ...     project_id="proj_456",
        ... )
        >>>
        >>> # Synchronous usage
        >>> with guardrail:
        ...     session = guardrail.start_session()
        ...     for token in llm_tokens:
        ...         for filtered in guardrail.evaluate(token):
        ...             print(filtered, end="")
        >>>
        >>> # Async usage
        >>> async with guardrail:
        ...     session = await guardrail.start_session_async()
        ...     async for token in async_llm_tokens:
        ...         async for filtered in guardrail.evaluate_async(token):
        ...             print(filtered, end="")
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
        use_websocket: bool = False,
        debug: bool = False,
    ):
        self.config = StreamingGuardrailConfig(
            api_key=api_key,
            organization_id=organization_id,
            project_id=project_id,
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            evaluate_every_n_tokens=evaluate_every_n_tokens,
            enable_early_termination=enable_early_termination,
            use_websocket=use_websocket,
            debug=debug,
        )

        self._session: Optional[StreamingSession] = None
        self._http_client: Optional[httpx.Client] = None
        self._async_http_client: Optional[httpx.AsyncClient] = None
        self._ws_client: Optional[WebSocketClientProtocol] = None
        self._token_index: int = 0

    def _log(self, message: str) -> None:
        """Log a debug message."""
        if self.config.debug:
            print(f"[DiagnyxGuardrails] {message}")

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "text/event-stream",
        }

    def _get_base_endpoint(self) -> str:
        """Get the base guardrails endpoint."""
        return f"{self.config.base_url}/api/v1/organizations/{self.config.organization_id}/guardrails"

    def _ensure_http_client(self) -> httpx.Client:
        """Get or create sync HTTP client."""
        if httpx is None:
            raise ImportError("httpx is required for HTTP streaming. Install with: pip install httpx")
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=self.config.timeout)
        return self._http_client

    def _ensure_async_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if httpx is None:
            raise ImportError("httpx is required for HTTP streaming. Install with: pip install httpx")
        if self._async_http_client is None:
            self._async_http_client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._async_http_client

    # ========================
    # Session Management
    # ========================

    def start_session(self, input_text: Optional[str] = None) -> StreamingSession:
        """Start a new streaming guardrail session (sync).

        Args:
            input_text: Optional input text to pre-evaluate

        Returns:
            StreamingSession with session details

        Raises:
            RuntimeError: If session creation fails
        """
        client = self._ensure_http_client()

        payload = {
            "projectId": self.config.project_id,
            "evaluateEveryNTokens": self.config.evaluate_every_n_tokens,
            "enableEarlyTermination": self.config.enable_early_termination,
        }
        if input_text:
            payload["input"] = input_text

        response = client.post(
            f"{self._get_base_endpoint()}/evaluate/stream/start",
            json=payload,
            headers=self._get_headers(),
        )
        response.raise_for_status()
        data = response.json()

        if data.get("type") == "session_started":
            self._session = StreamingSession(
                session_id=data["sessionId"],
                organization_id=self.config.organization_id,
                project_id=self.config.project_id,
                active_policies=data.get("activePolicies", []),
            )
            self._token_index = 0
            self._log(f"Session started: {self._session.session_id}")
            return self._session
        elif data.get("type") == "error":
            raise RuntimeError(f"Failed to start session: {data.get('error')}")
        else:
            raise RuntimeError(f"Unexpected response: {data}")

    async def start_session_async(self, input_text: Optional[str] = None) -> StreamingSession:
        """Start a new streaming guardrail session (async).

        Args:
            input_text: Optional input text to pre-evaluate

        Returns:
            StreamingSession with session details

        Raises:
            RuntimeError: If session creation fails
        """
        if self.config.use_websocket:
            return await self._start_ws_session(input_text)

        client = self._ensure_async_http_client()

        payload = {
            "projectId": self.config.project_id,
            "evaluateEveryNTokens": self.config.evaluate_every_n_tokens,
            "enableEarlyTermination": self.config.enable_early_termination,
        }
        if input_text:
            payload["input"] = input_text

        response = await client.post(
            f"{self._get_base_endpoint()}/evaluate/stream/start",
            json=payload,
            headers=self._get_headers(),
        )
        response.raise_for_status()
        data = response.json()

        if data.get("type") == "session_started":
            self._session = StreamingSession(
                session_id=data["sessionId"],
                organization_id=self.config.organization_id,
                project_id=self.config.project_id,
                active_policies=data.get("activePolicies", []),
            )
            self._token_index = 0
            self._log(f"Session started: {self._session.session_id}")
            return self._session
        elif data.get("type") == "error":
            raise RuntimeError(f"Failed to start session: {data.get('error')}")
        else:
            raise RuntimeError(f"Unexpected response: {data}")

    async def _start_ws_session(self, input_text: Optional[str] = None) -> StreamingSession:
        """Start session via WebSocket."""
        if websockets is None:
            raise ImportError(
                "websockets is required for WebSocket streaming. Install with: pip install websockets"
            )

        # Connect to WebSocket
        ws_url = f"{self.config.ws_url}?token={self.config.api_key}"
        self._ws_client = await websockets.connect(ws_url)

        # Send start session message
        await self._ws_client.send(
            json.dumps(
                {
                    "type": "start_session",
                    "projectId": self.config.project_id,
                    "input": input_text,
                    "evaluateEveryNTokens": self.config.evaluate_every_n_tokens,
                    "enableEarlyTermination": self.config.enable_early_termination,
                }
            )
        )

        # Wait for response
        response = await self._ws_client.recv()
        data = json.loads(response)

        if data.get("type") == "session_started":
            self._session = StreamingSession(
                session_id=data["sessionId"],
                organization_id=self.config.organization_id,
                project_id=self.config.project_id,
                active_policies=data.get("activePolicies", []),
            )
            self._token_index = 0
            self._log(f"Session started (WS): {self._session.session_id}")
            return self._session
        else:
            raise RuntimeError(f"Failed to start session: {data}")

    # ========================
    # Token Evaluation
    # ========================

    def evaluate(
        self,
        token: str,
        is_last: bool = False,
    ) -> Iterator[str]:
        """Evaluate a token against guardrail policies (sync).

        Yields the token if it passes validation. Raises GuardrailViolationError
        if a blocking violation is detected and early termination is enabled.

        Args:
            token: The token text to evaluate
            is_last: Whether this is the last token in the stream

        Yields:
            The token text if it passes validation

        Raises:
            GuardrailViolationError: If a blocking violation is detected
            RuntimeError: If no active session
        """
        if self._session is None:
            raise RuntimeError("No active session. Call start_session() first.")

        client = self._ensure_http_client()

        payload = {
            "sessionId": self._session.session_id,
            "token": token,
            "tokenIndex": self._token_index,
            "isLast": is_last,
        }

        self._session.accumulated_text += token
        self._token_index += 1

        with client.stream(
            "POST",
            f"{self._get_base_endpoint()}/evaluate/stream",
            json=payload,
            headers=self._get_headers(),
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                    event_type = data.get("type")

                    if event_type == "token_allowed":
                        self._session.tokens_processed = data.get("tokenIndex", 0) + 1
                        yield token

                    elif event_type == "violation_detected":
                        violation = self._parse_violation(data)
                        self._session.violations.append(violation)

                        if violation.enforcement_level == EnforcementLevel.BLOCKING:
                            self._session.allowed = False

                    elif event_type == "early_termination":
                        violation = self._parse_violation(data.get("blockingViolation", {}))
                        self._session.terminated = True
                        self._session.termination_reason = data.get("reason")
                        self._session.allowed = False
                        raise GuardrailViolationError(violation, self._session)

                    elif event_type == "session_complete":
                        self._session.tokens_processed = data.get("totalTokens", 0)
                        self._session.allowed = data.get("allowed", True)

                    elif event_type == "error":
                        self._log(f"Error: {data.get('error')}")

                except json.JSONDecodeError as e:
                    self._log(f"Failed to parse event: {e}")

    async def evaluate_async(
        self,
        token: str,
        is_last: bool = False,
    ) -> AsyncIterator[str]:
        """Evaluate a token against guardrail policies (async).

        Yields the token if it passes validation. Raises GuardrailViolationError
        if a blocking violation is detected and early termination is enabled.

        Args:
            token: The token text to evaluate
            is_last: Whether this is the last token in the stream

        Yields:
            The token text if it passes validation

        Raises:
            GuardrailViolationError: If a blocking violation is detected
            RuntimeError: If no active session
        """
        if self._session is None:
            raise RuntimeError("No active session. Call start_session_async() first.")

        if self.config.use_websocket and self._ws_client:
            async for result in self._evaluate_ws(token, is_last):
                yield result
            return

        client = self._ensure_async_http_client()

        payload = {
            "sessionId": self._session.session_id,
            "token": token,
            "tokenIndex": self._token_index,
            "isLast": is_last,
        }

        self._session.accumulated_text += token
        self._token_index += 1

        async with client.stream(
            "POST",
            f"{self._get_base_endpoint()}/evaluate/stream",
            json=payload,
            headers=self._get_headers(),
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                    event_type = data.get("type")

                    if event_type == "token_allowed":
                        self._session.tokens_processed = data.get("tokenIndex", 0) + 1
                        yield token

                    elif event_type == "violation_detected":
                        violation = self._parse_violation(data)
                        self._session.violations.append(violation)

                        if violation.enforcement_level == EnforcementLevel.BLOCKING:
                            self._session.allowed = False

                    elif event_type == "early_termination":
                        violation = self._parse_violation(data.get("blockingViolation", {}))
                        self._session.terminated = True
                        self._session.termination_reason = data.get("reason")
                        self._session.allowed = False
                        raise GuardrailViolationError(violation, self._session)

                    elif event_type == "session_complete":
                        self._session.tokens_processed = data.get("totalTokens", 0)
                        self._session.allowed = data.get("allowed", True)

                    elif event_type == "error":
                        self._log(f"Error: {data.get('error')}")

                except json.JSONDecodeError as e:
                    self._log(f"Failed to parse event: {e}")

    async def _evaluate_ws(self, token: str, is_last: bool) -> AsyncIterator[str]:
        """Evaluate token via WebSocket."""
        if not self._ws_client or not self._session:
            raise RuntimeError("WebSocket not connected")

        await self._ws_client.send(
            json.dumps(
                {
                    "type": "evaluate_token",
                    "sessionId": self._session.session_id,
                    "token": token,
                    "tokenIndex": self._token_index,
                    "isLast": is_last,
                }
            )
        )

        self._session.accumulated_text += token
        self._token_index += 1

        async for message in self._ws_client:
            data = json.loads(message)
            event_type = data.get("type")

            if event_type == "token_allowed":
                self._session.tokens_processed = data.get("tokenIndex", 0) + 1
                yield token
                break

            elif event_type == "violation_detected":
                violation = self._parse_violation(data)
                self._session.violations.append(violation)

                if violation.enforcement_level == EnforcementLevel.BLOCKING:
                    self._session.allowed = False

            elif event_type == "early_termination":
                violation = self._parse_violation(data.get("blockingViolation", {}))
                self._session.terminated = True
                self._session.termination_reason = data.get("reason")
                self._session.allowed = False
                raise GuardrailViolationError(violation, self._session)

            elif event_type == "session_complete":
                self._session.tokens_processed = data.get("totalTokens", 0)
                self._session.allowed = data.get("allowed", True)
                break

    # ========================
    # Session Completion
    # ========================

    def complete_session(self) -> StreamingSession:
        """Complete the current session (sync).

        Returns:
            Final session state
        """
        if self._session is None:
            raise RuntimeError("No active session")

        client = self._ensure_http_client()

        with client.stream(
            "POST",
            f"{self._get_base_endpoint()}/evaluate/stream/{self._session.session_id}/complete",
            headers=self._get_headers(),
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "session_complete":
                        self._session.tokens_processed = data.get("totalTokens", 0)
                        self._session.allowed = data.get("allowed", True)
                except json.JSONDecodeError:
                    pass

        session = self._session
        self._session = None
        return session

    async def complete_session_async(self) -> StreamingSession:
        """Complete the current session (async).

        Returns:
            Final session state
        """
        if self._session is None:
            raise RuntimeError("No active session")

        if self.config.use_websocket and self._ws_client:
            await self._ws_client.send(
                json.dumps(
                    {
                        "type": "complete_session",
                        "sessionId": self._session.session_id,
                    }
                )
            )
            async for message in self._ws_client:
                data = json.loads(message)
                if data.get("type") == "session_complete":
                    self._session.tokens_processed = data.get("totalTokens", 0)
                    self._session.allowed = data.get("allowed", True)
                    break
        else:
            client = self._ensure_async_http_client()

            async with client.stream(
                "POST",
                f"{self._get_base_endpoint()}/evaluate/stream/{self._session.session_id}/complete",
                headers=self._get_headers(),
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "session_complete":
                            self._session.tokens_processed = data.get("totalTokens", 0)
                            self._session.allowed = data.get("allowed", True)
                    except json.JSONDecodeError:
                        pass

        session = self._session
        self._session = None
        return session

    def cancel_session(self) -> bool:
        """Cancel the current session (sync).

        Returns:
            True if cancelled successfully
        """
        if self._session is None:
            return False

        client = self._ensure_http_client()

        response = client.delete(
            f"{self._get_base_endpoint()}/evaluate/stream/{self._session.session_id}",
            headers=self._get_headers(),
        )
        response.raise_for_status()
        data = response.json()

        self._session = None
        return data.get("cancelled", False)

    async def cancel_session_async(self) -> bool:
        """Cancel the current session (async).

        Returns:
            True if cancelled successfully
        """
        if self._session is None:
            return False

        if self.config.use_websocket and self._ws_client:
            await self._ws_client.send(
                json.dumps(
                    {
                        "type": "cancel_session",
                        "sessionId": self._session.session_id,
                    }
                )
            )
            self._session = None
            return True

        client = self._ensure_async_http_client()

        response = await client.delete(
            f"{self._get_base_endpoint()}/evaluate/stream/{self._session.session_id}",
            headers=self._get_headers(),
        )
        response.raise_for_status()
        data = response.json()

        self._session = None
        return data.get("cancelled", False)

    # ========================
    # Properties
    # ========================

    @property
    def session(self) -> Optional[StreamingSession]:
        """Get the current session."""
        return self._session

    @property
    def is_active(self) -> bool:
        """Check if there's an active session."""
        return self._session is not None and not self._session.terminated

    # ========================
    # Helpers
    # ========================

    def _parse_violation(self, data: Dict[str, Any]) -> GuardrailViolation:
        """Parse violation data into GuardrailViolation."""
        enforcement = data.get("enforcementLevel", data.get("enforcement_level", "advisory"))
        return GuardrailViolation(
            policy_id=data.get("policyId", data.get("policy_id", "")),
            policy_name=data.get("policyName", data.get("policy_name", "")),
            policy_type=data.get("policyType", data.get("policy_type", "")),
            violation_type=data.get("violationType", data.get("violation_type", "")),
            message=data.get("message", ""),
            severity=data.get("severity", ""),
            enforcement_level=EnforcementLevel(enforcement) if enforcement else EnforcementLevel.ADVISORY,
            details=data.get("details"),
        )

    # ========================
    # Context Managers
    # ========================

    def __enter__(self) -> "StreamingGuardrail":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit."""
        self.close()
        return False

    async def __aenter__(self) -> "StreamingGuardrail":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Async context manager exit."""
        await self.aclose()
        return False

    def close(self) -> None:
        """Close the client and release resources."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None

    async def aclose(self) -> None:
        """Close the client and release resources (async)."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None

        if self._async_http_client:
            await self._async_http_client.aclose()
            self._async_http_client = None

        if self._ws_client:
            await self._ws_client.close()
            self._ws_client = None


# Convenience function for wrapping async generators
T = TypeVar("T")


async def stream_with_guardrails(
    guardrail: StreamingGuardrail,
    token_stream: AsyncIterator[str],
    input_text: Optional[str] = None,
) -> AsyncIterator[str]:
    """Wrap an async token stream with guardrail protection.

    Args:
        guardrail: StreamingGuardrail instance
        token_stream: Async iterator of tokens
        input_text: Optional input text to pre-evaluate

    Yields:
        Tokens that pass guardrail validation

    Raises:
        GuardrailViolationError: If a blocking violation is detected
    """
    await guardrail.start_session_async(input_text)

    try:
        async for token in token_stream:
            async for filtered_token in guardrail.evaluate_async(token):
                yield filtered_token
    finally:
        if guardrail.is_active:
            await guardrail.complete_session_async()
