"""Diagnyx client for LLM tracking and tracing."""

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from .tracing import Tracer
from .tracing_types import IngestResult, TraceData
from .prompts import PromptsClient
from .types import (
    BatchResult,
    DiagnyxConfig,
    LLMCallData,
)


class Diagnyx:
    """Client for tracking LLM calls with Diagnyx."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.diagnyx.io",
        batch_size: int = 100,
        flush_interval_ms: int = 5000,
        max_retries: int = 3,
        debug: bool = False,
    ):
        """Initialize the Diagnyx client.

        Args:
            api_key: Your Diagnyx API key (starts with dx_)
            base_url: API base URL
            batch_size: Number of calls to batch before flushing
            flush_interval_ms: Interval to flush buffer in milliseconds
            max_retries: Maximum number of retry attempts
            debug: Enable debug logging
        """
        if not api_key:
            raise ValueError("Diagnyx: api_key is required")

        self.config = DiagnyxConfig(
            api_key=api_key,
            base_url=base_url,
            batch_size=batch_size,
            flush_interval_ms=flush_interval_ms,
            max_retries=max_retries,
            debug=debug,
        )

        self._buffer: List[LLMCallData] = []
        self._buffer_lock = threading.Lock()
        self._is_flushing = False
        self._flush_timer: Optional[threading.Timer] = None
        self._client = httpx.Client(timeout=30.0)
        self._tracers: Dict[str, Tracer] = {}
        self._prompts_clients: Dict[str, PromptsClient] = {}

        self._start_flush_timer()

    def tracer(
        self,
        organization_id: str,
        environment: Optional[str] = None,
        default_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tracer:
        """Get or create a tracer for an organization.

        Args:
            organization_id: The organization ID to trace for
            environment: Optional environment name (production, staging, etc.)
            default_metadata: Default metadata to include in all traces

        Returns:
            Tracer instance for creating traces and spans
        """
        cache_key = f"{organization_id}:{environment or ''}"
        if cache_key not in self._tracers:
            self._tracers[cache_key] = Tracer(
                client=self,
                organization_id=organization_id,
                environment=environment,
                default_metadata=default_metadata,
            )
        return self._tracers[cache_key]

    def prompts(self, organization_id: str) -> PromptsClient:
        """Get a prompts client for an organization.

        Args:
            organization_id: The organization ID

        Returns:
            PromptsClient for managing prompts

        Example:
            >>> # Get and render a prompt
            >>> prompt = dx.prompts(org_id).get(
            ...     "summarize-article",
            ...     variables={"article": article_text},
            ...     environment="production"
            ... )
            >>>
            >>> # Use with OpenAI
            >>> response = openai.chat.completions.create(
            ...     model=prompt.model or "gpt-4",
            ...     messages=prompt.to_openai_messages(),
            ...     **prompt.get_model_params()
            ... )
            >>>
            >>> # Log usage for analytics
            >>> dx.prompts(org_id).log_usage(
            ...     slug="summarize-article",
            ...     version=prompt.version,
            ...     environment="production",
            ...     latency_ms=response_time_ms,
            ...     input_tokens=response.usage.prompt_tokens,
            ...     output_tokens=response.usage.completion_tokens,
            ... )
        """
        if organization_id not in self._prompts_clients:
            self._prompts_clients[organization_id] = PromptsClient(
                api_key=self.config.api_key,
                organization_id=organization_id,
                base_url=self.config.base_url,
                max_retries=self.config.max_retries,
                debug=self.config.debug,
            )
        return self._prompts_clients[organization_id]

    def _send_traces(
        self,
        organization_id: str,
        traces: List[TraceData],
    ) -> IngestResult:
        """Send traces to the backend API.

        Args:
            organization_id: The organization ID
            traces: List of trace data to send

        Returns:
            IngestResult with accepted/failed counts
        """
        payload = {"traces": [t.to_dict() for t in traces]}

        last_error: Optional[Exception] = None

        for attempt in range(self.config.max_retries):
            try:
                response = self._client.post(
                    f"{self.config.base_url}/api/v1/organizations/{organization_id}/tracing/ingest",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.config.api_key}",
                    },
                )
                response.raise_for_status()
                data = response.json()

                return IngestResult(
                    accepted=data.get("accepted", len(traces)),
                    failed=data.get("failed", 0),
                    errors=data.get("errors"),
                )

            except Exception as e:
                last_error = e
                self._log(f"Trace send attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2**attempt)

        raise last_error or Exception("Failed to send traces")

    def track_call(self, call: LLMCallData) -> None:
        """Track a single LLM call.

        Args:
            call: The LLM call data to track
        """
        if call.timestamp is None:
            call.timestamp = datetime.utcnow()

        with self._buffer_lock:
            self._buffer.append(call)
            should_flush = len(self._buffer) >= self.config.batch_size

        if should_flush:
            self.flush()

    def track_calls(self, calls: List[LLMCallData]) -> None:
        """Track multiple LLM calls.

        Args:
            calls: List of LLM call data to track
        """
        now = datetime.utcnow()
        for call in calls:
            if call.timestamp is None:
                call.timestamp = now

        with self._buffer_lock:
            self._buffer.extend(calls)
            should_flush = len(self._buffer) >= self.config.batch_size

        if should_flush:
            self.flush()

    def flush(self) -> Optional[BatchResult]:
        """Flush the buffer immediately.

        Returns:
            BatchResult if calls were flushed, None otherwise
        """
        if self._is_flushing:
            return None

        with self._buffer_lock:
            if not self._buffer:
                return None
            calls = self._buffer.copy()
            self._buffer.clear()

        self._is_flushing = True
        try:
            result = self._send_batch(calls)
            self._log(f"Flushed {len(calls)} calls")
            return result
        except Exception as e:
            # On error, put calls back in buffer
            with self._buffer_lock:
                self._buffer = calls + self._buffer
            self._log(f"Flush failed: {e}")
            raise
        finally:
            self._is_flushing = False

    def shutdown(self) -> None:
        """Shutdown the client, flushing any remaining calls."""
        self._stop_flush_timer()
        if self._buffer:
            try:
                self.flush()
            except Exception as e:
                self._log(f"Error during shutdown flush: {e}")
        self._client.close()

    @property
    def buffer_size(self) -> int:
        """Get the current buffer size."""
        return len(self._buffer)

    def _send_batch(self, calls: List[LLMCallData]) -> BatchResult:
        """Send a batch of calls to the API."""
        payload = {"calls": [call.to_dict() for call in calls]}

        last_error: Optional[Exception] = None

        for attempt in range(self.config.max_retries):
            try:
                response = self._client.post(
                    f"{self.config.base_url}/api/v1/ingest/llm/batch",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.config.api_key}",
                    },
                )
                response.raise_for_status()
                data = response.json()

                return BatchResult(
                    tracked=data.get("tracked", len(calls)),
                    total_cost=data.get("total_cost", 0),
                    total_tokens=data.get("total_tokens", 0),
                    ids=data.get("ids", []),
                )

            except Exception as e:
                last_error = e
                self._log(f"Attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2**attempt)

        raise last_error or Exception("Failed to send batch")

    def _start_flush_timer(self) -> None:
        """Start the background flush timer."""

        def timer_callback():
            if self._buffer:
                try:
                    self.flush()
                except Exception as e:
                    self._log(f"Background flush error: {e}")
            self._start_flush_timer()

        self._flush_timer = threading.Timer(self.config.flush_interval_ms / 1000, timer_callback)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _stop_flush_timer(self) -> None:
        """Stop the background flush timer."""
        if self._flush_timer:
            self._flush_timer.cancel()
            self._flush_timer = None

    def _log(self, message: str) -> None:
        """Log a message if debug is enabled."""
        if self.config.debug:
            print(f"[Diagnyx] {message}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()
        return False
