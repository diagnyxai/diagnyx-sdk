"""Type definitions for Diagnyx SDK."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    COHERE = "cohere"
    MISTRAL = "mistral"
    GROQ = "groq"
    TOGETHER = "together"
    FIREWORKS = "fireworks"
    CUSTOM = "custom"


class CallStatus(str, Enum):
    """Status of an LLM call."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


@dataclass
class LLMCallData:
    """Data for an LLM call to track."""

    provider: LLMProvider
    model: str
    input_tokens: int
    output_tokens: int
    status: CallStatus
    latency_ms: Optional[int] = None
    ttft_ms: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    endpoint: Optional[str] = None
    project_id: Optional[str] = None
    environment: Optional[str] = None
    trace_id: Optional[str] = None
    user_identifier: Optional[str] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API request."""
        data = {
            "provider": self.provider.value
            if isinstance(self.provider, LLMProvider)
            else self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "status": self.status.value if isinstance(self.status, CallStatus) else self.status,
        }

        if self.latency_ms is not None:
            data["latency_ms"] = self.latency_ms
        if self.ttft_ms is not None:
            data["ttft_ms"] = self.ttft_ms
        if self.error_code:
            data["error_code"] = self.error_code
        if self.error_message:
            data["error_message"] = self.error_message
        if self.endpoint:
            data["endpoint"] = self.endpoint
        if self.project_id:
            data["project_id"] = self.project_id
        if self.environment:
            data["environment"] = self.environment
        if self.trace_id:
            data["trace_id"] = self.trace_id
        if self.user_identifier:
            data["user_identifier"] = self.user_identifier
        if self.timestamp:
            data["timestamp"] = self.timestamp.isoformat()

        return data


@dataclass
class TrackResult:
    """Result of tracking a call."""

    id: str
    cost_usd: float
    total_tokens: int


@dataclass
class BatchResult:
    """Result of tracking a batch of calls."""

    tracked: int
    total_cost: float
    total_tokens: int
    ids: List[str] = field(default_factory=list)


@dataclass
class DiagnyxConfig:
    """Configuration for the Diagnyx client."""

    api_key: str
    base_url: str = "https://api.diagnyx.io"
    batch_size: int = 100
    flush_interval_ms: int = 5000
    max_retries: int = 3
    debug: bool = False
