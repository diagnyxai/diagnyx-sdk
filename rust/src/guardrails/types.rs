//! Type definitions for streaming guardrails.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Event types for streaming guardrail evaluation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StreamingEventType {
    SessionStarted,
    TokenAllowed,
    ViolationDetected,
    EarlyTermination,
    SessionComplete,
    Error,
}

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

/// Represents a guardrail violation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardrailViolation {
    pub policy_id: String,
    pub policy_type: String,
    pub message: String,
    pub severity: EnforcementLevel,
    pub details: Option<HashMap<String, serde_json::Value>>,
}

/// Session started event data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionStartedData {
    pub session_id: String,
    pub organization_id: String,
    pub project_id: String,
    pub active_policies: Vec<String>,
}

/// Token allowed event data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenAllowedData {
    pub session_id: String,
    pub token: String,
    pub tokens_processed: i32,
}

/// Violation detected event data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ViolationDetectedData {
    pub session_id: String,
    pub violation: GuardrailViolation,
    pub tokens_processed: i32,
}

/// Early termination event data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EarlyTerminationData {
    pub session_id: String,
    pub reason: String,
    pub violation: GuardrailViolation,
    pub tokens_processed: i32,
}

/// Session complete event data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionCompleteData {
    pub session_id: String,
    pub total_tokens: i32,
    pub violations: Vec<GuardrailViolation>,
    pub allowed: bool,
}

/// Error event data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorData {
    pub session_id: Option<String>,
    pub error: String,
    pub code: Option<String>,
}

/// Streaming event from guardrail evaluation.
#[derive(Debug, Clone)]
pub enum StreamingEvent {
    SessionStarted(SessionStartedData),
    TokenAllowed(TokenAllowedData),
    ViolationDetected(ViolationDetectedData),
    EarlyTermination(EarlyTerminationData),
    SessionComplete(SessionCompleteData),
    Error(ErrorData),
}

impl StreamingEvent {
    /// Get the event type.
    pub fn event_type(&self) -> StreamingEventType {
        match self {
            StreamingEvent::SessionStarted(_) => StreamingEventType::SessionStarted,
            StreamingEvent::TokenAllowed(_) => StreamingEventType::TokenAllowed,
            StreamingEvent::ViolationDetected(_) => StreamingEventType::ViolationDetected,
            StreamingEvent::EarlyTermination(_) => StreamingEventType::EarlyTermination,
            StreamingEvent::SessionComplete(_) => StreamingEventType::SessionComplete,
            StreamingEvent::Error(_) => StreamingEventType::Error,
        }
    }

    /// Get the session ID if available.
    pub fn session_id(&self) -> Option<&str> {
        match self {
            StreamingEvent::SessionStarted(data) => Some(&data.session_id),
            StreamingEvent::TokenAllowed(data) => Some(&data.session_id),
            StreamingEvent::ViolationDetected(data) => Some(&data.session_id),
            StreamingEvent::EarlyTermination(data) => Some(&data.session_id),
            StreamingEvent::SessionComplete(data) => Some(&data.session_id),
            StreamingEvent::Error(data) => data.session_id.as_deref(),
        }
    }

    /// Parse a streaming event from SSE data.
    pub fn from_sse(event_type: &str, data: &str) -> Result<Self, serde_json::Error> {
        match event_type {
            "session_started" => {
                let data: SessionStartedData = serde_json::from_str(data)?;
                Ok(StreamingEvent::SessionStarted(data))
            }
            "token_allowed" => {
                let data: TokenAllowedData = serde_json::from_str(data)?;
                Ok(StreamingEvent::TokenAllowed(data))
            }
            "violation_detected" => {
                let data: ViolationDetectedData = serde_json::from_str(data)?;
                Ok(StreamingEvent::ViolationDetected(data))
            }
            "early_termination" => {
                let data: EarlyTerminationData = serde_json::from_str(data)?;
                Ok(StreamingEvent::EarlyTermination(data))
            }
            "session_complete" => {
                let data: SessionCompleteData = serde_json::from_str(data)?;
                Ok(StreamingEvent::SessionComplete(data))
            }
            "error" => {
                let data: ErrorData = serde_json::from_str(data)?;
                Ok(StreamingEvent::Error(data))
            }
            _ => {
                // Unknown event type, treat as error
                Ok(StreamingEvent::Error(ErrorData {
                    session_id: None,
                    error: format!("Unknown event type: {}", event_type),
                    code: Some("unknown_event".to_string()),
                }))
            }
        }
    }
}

/// Guardrail session state.
#[derive(Debug, Clone)]
pub struct GuardrailSession {
    pub session_id: String,
    pub organization_id: String,
    pub project_id: String,
    pub active_policies: Vec<String>,
    pub tokens_processed: i32,
    pub violations: Vec<GuardrailViolation>,
    pub terminated: bool,
    pub termination_reason: Option<String>,
    pub allowed: bool,
}

impl GuardrailSession {
    /// Create a new session from session started data.
    pub fn new(data: SessionStartedData) -> Self {
        Self {
            session_id: data.session_id,
            organization_id: data.organization_id,
            project_id: data.project_id,
            active_policies: data.active_policies,
            tokens_processed: 0,
            violations: Vec::new(),
            terminated: false,
            termination_reason: None,
            allowed: true,
        }
    }

    /// Update session state from a streaming event.
    pub fn update(&mut self, event: &StreamingEvent) {
        match event {
            StreamingEvent::TokenAllowed(data) => {
                self.tokens_processed = data.tokens_processed;
            }
            StreamingEvent::ViolationDetected(data) => {
                self.tokens_processed = data.tokens_processed;
                self.violations.push(data.violation.clone());
            }
            StreamingEvent::EarlyTermination(data) => {
                self.tokens_processed = data.tokens_processed;
                self.violations.push(data.violation.clone());
                self.terminated = true;
                self.termination_reason = Some(data.reason.clone());
                self.allowed = false;
            }
            StreamingEvent::SessionComplete(data) => {
                self.tokens_processed = data.total_tokens;
                self.violations = data.violations.clone();
                self.allowed = data.allowed;
            }
            _ => {}
        }
    }
}

/// Configuration for the streaming guardrails client.
#[derive(Debug, Clone)]
pub struct StreamingGuardrailsConfig {
    pub api_key: String,
    pub organization_id: String,
    pub project_id: String,
    pub base_url: String,
    pub timeout_secs: u64,
    pub evaluate_every_n_tokens: i32,
    pub enable_early_termination: bool,
    pub debug: bool,
}

impl StreamingGuardrailsConfig {
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

/// Request body for starting a streaming session.
#[derive(Debug, Serialize)]
pub(crate) struct StartSessionRequest {
    pub organization_id: String,
    pub project_id: String,
    pub input: Option<String>,
    pub evaluate_every_n_tokens: i32,
    pub enable_early_termination: bool,
}

/// Request body for evaluating a token.
#[derive(Debug, Serialize)]
pub(crate) struct EvaluateTokenRequest {
    pub session_id: String,
    pub token: String,
}

/// Request body for completing a session.
#[derive(Debug, Serialize)]
pub(crate) struct CompleteSessionRequest {
    pub session_id: String,
}

/// Request body for cancelling a session.
#[derive(Debug, Serialize)]
pub(crate) struct CancelSessionRequest {
    pub session_id: String,
    pub reason: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_streaming_event_type_serialization() {
        let event_type = StreamingEventType::SessionStarted;
        let json = serde_json::to_string(&event_type).unwrap();
        assert_eq!(json, "\"session_started\"");

        let event_type = StreamingEventType::EarlyTermination;
        let json = serde_json::to_string(&event_type).unwrap();
        assert_eq!(json, "\"early_termination\"");
    }

    #[test]
    fn test_enforcement_level_serialization() {
        let level = EnforcementLevel::Blocking;
        let json = serde_json::to_string(&level).unwrap();
        assert_eq!(json, "\"blocking\"");
    }

    #[test]
    fn test_enforcement_level_default() {
        let level = EnforcementLevel::default();
        assert_eq!(level, EnforcementLevel::Advisory);
    }

    #[test]
    fn test_streaming_event_from_sse_session_started() {
        let data = r#"{"session_id":"sess-123","organization_id":"org-1","project_id":"proj-1","active_policies":["policy-1"]}"#;
        let event = StreamingEvent::from_sse("session_started", data).unwrap();

        match event {
            StreamingEvent::SessionStarted(data) => {
                assert_eq!(data.session_id, "sess-123");
                assert_eq!(data.organization_id, "org-1");
                assert_eq!(data.project_id, "proj-1");
                assert_eq!(data.active_policies.len(), 1);
            }
            _ => panic!("Expected SessionStarted event"),
        }
    }

    #[test]
    fn test_streaming_event_from_sse_token_allowed() {
        let data = r#"{"session_id":"sess-123","token":"hello","tokens_processed":5}"#;
        let event = StreamingEvent::from_sse("token_allowed", data).unwrap();

        match event {
            StreamingEvent::TokenAllowed(data) => {
                assert_eq!(data.session_id, "sess-123");
                assert_eq!(data.token, "hello");
                assert_eq!(data.tokens_processed, 5);
            }
            _ => panic!("Expected TokenAllowed event"),
        }
    }

    #[test]
    fn test_streaming_event_from_sse_violation_detected() {
        let data = r#"{"session_id":"sess-123","violation":{"policy_id":"pol-1","policy_type":"pii_detection","message":"PII detected","severity":"warning","details":null},"tokens_processed":10}"#;
        let event = StreamingEvent::from_sse("violation_detected", data).unwrap();

        match event {
            StreamingEvent::ViolationDetected(data) => {
                assert_eq!(data.session_id, "sess-123");
                assert_eq!(data.violation.policy_id, "pol-1");
                assert_eq!(data.violation.severity, EnforcementLevel::Warning);
            }
            _ => panic!("Expected ViolationDetected event"),
        }
    }

    #[test]
    fn test_streaming_event_event_type() {
        let event = StreamingEvent::SessionStarted(SessionStartedData {
            session_id: "sess-123".to_string(),
            organization_id: "org-1".to_string(),
            project_id: "proj-1".to_string(),
            active_policies: vec![],
        });
        assert_eq!(event.event_type(), StreamingEventType::SessionStarted);
    }

    #[test]
    fn test_streaming_event_session_id() {
        let event = StreamingEvent::TokenAllowed(TokenAllowedData {
            session_id: "sess-123".to_string(),
            token: "test".to_string(),
            tokens_processed: 1,
        });
        assert_eq!(event.session_id(), Some("sess-123"));
    }

    #[test]
    fn test_guardrail_session_new() {
        let data = SessionStartedData {
            session_id: "sess-123".to_string(),
            organization_id: "org-1".to_string(),
            project_id: "proj-1".to_string(),
            active_policies: vec!["policy-1".to_string()],
        };
        let session = GuardrailSession::new(data);

        assert_eq!(session.session_id, "sess-123");
        assert_eq!(session.tokens_processed, 0);
        assert!(session.violations.is_empty());
        assert!(!session.terminated);
        assert!(session.allowed);
    }

    #[test]
    fn test_guardrail_session_update() {
        let data = SessionStartedData {
            session_id: "sess-123".to_string(),
            organization_id: "org-1".to_string(),
            project_id: "proj-1".to_string(),
            active_policies: vec![],
        };
        let mut session = GuardrailSession::new(data);

        let event = StreamingEvent::TokenAllowed(TokenAllowedData {
            session_id: "sess-123".to_string(),
            token: "hello".to_string(),
            tokens_processed: 5,
        });
        session.update(&event);
        assert_eq!(session.tokens_processed, 5);

        let violation = GuardrailViolation {
            policy_id: "pol-1".to_string(),
            policy_type: "pii_detection".to_string(),
            message: "PII detected".to_string(),
            severity: EnforcementLevel::Warning,
            details: None,
        };
        let event = StreamingEvent::ViolationDetected(ViolationDetectedData {
            session_id: "sess-123".to_string(),
            violation,
            tokens_processed: 10,
        });
        session.update(&event);
        assert_eq!(session.tokens_processed, 10);
        assert_eq!(session.violations.len(), 1);
    }

    #[test]
    fn test_streaming_guardrails_config_defaults() {
        let config = StreamingGuardrailsConfig::new("api-key", "org-1", "proj-1");

        assert_eq!(config.api_key, "api-key");
        assert_eq!(config.organization_id, "org-1");
        assert_eq!(config.project_id, "proj-1");
        assert_eq!(config.base_url, "https://api.diagnyx.io");
        assert_eq!(config.timeout_secs, 30);
        assert_eq!(config.evaluate_every_n_tokens, 10);
        assert!(config.enable_early_termination);
        assert!(!config.debug);
    }

    #[test]
    fn test_streaming_guardrails_config_builder() {
        let config = StreamingGuardrailsConfig::new("api-key", "org-1", "proj-1")
            .base_url("https://custom.api.com")
            .timeout_secs(60)
            .evaluate_every_n_tokens(5)
            .enable_early_termination(false)
            .debug(true);

        assert_eq!(config.base_url, "https://custom.api.com");
        assert_eq!(config.timeout_secs, 60);
        assert_eq!(config.evaluate_every_n_tokens, 5);
        assert!(!config.enable_early_termination);
        assert!(config.debug);
    }
}
