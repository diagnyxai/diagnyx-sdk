//! Feedback Module for Diagnyx Rust SDK
//!
//! Provides methods for collecting end-user feedback on LLM responses.
//! Feedback is linked to traces for analysis and fine-tuning.
//!
//! # Example
//!
//! ```rust,no_run
//! use diagnyx::feedback::{FeedbackClient, FeedbackOptions};
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let client = FeedbackClient::new("dx_api_key", "org-123");
//!
//!     // Submit thumbs up
//!     client.thumbs_up("trace_123", None).await?;
//!
//!     // Submit rating
//!     client.rating("trace_123", 4, None).await?;
//!
//!     // Submit with options
//!     let options = FeedbackOptions::builder()
//!         .tags(vec!["accurate", "helpful"])
//!         .user_id("user_123")
//!         .build();
//!     client.text("trace_123", "Great response!", Some(options)).await?;
//!
//!     Ok(())
//! }
//! ```

use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Duration;

use crate::error::DiagnyxError;

/// Types of feedback that can be submitted.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FeedbackType {
    ThumbsUp,
    ThumbsDown,
    Rating,
    Text,
    Correction,
    Flag,
}

/// Sentiment classification of feedback.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FeedbackSentiment {
    Positive,
    Negative,
    Neutral,
}

/// Represents a feedback record.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Feedback {
    pub id: String,
    pub trace_id: String,
    pub feedback_type: FeedbackType,
    pub sentiment: FeedbackSentiment,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rating: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub comment: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub correction: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub span_id: Option<String>,
    pub created_at: DateTime<Utc>,
}

/// Feedback analytics summary.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FeedbackSummary {
    pub total_feedback: i32,
    pub positive_count: i32,
    pub negative_count: i32,
    pub neutral_count: i32,
    pub positive_rate: f64,
    pub average_rating: f64,
    pub feedback_by_type: HashMap<String, i32>,
    pub feedback_by_tag: HashMap<String, i32>,
}

/// Options for feedback submission.
#[derive(Debug, Clone, Default)]
pub struct FeedbackOptions {
    pub span_id: Option<String>,
    pub comment: Option<String>,
    pub tags: Option<Vec<String>>,
    pub metadata: Option<HashMap<String, serde_json::Value>>,
    pub user_id: Option<String>,
    pub session_id: Option<String>,
}

impl FeedbackOptions {
    pub fn builder() -> FeedbackOptionsBuilder {
        FeedbackOptionsBuilder::default()
    }
}

/// Builder for FeedbackOptions.
#[derive(Debug, Default)]
pub struct FeedbackOptionsBuilder {
    span_id: Option<String>,
    comment: Option<String>,
    tags: Option<Vec<String>>,
    metadata: Option<HashMap<String, serde_json::Value>>,
    user_id: Option<String>,
    session_id: Option<String>,
}

impl FeedbackOptionsBuilder {
    pub fn span_id(mut self, span_id: impl Into<String>) -> Self {
        self.span_id = Some(span_id.into());
        self
    }

    pub fn comment(mut self, comment: impl Into<String>) -> Self {
        self.comment = Some(comment.into());
        self
    }

    pub fn tags(mut self, tags: Vec<impl Into<String>>) -> Self {
        self.tags = Some(tags.into_iter().map(|t| t.into()).collect());
        self
    }

    pub fn metadata(mut self, metadata: HashMap<String, serde_json::Value>) -> Self {
        self.metadata = Some(metadata);
        self
    }

    pub fn user_id(mut self, user_id: impl Into<String>) -> Self {
        self.user_id = Some(user_id.into());
        self
    }

    pub fn session_id(mut self, session_id: impl Into<String>) -> Self {
        self.session_id = Some(session_id.into());
        self
    }

    pub fn build(self) -> FeedbackOptions {
        FeedbackOptions {
            span_id: self.span_id,
            comment: self.comment,
            tags: self.tags,
            metadata: self.metadata,
            user_id: self.user_id,
            session_id: self.session_id,
        }
    }
}

/// Options for listing feedback.
#[derive(Debug, Clone, Default)]
pub struct ListFeedbackOptions {
    pub limit: Option<i32>,
    pub offset: Option<i32>,
    pub feedback_type: Option<FeedbackType>,
    pub sentiment: Option<FeedbackSentiment>,
    pub tag: Option<String>,
    pub start_date: Option<DateTime<Utc>>,
    pub end_date: Option<DateTime<Utc>>,
}

/// Result of listing feedback.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeedbackListResult {
    pub data: Vec<Feedback>,
    pub total: i32,
    pub limit: i32,
    pub offset: i32,
}

/// Configuration for FeedbackClient.
#[derive(Debug, Clone)]
pub struct FeedbackClientConfig {
    pub api_key: String,
    pub organization_id: String,
    pub base_url: String,
    pub max_retries: usize,
    pub debug: bool,
}

impl FeedbackClientConfig {
    pub fn new(api_key: impl Into<String>, organization_id: impl Into<String>) -> Self {
        Self {
            api_key: api_key.into(),
            organization_id: organization_id.into(),
            base_url: "https://api.diagnyx.io".to_string(),
            max_retries: 3,
            debug: false,
        }
    }

    pub fn base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = url.into();
        self
    }

    pub fn max_retries(mut self, retries: usize) -> Self {
        self.max_retries = retries;
        self
    }

    pub fn debug(mut self, debug: bool) -> Self {
        self.debug = debug;
        self
    }
}

/// Client for submitting and managing user feedback.
pub struct FeedbackClient {
    config: FeedbackClientConfig,
    http_client: Client,
}

impl FeedbackClient {
    /// Create a new FeedbackClient with default settings.
    pub fn new(api_key: impl Into<String>, organization_id: impl Into<String>) -> Self {
        Self::with_config(FeedbackClientConfig::new(api_key, organization_id))
    }

    /// Create a new FeedbackClient with custom configuration.
    pub fn with_config(config: FeedbackClientConfig) -> Self {
        Self {
            config,
            http_client: Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("Failed to create HTTP client"),
        }
    }

    /// Submit positive thumbs up feedback.
    pub async fn thumbs_up(
        &self,
        trace_id: &str,
        options: Option<FeedbackOptions>,
    ) -> Result<Feedback, DiagnyxError> {
        self.submit(trace_id, FeedbackType::ThumbsUp, None, None, None, options)
            .await
    }

    /// Submit negative thumbs down feedback.
    pub async fn thumbs_down(
        &self,
        trace_id: &str,
        options: Option<FeedbackOptions>,
    ) -> Result<Feedback, DiagnyxError> {
        self.submit(trace_id, FeedbackType::ThumbsDown, None, None, None, options)
            .await
    }

    /// Submit a numeric rating (1-5).
    pub async fn rating(
        &self,
        trace_id: &str,
        value: i32,
        options: Option<FeedbackOptions>,
    ) -> Result<Feedback, DiagnyxError> {
        if value < 1 || value > 5 {
            return Err(DiagnyxError::ConfigError(
                "Rating value must be between 1 and 5".to_string(),
            ));
        }
        self.submit(trace_id, FeedbackType::Rating, Some(value), None, None, options)
            .await
    }

    /// Submit text feedback.
    pub async fn text(
        &self,
        trace_id: &str,
        comment: &str,
        options: Option<FeedbackOptions>,
    ) -> Result<Feedback, DiagnyxError> {
        self.submit(
            trace_id,
            FeedbackType::Text,
            None,
            Some(comment.to_string()),
            None,
            options,
        )
        .await
    }

    /// Submit a correction for fine-tuning.
    pub async fn correction(
        &self,
        trace_id: &str,
        correction: &str,
        options: Option<FeedbackOptions>,
    ) -> Result<Feedback, DiagnyxError> {
        self.submit(
            trace_id,
            FeedbackType::Correction,
            None,
            None,
            Some(correction.to_string()),
            options,
        )
        .await
    }

    /// Flag a response for review.
    pub async fn flag(
        &self,
        trace_id: &str,
        reason: Option<&str>,
        options: Option<FeedbackOptions>,
    ) -> Result<Feedback, DiagnyxError> {
        self.submit(
            trace_id,
            FeedbackType::Flag,
            None,
            reason.map(|s| s.to_string()),
            None,
            options,
        )
        .await
    }

    async fn submit(
        &self,
        trace_id: &str,
        feedback_type: FeedbackType,
        rating: Option<i32>,
        comment: Option<String>,
        correction: Option<String>,
        options: Option<FeedbackOptions>,
    ) -> Result<Feedback, DiagnyxError> {
        let options = options.unwrap_or_default();

        let mut payload = serde_json::json!({
            "traceId": trace_id,
            "feedbackType": feedback_type,
        });

        if let Some(span_id) = &options.span_id {
            payload["spanId"] = serde_json::Value::String(span_id.clone());
        }
        if let Some(r) = rating {
            payload["rating"] = serde_json::Value::Number(r.into());
        }
        if let Some(c) = comment.or(options.comment) {
            payload["comment"] = serde_json::Value::String(c);
        }
        if let Some(c) = correction {
            payload["correction"] = serde_json::Value::String(c);
        }
        if let Some(tags) = &options.tags {
            payload["tags"] = serde_json::json!(tags);
        }
        if let Some(metadata) = &options.metadata {
            payload["metadata"] = serde_json::json!(metadata);
        }
        if let Some(user_id) = &options.user_id {
            payload["userId"] = serde_json::Value::String(user_id.clone());
        }
        if let Some(session_id) = &options.session_id {
            payload["sessionId"] = serde_json::Value::String(session_id.clone());
        }

        let response: Feedback = self.request("POST", "/api/v1/feedback", Some(payload)).await?;
        Ok(response)
    }

    /// List feedback with filters.
    pub async fn list(
        &self,
        options: Option<ListFeedbackOptions>,
    ) -> Result<FeedbackListResult, DiagnyxError> {
        let options = options.unwrap_or_default();

        let mut query_params = Vec::new();
        if let Some(limit) = options.limit {
            query_params.push(format!("limit={}", limit));
        }
        if let Some(offset) = options.offset {
            query_params.push(format!("offset={}", offset));
        }
        if let Some(ft) = options.feedback_type {
            query_params.push(format!("feedbackType={:?}", ft).to_lowercase());
        }
        if let Some(s) = options.sentiment {
            query_params.push(format!("sentiment={:?}", s).to_lowercase());
        }
        if let Some(tag) = &options.tag {
            query_params.push(format!("tag={}", tag));
        }
        if let Some(start) = options.start_date {
            query_params.push(format!("startDate={}", start.to_rfc3339()));
        }
        if let Some(end) = options.end_date {
            query_params.push(format!("endDate={}", end.to_rfc3339()));
        }

        let mut path = format!(
            "/api/v1/organizations/{}/feedback",
            self.config.organization_id
        );
        if !query_params.is_empty() {
            path.push('?');
            path.push_str(&query_params.join("&"));
        }

        self.request("GET", &path, None).await
    }

    /// Get feedback summary/analytics.
    pub async fn get_summary(
        &self,
        start_date: Option<DateTime<Utc>>,
        end_date: Option<DateTime<Utc>>,
    ) -> Result<FeedbackSummary, DiagnyxError> {
        let mut query_params = Vec::new();
        if let Some(start) = start_date {
            query_params.push(format!("startDate={}", start.to_rfc3339()));
        }
        if let Some(end) = end_date {
            query_params.push(format!("endDate={}", end.to_rfc3339()));
        }

        let mut path = format!(
            "/api/v1/organizations/{}/feedback/analytics",
            self.config.organization_id
        );
        if !query_params.is_empty() {
            path.push('?');
            path.push_str(&query_params.join("&"));
        }

        self.request("GET", &path, None).await
    }

    /// Get feedback for a specific trace.
    pub async fn get_for_trace(&self, trace_id: &str) -> Result<Vec<Feedback>, DiagnyxError> {
        let path = format!(
            "/api/v1/organizations/{}/feedback/trace/{}",
            self.config.organization_id, trace_id
        );
        self.request("GET", &path, None).await
    }

    async fn request<T: serde::de::DeserializeOwned>(
        &self,
        method: &str,
        path: &str,
        body: Option<serde_json::Value>,
    ) -> Result<T, DiagnyxError> {
        let url = format!("{}{}", self.config.base_url, path);
        let mut last_error = None;

        for attempt in 0..self.config.max_retries {
            let mut request = match method {
                "POST" => self.http_client.post(&url),
                "GET" => self.http_client.get(&url),
                _ => return Err(DiagnyxError::ConfigError(format!("Unknown method: {}", method))),
            };

            request = request
                .header("Content-Type", "application/json")
                .header("Authorization", format!("Bearer {}", self.config.api_key));

            if let Some(ref b) = body {
                request = request.json(b);
            }

            match request.send().await {
                Ok(response) => {
                    let status = response.status();
                    if status.is_success() {
                        return response.json().await.map_err(|e| {
                            DiagnyxError::ConfigError(format!("Failed to parse response: {}", e))
                        });
                    }

                    let message = response.text().await.unwrap_or_default();
                    last_error = Some(DiagnyxError::ApiError {
                        status_code: status.as_u16(),
                        message,
                    });

                    if status.is_client_error() {
                        break;
                    }
                }
                Err(e) => {
                    last_error = Some(DiagnyxError::HttpError(e));
                }
            }

            if attempt < self.config.max_retries - 1 {
                tokio::time::sleep(Duration::from_secs(2u64.pow(attempt as u32))).await;
            }
        }

        Err(last_error.unwrap_or(DiagnyxError::MaxRetriesExceeded))
    }
}
