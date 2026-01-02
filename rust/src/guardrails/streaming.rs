//! Token-by-token streaming guardrail for real-time LLM output validation.
//!
//! This module provides the `StreamingGuardrail` struct for evaluating LLM output
//! tokens as they are generated, enabling early termination on policy violations.
//!
//! # Example
//!
//! ```rust,no_run
//! use diagnyx::guardrails::streaming::{StreamingGuardrail, StreamingGuardrailConfig};
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let config = StreamingGuardrailConfig::new("dx_...", "org_123", "proj_456");
//!     let guardrail = StreamingGuardrail::new(config);
//!
//!     // Start a session
//!     let session = guardrail.start_session(None).await?;
//!     println!("Session started: {}", session.session_id);
//!
//!     // Evaluate tokens
//!     for token in vec!["Hello", " ", "world", "!"] {
//!         match guardrail.evaluate(token, false).await {
//!             Ok(Some(filtered)) => print!("{}", filtered),
//!             Ok(None) => println!("Token blocked"),
//!             Err(e) => {
//!                 eprintln!("Error: {}", e);
//!                 break;
//!             }
//!         }
//!     }
//!
//!     // Complete the session
//!     let final_session = guardrail.complete_session().await?;
//!     println!("\nAllowed: {}", final_session.allowed);
//!
//!     Ok(())
//! }
//! ```

use crate::error::DiagnyxError;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;

/// Enforcement level for guardrail policies.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EnforcementLevel {
    Advisory,
    Warning,
    Blocking,
}

impl Default for EnforcementLevel {
    fn default() -> Self {
        EnforcementLevel::Advisory
    }
}

/// Details of a guardrail policy violation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Violation {
    pub policy_id: String,
    pub policy_name: String,
    pub policy_type: String,
    pub violation_type: String,
    pub message: String,
    pub severity: String,
    pub enforcement_level: EnforcementLevel,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<HashMap<String, serde_json::Value>>,
}

/// Error type for guardrail violations that require termination.
#[derive(Debug, Clone)]
pub struct ViolationError {
    pub violation: Violation,
    pub session: StreamingGuardrailSession,
}

impl std::fmt::Display for ViolationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Guardrail violation: {}", self.violation.message)
    }
}

impl std::error::Error for ViolationError {}

/// Configuration for the streaming guardrail.
#[derive(Debug, Clone)]
pub struct StreamingGuardrailConfig {
    pub api_key: String,
    pub organization_id: String,
    pub project_id: String,
    pub base_url: String,
    pub timeout_secs: u64,
    pub evaluate_every_n_tokens: i32,
    pub enable_early_termination: bool,
    pub debug: bool,
}

impl StreamingGuardrailConfig {
    /// Create a new configuration with required parameters.
    pub fn new(
        api_key: impl Into<String>,
        organization_id: impl Into<String>,
        project_id: impl Into<String>,
    ) -> Self {
        Self {
            api_key: api_key.into(),
            organization_id: organization_id.into(),
            project_id: project_id.into(),
            base_url: "https://api.diagnyx.io".to_string(),
            timeout_secs: 30,
            evaluate_every_n_tokens: 10,
            enable_early_termination: true,
            debug: false,
        }
    }

    /// Set the base URL for the API.
    pub fn base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = url.into();
        self
    }

    /// Set the timeout in seconds.
    pub fn timeout_secs(mut self, timeout: u64) -> Self {
        self.timeout_secs = timeout;
        self
    }

    /// Set how often to evaluate (every N tokens).
    pub fn evaluate_every_n_tokens(mut self, n: i32) -> Self {
        self.evaluate_every_n_tokens = n;
        self
    }

    /// Enable or disable early termination.
    pub fn enable_early_termination(mut self, enable: bool) -> Self {
        self.enable_early_termination = enable;
        self
    }

    /// Enable or disable debug logging.
    pub fn debug(mut self, debug: bool) -> Self {
        self.debug = debug;
        self
    }
}

/// Session state for streaming guardrail.
#[derive(Debug, Clone)]
pub struct StreamingGuardrailSession {
    pub session_id: String,
    pub organization_id: String,
    pub project_id: String,
    pub active_policies: Vec<String>,
    pub tokens_processed: i32,
    pub violations: Vec<Violation>,
    pub terminated: bool,
    pub termination_reason: Option<String>,
    pub allowed: bool,
    pub accumulated_text: String,
}

impl StreamingGuardrailSession {
    fn new(session_id: String, organization_id: String, project_id: String, active_policies: Vec<String>) -> Self {
        Self {
            session_id,
            organization_id,
            project_id,
            active_policies,
            tokens_processed: 0,
            violations: Vec::new(),
            terminated: false,
            termination_reason: None,
            allowed: true,
            accumulated_text: String::new(),
        }
    }
}

/// Internal response structures
#[derive(Debug, Deserialize)]
struct StartSessionResponse {
    #[serde(rename = "type")]
    event_type: String,
    #[serde(rename = "sessionId")]
    session_id: Option<String>,
    #[serde(rename = "activePolicies")]
    active_policies: Option<Vec<String>>,
    error: Option<String>,
}

#[derive(Debug, Deserialize)]
struct EvaluateResponse {
    #[serde(rename = "type")]
    event_type: String,
    #[serde(rename = "tokenIndex")]
    token_index: Option<i32>,
    #[serde(rename = "totalTokens")]
    total_tokens: Option<i32>,
    allowed: Option<bool>,
    reason: Option<String>,
    #[serde(rename = "blockingViolation")]
    blocking_violation: Option<ViolationData>,
    #[serde(rename = "policyId")]
    policy_id: Option<String>,
    #[serde(rename = "policyName")]
    policy_name: Option<String>,
    #[serde(rename = "policyType")]
    policy_type: Option<String>,
    #[serde(rename = "violationType")]
    violation_type: Option<String>,
    message: Option<String>,
    severity: Option<String>,
    #[serde(rename = "enforcementLevel")]
    enforcement_level: Option<String>,
    details: Option<HashMap<String, serde_json::Value>>,
    error: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ViolationData {
    #[serde(rename = "policyId")]
    policy_id: Option<String>,
    #[serde(rename = "policyName")]
    policy_name: Option<String>,
    #[serde(rename = "policyType")]
    policy_type: Option<String>,
    #[serde(rename = "violationType")]
    violation_type: Option<String>,
    message: Option<String>,
    severity: Option<String>,
    #[serde(rename = "enforcementLevel")]
    enforcement_level: Option<String>,
    details: Option<HashMap<String, serde_json::Value>>,
}

impl ViolationData {
    fn to_violation(&self) -> Violation {
        let level = self.enforcement_level.as_ref()
            .map(|s| match s.as_str() {
                "blocking" => EnforcementLevel::Blocking,
                "warning" => EnforcementLevel::Warning,
                _ => EnforcementLevel::Advisory,
            })
            .unwrap_or(EnforcementLevel::Advisory);

        Violation {
            policy_id: self.policy_id.clone().unwrap_or_default(),
            policy_name: self.policy_name.clone().unwrap_or_default(),
            policy_type: self.policy_type.clone().unwrap_or_default(),
            violation_type: self.violation_type.clone().unwrap_or_default(),
            message: self.message.clone().unwrap_or_default(),
            severity: self.severity.clone().unwrap_or_default(),
            enforcement_level: level,
            details: self.details.clone(),
        }
    }
}

#[derive(Debug, Serialize)]
struct StartSessionRequest {
    #[serde(rename = "projectId")]
    project_id: String,
    #[serde(rename = "evaluateEveryNTokens")]
    evaluate_every_n_tokens: i32,
    #[serde(rename = "enableEarlyTermination")]
    enable_early_termination: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    input: Option<String>,
}

#[derive(Debug, Serialize)]
struct EvaluateTokenRequest {
    #[serde(rename = "sessionId")]
    session_id: String,
    token: String,
    #[serde(rename = "tokenIndex")]
    token_index: i32,
    #[serde(rename = "isLast")]
    is_last: bool,
}

/// Token-by-token streaming guardrail for LLM output validation.
///
/// Provides real-time evaluation of LLM response tokens against configured
/// guardrail policies with support for early termination on blocking violations.
pub struct StreamingGuardrail {
    config: StreamingGuardrailConfig,
    http_client: Client,
    session: Arc<Mutex<Option<StreamingGuardrailSession>>>,
    token_index: Arc<Mutex<i32>>,
}

impl StreamingGuardrail {
    /// Create a new streaming guardrail client.
    pub fn new(config: StreamingGuardrailConfig) -> Self {
        let http_client = Client::builder()
            .timeout(Duration::from_secs(config.timeout_secs))
            .build()
            .expect("Failed to create HTTP client");

        Self {
            config,
            http_client,
            session: Arc::new(Mutex::new(None)),
            token_index: Arc::new(Mutex::new(0)),
        }
    }

    fn log(&self, message: &str) {
        if self.config.debug {
            println!("[DiagnyxGuardrails] {}", message);
        }
    }

    fn get_base_endpoint(&self) -> String {
        format!(
            "{}/api/v1/organizations/{}/guardrails",
            self.config.base_url.trim_end_matches('/'),
            self.config.organization_id
        )
    }

    /// Start a new streaming guardrail session.
    pub async fn start_session(&self, input: Option<&str>) -> Result<StreamingGuardrailSession, DiagnyxError> {
        let url = format!("{}/evaluate/stream/start", self.get_base_endpoint());

        let request = StartSessionRequest {
            project_id: self.config.project_id.clone(),
            evaluate_every_n_tokens: self.config.evaluate_every_n_tokens,
            enable_early_termination: self.config.enable_early_termination,
            input: input.map(|s| s.to_string()),
        };

        self.log(&format!("Starting session at {}", url));

        let response = self.http_client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("Authorization", format!("Bearer {}", self.config.api_key))
            .json(&request)
            .send()
            .await?;

        let status = response.status();
        if !status.is_success() {
            let message = response.text().await.unwrap_or_default();
            return Err(DiagnyxError::ApiError {
                status_code: status.as_u16(),
                message,
            });
        }

        let data: StartSessionResponse = response.json().await?;

        if data.event_type == "session_started" {
            let session_id = data.session_id.ok_or_else(|| {
                DiagnyxError::ConfigError("Missing session_id in response".to_string())
            })?;

            let session = StreamingGuardrailSession::new(
                session_id.clone(),
                self.config.organization_id.clone(),
                self.config.project_id.clone(),
                data.active_policies.unwrap_or_default(),
            );

            *self.session.lock().await = Some(session.clone());
            *self.token_index.lock().await = 0;

            self.log(&format!("Session started: {}", session_id));
            Ok(session)
        } else if data.event_type == "error" {
            Err(DiagnyxError::ApiError {
                status_code: 400,
                message: data.error.unwrap_or("Unknown error".to_string()),
            })
        } else {
            Err(DiagnyxError::ConfigError(format!(
                "Unexpected response type: {}",
                data.event_type
            )))
        }
    }

    /// Evaluate a token against guardrail policies.
    ///
    /// Returns `Ok(Some(token))` if the token is allowed, `Ok(None)` if blocked without error,
    /// or `Err(ViolationError)` if a blocking violation occurred.
    pub async fn evaluate(&self, token: &str, is_last: bool) -> Result<Option<String>, DiagnyxError> {
        self.evaluate_with_index(token, None, is_last).await
    }

    /// Evaluate a token with an explicit index.
    pub async fn evaluate_with_index(
        &self,
        token: &str,
        token_idx: Option<i32>,
        is_last: bool,
    ) -> Result<Option<String>, DiagnyxError> {
        let session_id = {
            let session = self.session.lock().await;
            session
                .as_ref()
                .ok_or_else(|| DiagnyxError::ConfigError("No active session".to_string()))?
                .session_id
                .clone()
        };

        let index = match token_idx {
            Some(i) => i,
            None => {
                let mut idx = self.token_index.lock().await;
                let current = *idx;
                *idx += 1;
                current
            }
        };

        // Update accumulated text
        {
            let mut session = self.session.lock().await;
            if let Some(ref mut s) = *session {
                s.accumulated_text.push_str(token);
            }
        }

        let url = format!("{}/evaluate/stream", self.get_base_endpoint());

        let request = EvaluateTokenRequest {
            session_id: session_id.clone(),
            token: token.to_string(),
            token_index: index,
            is_last,
        };

        let response = self.http_client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("Authorization", format!("Bearer {}", self.config.api_key))
            .header("Accept", "text/event-stream")
            .json(&request)
            .send()
            .await?;

        let status = response.status();
        if !status.is_success() {
            let message = response.text().await.unwrap_or_default();
            return Err(DiagnyxError::ApiError {
                status_code: status.as_u16(),
                message,
            });
        }

        let text = response.text().await?;
        let mut result: Option<String> = None;

        for line in text.lines() {
            if !line.starts_with("data: ") {
                continue;
            }

            let json_str = &line[6..];
            match serde_json::from_str::<EvaluateResponse>(json_str) {
                Ok(data) => {
                    match data.event_type.as_str() {
                        "token_allowed" => {
                            let mut session = self.session.lock().await;
                            if let Some(ref mut s) = *session {
                                s.tokens_processed = data.token_index.unwrap_or(0) + 1;
                            }
                            result = Some(token.to_string());
                        }
                        "violation_detected" => {
                            let violation = self.parse_violation_from_response(&data);
                            let mut session = self.session.lock().await;
                            if let Some(ref mut s) = *session {
                                s.violations.push(violation.clone());
                                if violation.enforcement_level == EnforcementLevel::Blocking {
                                    s.allowed = false;
                                }
                            }
                        }
                        "early_termination" => {
                            let violation = data.blocking_violation
                                .map(|v| v.to_violation())
                                .unwrap_or_else(|| self.parse_violation_from_response(&data));

                            let session = {
                                let mut session_guard = self.session.lock().await;
                                if let Some(ref mut s) = *session_guard {
                                    s.terminated = true;
                                    s.termination_reason = data.reason.clone();
                                    s.allowed = false;
                                }
                                session_guard.clone()
                            };

                            return Err(DiagnyxError::ViolationError(Box::new(ViolationError {
                                violation,
                                session: session.unwrap(),
                            })));
                        }
                        "session_complete" => {
                            let mut session = self.session.lock().await;
                            if let Some(ref mut s) = *session {
                                s.tokens_processed = data.total_tokens.unwrap_or(0);
                                s.allowed = data.allowed.unwrap_or(true);
                            }
                        }
                        "error" => {
                            self.log(&format!("Error: {}", data.error.unwrap_or_default()));
                        }
                        _ => {}
                    }
                }
                Err(e) => {
                    self.log(&format!("Failed to parse event: {}", e));
                }
            }
        }

        Ok(result)
    }

    /// Complete the current session.
    pub async fn complete_session(&self) -> Result<StreamingGuardrailSession, DiagnyxError> {
        let session_id = {
            let session = self.session.lock().await;
            session
                .as_ref()
                .ok_or_else(|| DiagnyxError::ConfigError("No active session".to_string()))?
                .session_id
                .clone()
        };

        let url = format!("{}/evaluate/stream/{}/complete", self.get_base_endpoint(), session_id);

        self.log(&format!("Completing session: {}", session_id));

        let response = self.http_client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.config.api_key))
            .header("Accept", "text/event-stream")
            .send()
            .await?;

        let status = response.status();
        if !status.is_success() {
            let message = response.text().await.unwrap_or_default();
            return Err(DiagnyxError::ApiError {
                status_code: status.as_u16(),
                message,
            });
        }

        let text = response.text().await?;

        for line in text.lines() {
            if !line.starts_with("data: ") {
                continue;
            }

            if let Ok(data) = serde_json::from_str::<EvaluateResponse>(&line[6..]) {
                if data.event_type == "session_complete" {
                    let mut session = self.session.lock().await;
                    if let Some(ref mut s) = *session {
                        s.tokens_processed = data.total_tokens.unwrap_or(0);
                        s.allowed = data.allowed.unwrap_or(true);
                    }
                }
            }
        }

        let session = self.session.lock().await.take();
        session.ok_or_else(|| DiagnyxError::ConfigError("No active session".to_string()))
    }

    /// Cancel the current session.
    pub async fn cancel_session(&self) -> Result<bool, DiagnyxError> {
        let session_id = {
            let session = self.session.lock().await;
            match session.as_ref() {
                Some(s) => s.session_id.clone(),
                None => return Ok(false),
            }
        };

        let url = format!("{}/evaluate/stream/{}", self.get_base_endpoint(), session_id);

        self.log(&format!("Cancelling session: {}", session_id));

        let response = self.http_client
            .delete(&url)
            .header("Authorization", format!("Bearer {}", self.config.api_key))
            .send()
            .await?;

        let status = response.status();
        if !status.is_success() {
            let message = response.text().await.unwrap_or_default();
            return Err(DiagnyxError::ApiError {
                status_code: status.as_u16(),
                message,
            });
        }

        #[derive(Deserialize)]
        struct CancelResponse {
            cancelled: Option<bool>,
        }

        let data: CancelResponse = response.json().await?;
        *self.session.lock().await = None;

        Ok(data.cancelled.unwrap_or(false))
    }

    /// Get the current session.
    pub async fn get_session(&self) -> Option<StreamingGuardrailSession> {
        self.session.lock().await.clone()
    }

    /// Check if there's an active session.
    pub async fn is_active(&self) -> bool {
        let session = self.session.lock().await;
        session.as_ref().map(|s| !s.terminated).unwrap_or(false)
    }

    fn parse_violation_from_response(&self, data: &EvaluateResponse) -> Violation {
        let level = data.enforcement_level.as_ref()
            .map(|s| match s.as_str() {
                "blocking" => EnforcementLevel::Blocking,
                "warning" => EnforcementLevel::Warning,
                _ => EnforcementLevel::Advisory,
            })
            .unwrap_or(EnforcementLevel::Advisory);

        Violation {
            policy_id: data.policy_id.clone().unwrap_or_default(),
            policy_name: data.policy_name.clone().unwrap_or_default(),
            policy_type: data.policy_type.clone().unwrap_or_default(),
            violation_type: data.violation_type.clone().unwrap_or_default(),
            message: data.message.clone().unwrap_or_default(),
            severity: data.severity.clone().unwrap_or_default(),
            enforcement_level: level,
            details: data.details.clone(),
        }
    }
}

/// Wrap an async token stream with guardrail protection.
///
/// Returns a stream that yields filtered tokens. If a blocking violation
/// is detected, the stream will end with an error.
pub async fn stream_with_guardrails<S>(
    config: StreamingGuardrailConfig,
    mut token_stream: S,
    input: Option<&str>,
) -> Result<impl futures::Stream<Item = Result<String, DiagnyxError>>, DiagnyxError>
where
    S: futures::Stream<Item = String> + Send + Unpin + 'static,
{
    use futures::StreamExt;
    use tokio::sync::mpsc;

    let guardrail = StreamingGuardrail::new(config);
    guardrail.start_session(input).await?;

    let (tx, rx) = mpsc::channel(100);
    let guardrail = Arc::new(guardrail);
    let guardrail_clone = Arc::clone(&guardrail);

    tokio::spawn(async move {
        while let Some(token) = token_stream.next().await {
            match guardrail_clone.evaluate(&token, false).await {
                Ok(Some(filtered)) => {
                    if tx.send(Ok(filtered)).await.is_err() {
                        break;
                    }
                }
                Ok(None) => {
                    // Token blocked but not a terminating violation
                }
                Err(e) => {
                    let _ = tx.send(Err(e)).await;
                    break;
                }
            }
        }

        if guardrail_clone.is_active().await {
            let _ = guardrail_clone.complete_session().await;
        }
    });

    Ok(tokio_stream::wrappers::ReceiverStream::new(rx))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_builder() {
        let config = StreamingGuardrailConfig::new("api-key", "org-1", "proj-1")
            .base_url("https://custom.api.com")
            .timeout_secs(60)
            .evaluate_every_n_tokens(5)
            .enable_early_termination(false)
            .debug(true);

        assert_eq!(config.api_key, "api-key");
        assert_eq!(config.organization_id, "org-1");
        assert_eq!(config.project_id, "proj-1");
        assert_eq!(config.base_url, "https://custom.api.com");
        assert_eq!(config.timeout_secs, 60);
        assert_eq!(config.evaluate_every_n_tokens, 5);
        assert!(!config.enable_early_termination);
        assert!(config.debug);
    }

    #[test]
    fn test_config_defaults() {
        let config = StreamingGuardrailConfig::new("api-key", "org-1", "proj-1");

        assert_eq!(config.base_url, "https://api.diagnyx.io");
        assert_eq!(config.timeout_secs, 30);
        assert_eq!(config.evaluate_every_n_tokens, 10);
        assert!(config.enable_early_termination);
        assert!(!config.debug);
    }

    #[test]
    fn test_enforcement_level_default() {
        assert_eq!(EnforcementLevel::default(), EnforcementLevel::Advisory);
    }

    #[test]
    fn test_violation_error_display() {
        let violation = Violation {
            policy_id: "pol-1".to_string(),
            policy_name: "Test Policy".to_string(),
            policy_type: "pii_detection".to_string(),
            violation_type: "pii_detected".to_string(),
            message: "PII detected in output".to_string(),
            severity: "high".to_string(),
            enforcement_level: EnforcementLevel::Blocking,
            details: None,
        };

        let session = StreamingGuardrailSession::new(
            "sess-123".to_string(),
            "org-1".to_string(),
            "proj-1".to_string(),
            vec![],
        );

        let error = ViolationError { violation, session };
        assert_eq!(
            error.to_string(),
            "Guardrail violation: PII detected in output"
        );
    }

    #[test]
    fn test_session_new() {
        let session = StreamingGuardrailSession::new(
            "sess-123".to_string(),
            "org-1".to_string(),
            "proj-1".to_string(),
            vec!["policy-1".to_string()],
        );

        assert_eq!(session.session_id, "sess-123");
        assert_eq!(session.organization_id, "org-1");
        assert_eq!(session.project_id, "proj-1");
        assert_eq!(session.active_policies.len(), 1);
        assert_eq!(session.tokens_processed, 0);
        assert!(session.violations.is_empty());
        assert!(!session.terminated);
        assert!(session.allowed);
        assert!(session.accumulated_text.is_empty());
    }
}
