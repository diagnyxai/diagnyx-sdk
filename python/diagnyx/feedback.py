"""
User Feedback Collection Module

Provides methods for collecting end-user feedback on LLM responses.
Feedback is linked to traces for analysis and fine-tuning.

Usage:
    from diagnyx import Diagnyx

    diagnyx = Diagnyx(api_key="...")

    # Submit thumbs up feedback
    diagnyx.feedback.thumbs_up(trace_id="trace_123")

    # Submit rating feedback
    diagnyx.feedback.rating(trace_id="trace_123", value=4)

    # Submit text feedback with tags
    diagnyx.feedback.text(
        trace_id="trace_123",
        comment="Great response!",
        tags=["accurate", "helpful"]
    )

    # Submit correction
    diagnyx.feedback.correction(
        trace_id="trace_123",
        correction="The capital of France is Paris, not Lyon.",
    )
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import httpx


class FeedbackType(str, Enum):
    """Types of feedback that can be submitted."""

    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    RATING = "rating"
    TEXT = "text"
    CORRECTION = "correction"
    FLAG = "flag"


class FeedbackSentiment(str, Enum):
    """Sentiment classification of feedback."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class Feedback:
    """Represents a feedback record."""

    id: str
    trace_id: str
    feedback_type: FeedbackType
    sentiment: FeedbackSentiment
    value: Optional[int] = None
    comment: Optional[str] = None
    correction: Optional[str] = None
    tags: List[str] = None
    metadata: Dict[str, Any] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: Optional[datetime] = None
    span_id: Optional[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class FeedbackSummary:
    """Summary analytics for feedback."""

    total_feedback: int
    positive_count: int
    negative_count: int
    neutral_count: int
    positive_rate: float
    average_rating: float
    feedback_by_type: Dict[str, int]
    feedback_by_tag: Dict[str, int]


class FeedbackClient:
    """
    Client for submitting and managing user feedback.

    Feedback is linked to traces and can be used for:
    - Monitoring user satisfaction
    - Identifying problematic responses
    - Collecting data for fine-tuning
    - Quality assurance
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.diagnyx.ai",
        organization_id: Optional[str] = None,
        project_id: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize the feedback client.

        Args:
            api_key: Diagnyx API key
            base_url: API base URL
            organization_id: Organization ID
            project_id: Project ID
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.organization_id = organization_id
        self.project_id = project_id
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def thumbs_up(
        self,
        trace_id: str,
        *,
        span_id: Optional[str] = None,
        comment: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Feedback:
        """
        Submit positive thumbs up feedback.

        Args:
            trace_id: The trace ID to attach feedback to
            span_id: Optional span ID for specific span feedback
            comment: Optional text comment
            tags: Optional tags for categorization
            user_id: Optional anonymized user identifier
            session_id: Optional session identifier
            metadata: Optional additional metadata

        Returns:
            The created Feedback object
        """
        return self._submit(
            trace_id=trace_id,
            feedback_type=FeedbackType.THUMBS_UP,
            span_id=span_id,
            comment=comment,
            tags=tags,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
        )

    def thumbs_down(
        self,
        trace_id: str,
        *,
        span_id: Optional[str] = None,
        comment: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Feedback:
        """
        Submit negative thumbs down feedback.

        Args:
            trace_id: The trace ID to attach feedback to
            span_id: Optional span ID for specific span feedback
            comment: Optional text comment explaining the issue
            tags: Optional tags for categorization (e.g., ["inaccurate", "off-topic"])
            user_id: Optional anonymized user identifier
            session_id: Optional session identifier
            metadata: Optional additional metadata

        Returns:
            The created Feedback object
        """
        return self._submit(
            trace_id=trace_id,
            feedback_type=FeedbackType.THUMBS_DOWN,
            span_id=span_id,
            comment=comment,
            tags=tags,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
        )

    def rating(
        self,
        trace_id: str,
        value: int,
        *,
        span_id: Optional[str] = None,
        comment: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Feedback:
        """
        Submit a numeric rating (1-5 stars).

        Args:
            trace_id: The trace ID to attach feedback to
            value: Rating value (1-5)
            span_id: Optional span ID for specific span feedback
            comment: Optional text comment
            tags: Optional tags for categorization
            user_id: Optional anonymized user identifier
            session_id: Optional session identifier
            metadata: Optional additional metadata

        Returns:
            The created Feedback object

        Raises:
            ValueError: If value is not between 1 and 5
        """
        if not 1 <= value <= 5:
            raise ValueError("Rating value must be between 1 and 5")

        return self._submit(
            trace_id=trace_id,
            feedback_type=FeedbackType.RATING,
            value=value,
            span_id=span_id,
            comment=comment,
            tags=tags,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
        )

    def text(
        self,
        trace_id: str,
        comment: str,
        *,
        span_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Feedback:
        """
        Submit text feedback/comment.

        Args:
            trace_id: The trace ID to attach feedback to
            comment: The text feedback
            span_id: Optional span ID for specific span feedback
            tags: Optional tags for categorization
            user_id: Optional anonymized user identifier
            session_id: Optional session identifier
            metadata: Optional additional metadata

        Returns:
            The created Feedback object
        """
        return self._submit(
            trace_id=trace_id,
            feedback_type=FeedbackType.TEXT,
            comment=comment,
            span_id=span_id,
            tags=tags,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
        )

    def correction(
        self,
        trace_id: str,
        correction: str,
        *,
        span_id: Optional[str] = None,
        comment: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Feedback:
        """
        Submit a correction for the response.

        Corrections are used for fine-tuning - they provide the "correct"
        response that should have been generated.

        Args:
            trace_id: The trace ID to attach feedback to
            correction: The corrected response text
            span_id: Optional span ID for specific span feedback
            comment: Optional comment explaining the correction
            tags: Optional tags for categorization
            user_id: Optional anonymized user identifier
            session_id: Optional session identifier
            metadata: Optional additional metadata

        Returns:
            The created Feedback object
        """
        return self._submit(
            trace_id=trace_id,
            feedback_type=FeedbackType.CORRECTION,
            correction=correction,
            span_id=span_id,
            comment=comment,
            tags=tags,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
        )

    def flag(
        self,
        trace_id: str,
        *,
        reason: Optional[str] = None,
        span_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Feedback:
        """
        Flag a response for review.

        Use this for responses that need human review (e.g., potentially
        harmful content, policy violations, etc.)

        Args:
            trace_id: The trace ID to flag
            reason: Optional reason for flagging
            span_id: Optional span ID for specific span
            tags: Optional tags (e.g., ["harmful", "policy-violation"])
            user_id: Optional anonymized user identifier
            session_id: Optional session identifier
            metadata: Optional additional metadata

        Returns:
            The created Feedback object
        """
        return self._submit(
            trace_id=trace_id,
            feedback_type=FeedbackType.FLAG,
            span_id=span_id,
            comment=reason,
            tags=tags,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
        )

    def _submit(
        self,
        trace_id: str,
        feedback_type: FeedbackType,
        *,
        value: Optional[int] = None,
        span_id: Optional[str] = None,
        comment: Optional[str] = None,
        correction: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Feedback:
        """
        Internal method to submit feedback.

        Args:
            trace_id: The trace ID
            feedback_type: Type of feedback
            value: Optional numeric value
            span_id: Optional span ID
            comment: Optional comment
            correction: Optional correction text
            tags: Optional tags
            user_id: Optional user ID
            session_id: Optional session ID
            metadata: Optional metadata

        Returns:
            The created Feedback object
        """
        payload = {
            "traceId": trace_id,
            "feedbackType": feedback_type.value,
        }

        if span_id:
            payload["spanId"] = span_id
        if value is not None:
            payload["value"] = value
        if comment:
            payload["comment"] = comment
        if correction:
            payload["correction"] = correction
        if tags:
            payload["tags"] = tags
        if user_id:
            payload["userId"] = user_id
        if session_id:
            payload["sessionId"] = session_id
        if metadata:
            payload["metadata"] = metadata

        response = self._client.post("/api/v1/feedback", json=payload)
        response.raise_for_status()

        data = response.json()

        return Feedback(
            id=data.get("id"),
            trace_id=trace_id,
            feedback_type=feedback_type,
            sentiment=FeedbackSentiment(data.get("sentiment", "neutral")),
            value=value,
            comment=comment,
            correction=correction,
            tags=tags or [],
            metadata=metadata or {},
            user_id=user_id,
            session_id=session_id,
            span_id=span_id,
            created_at=datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00"))
            if "createdAt" in data
            else None,
        )

    def get_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> FeedbackSummary:
        """
        Get feedback analytics summary.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            FeedbackSummary with analytics data
        """
        params = {}
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()

        response = self._client.get("/api/v1/feedback/summary", params=params)
        response.raise_for_status()

        data = response.json()

        return FeedbackSummary(
            total_feedback=data["totalFeedback"],
            positive_count=data["positiveCount"],
            negative_count=data["negativeCount"],
            neutral_count=data["neutralCount"],
            positive_rate=data["positiveRate"],
            average_rating=data["averageRating"],
            feedback_by_type=data["feedbackByType"],
            feedback_by_tag=data["feedbackByTag"],
        )

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        feedback_type: Optional[FeedbackType] = None,
        sentiment: Optional[FeedbackSentiment] = None,
        tag: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Feedback]:
        """
        List feedback with filters.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            feedback_type: Filter by feedback type
            sentiment: Filter by sentiment
            tag: Filter by tag
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            List of Feedback objects
        """
        params = {"limit": limit, "offset": offset}
        if feedback_type:
            params["feedbackType"] = feedback_type.value
        if sentiment:
            params["sentiment"] = sentiment.value
        if tag:
            params["tag"] = tag
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()

        response = self._client.get("/api/v1/feedback", params=params)
        response.raise_for_status()

        data = response.json()

        return [
            Feedback(
                id=item["id"],
                trace_id=item["traceId"],
                feedback_type=FeedbackType(item["feedbackType"]),
                sentiment=FeedbackSentiment(item["sentiment"]),
                value=item.get("value"),
                comment=item.get("comment"),
                correction=item.get("correction"),
                tags=item.get("tags", []),
                metadata=item.get("metadata", {}),
                user_id=item.get("userId"),
                session_id=item.get("sessionId"),
                span_id=item.get("spanId"),
                created_at=datetime.fromisoformat(
                    item["createdAt"].replace("Z", "+00:00")
                )
                if "createdAt" in item
                else None,
            )
            for item in data.get("data", [])
        ]

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
