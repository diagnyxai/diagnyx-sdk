//! Streaming guardrails client for real-time token validation.

use crate::error::DiagnyxError;
use crate::guardrails::types::{
    CancelSessionRequest, CompleteSessionRequest, EvaluateTokenRequest, GuardrailSession,
    GuardrailViolation, SessionStartedData, StartSessionRequest, StreamingEvent,
    StreamingGuardrailsConfig,
};
use reqwest::Client;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use tokio::sync::Mutex;

/// Error type for guardrail violations that require termination.
#[derive(Debug, Clone)]
pub struct GuardrailViolationError {
    pub violation: GuardrailViolation,
    pub session: GuardrailSession,
}

impl std::fmt::Display for GuardrailViolationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Guardrail violation: {}", self.violation.message)
    }
}

impl std::error::Error for GuardrailViolationError {}

/// Streaming guardrails client for real-time LLM output validation.
pub struct StreamingGuardrails {
    config: StreamingGuardrailsConfig,
    http_client: Client,
    session: Arc<Mutex<Option<GuardrailSession>>>,
}

impl StreamingGuardrails {
    /// Create a new streaming guardrails client.
    pub fn new(config: StreamingGuardrailsConfig) -> Self {
        Self {
            http_client: Client::builder()
                .timeout(Duration::from_secs(config.timeout_secs))
                .build()
                .expect("Failed to create HTTP client"),
            config,
            session: Arc::new(Mutex::new(None)),
        }
    }

    /// Start a new streaming evaluation session.
    pub async fn start_session(&self, input: Option<&str>) -> Result<GuardrailSession, DiagnyxError> {
        let url = format!("{}/api/v1/guardrails/streaming/start", self.config.base_url);

        let request = StartSessionRequest {
            organization_id: self.config.organization_id.clone(),
            project_id: self.config.project_id.clone(),
            input: input.map(|s| s.to_string()),
            evaluate_every_n_tokens: self.config.evaluate_every_n_tokens,
            enable_early_termination: self.config.enable_early_termination,
        };

        self.log(&format!("Starting session at {}", url));

        let response = self
            .http_client
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

        let data: SessionStartedData = response.json().await?;
        self.log(&format!("Session started: {}", data.session_id));

        let session = GuardrailSession::new(data);
        *self.session.lock().await = Some(session.clone());

        Ok(session)
    }

    /// Evaluate a single token.
    pub async fn evaluate_token(&self, token: &str) -> Result<StreamingEvent, DiagnyxError> {
        let session_id = {
            let session = self.session.lock().await;
            session
                .as_ref()
                .ok_or_else(|| DiagnyxError::ConfigError("No active session".to_string()))?
                .session_id
                .clone()
        };

        let url = format!(
            "{}/api/v1/guardrails/streaming/evaluate",
            self.config.base_url
        );

        let request = EvaluateTokenRequest {
            session_id: session_id.clone(),
            token: token.to_string(),
        };

        let response = self
            .http_client
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

        // Parse SSE response
        let text = response.text().await?;
        let event = self.parse_sse_response(&text)?;

        // Update session state
        {
            let mut session = self.session.lock().await;
            if let Some(ref mut s) = *session {
                s.update(&event);
            }
        }

        Ok(event)
    }

    /// Complete the streaming session.
    pub async fn complete_session(&self) -> Result<GuardrailSession, DiagnyxError> {
        let session_id = {
            let session = self.session.lock().await;
            session
                .as_ref()
                .ok_or_else(|| DiagnyxError::ConfigError("No active session".to_string()))?
                .session_id
                .clone()
        };

        let url = format!(
            "{}/api/v1/guardrails/streaming/complete",
            self.config.base_url
        );

        let request = CompleteSessionRequest {
            session_id: session_id.clone(),
        };

        self.log(&format!("Completing session: {}", session_id));

        let response = self
            .http_client
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

        // Parse SSE response and update session
        let text = response.text().await?;
        let event = self.parse_sse_response(&text)?;

        let session = {
            let mut session_lock = self.session.lock().await;
            if let Some(ref mut s) = *session_lock {
                s.update(&event);
            }
            session_lock.take()
        };

        session.ok_or_else(|| DiagnyxError::ConfigError("No active session".to_string()))
    }

    /// Cancel the streaming session.
    pub async fn cancel_session(&self, reason: Option<&str>) -> Result<(), DiagnyxError> {
        let session_id = {
            let session = self.session.lock().await;
            match session.as_ref() {
                Some(s) => s.session_id.clone(),
                None => return Ok(()), // No active session to cancel
            }
        };

        let url = format!(
            "{}/api/v1/guardrails/streaming/cancel",
            self.config.base_url
        );

        let request = CancelSessionRequest {
            session_id: session_id.clone(),
            reason: reason.map(|s| s.to_string()),
        };

        self.log(&format!("Cancelling session: {}", session_id));

        let response = self
            .http_client
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

        // Clear session
        *self.session.lock().await = None;

        Ok(())
    }

    /// Get the current session state.
    pub async fn get_session(&self) -> Option<GuardrailSession> {
        self.session.lock().await.clone()
    }

    /// Stream tokens with guardrail evaluation.
    ///
    /// Returns a receiver that yields streaming events. Each token is evaluated
    /// and events are sent to the receiver. If early termination is triggered,
    /// the stream will end with an EarlyTermination event.
    pub async fn stream_with_guardrails<S>(
        &self,
        token_stream: S,
        input: Option<&str>,
    ) -> Result<mpsc::Receiver<Result<StreamingEvent, DiagnyxError>>, DiagnyxError>
    where
        S: futures::Stream<Item = String> + Send + 'static,
    {
        use futures::StreamExt;

        // Start session
        self.start_session(input).await?;

        let (tx, rx) = mpsc::channel(100);
        let client = self.http_client.clone();
        let config = self.config.clone();
        let session = Arc::clone(&self.session);

        tokio::spawn(async move {
            let mut stream = Box::pin(token_stream);

            while let Some(token) = stream.next().await {
                let session_id = {
                    let session_lock = session.lock().await;
                    match session_lock.as_ref() {
                        Some(s) => s.session_id.clone(),
                        None => {
                            let _ = tx
                                .send(Err(DiagnyxError::ConfigError(
                                    "Session ended".to_string(),
                                )))
                                .await;
                            return;
                        }
                    }
                };

                let url = format!(
                    "{}/api/v1/guardrails/streaming/evaluate",
                    config.base_url
                );

                let request = EvaluateTokenRequest {
                    session_id: session_id.clone(),
                    token: token.clone(),
                };

                let result = client
                    .post(&url)
                    .header("Content-Type", "application/json")
                    .header("Authorization", format!("Bearer {}", config.api_key))
                    .json(&request)
                    .send()
                    .await;

                match result {
                    Ok(response) => {
                        let status = response.status();
                        if !status.is_success() {
                            let message = response.text().await.unwrap_or_default();
                            let _ = tx
                                .send(Err(DiagnyxError::ApiError {
                                    status_code: status.as_u16(),
                                    message,
                                }))
                                .await;
                            return;
                        }

                        match response.text().await {
                            Ok(text) => {
                                match parse_sse_response_static(&text) {
                                    Ok(event) => {
                                        // Update session state
                                        {
                                            let mut session_lock = session.lock().await;
                                            if let Some(ref mut s) = *session_lock {
                                                s.update(&event);
                                            }
                                        }

                                        // Check for early termination
                                        let is_termination =
                                            matches!(event, StreamingEvent::EarlyTermination(_));

                                        let _ = tx.send(Ok(event)).await;

                                        if is_termination {
                                            return;
                                        }
                                    }
                                    Err(e) => {
                                        let _ = tx.send(Err(e)).await;
                                        return;
                                    }
                                }
                            }
                            Err(e) => {
                                let _ = tx.send(Err(DiagnyxError::HttpError(e))).await;
                                return;
                            }
                        }
                    }
                    Err(e) => {
                        let _ = tx.send(Err(DiagnyxError::HttpError(e))).await;
                        return;
                    }
                }
            }

            // Complete session
            let session_id = {
                let session_lock = session.lock().await;
                session_lock.as_ref().map(|s| s.session_id.clone())
            };

            if let Some(session_id) = session_id {
                let url = format!(
                    "{}/api/v1/guardrails/streaming/complete",
                    config.base_url
                );

                let request = CompleteSessionRequest { session_id };

                let result = client
                    .post(&url)
                    .header("Content-Type", "application/json")
                    .header("Authorization", format!("Bearer {}", config.api_key))
                    .json(&request)
                    .send()
                    .await;

                if let Ok(response) = result {
                    if let Ok(text) = response.text().await {
                        if let Ok(event) = parse_sse_response_static(&text) {
                            let _ = tx.send(Ok(event)).await;
                        }
                    }
                }
            }
        });

        Ok(rx)
    }

    fn parse_sse_response(&self, text: &str) -> Result<StreamingEvent, DiagnyxError> {
        parse_sse_response_static(text)
    }

    fn log(&self, message: &str) {
        if self.config.debug {
            println!("[Diagnyx Guardrails] {}", message);
        }
    }
}

fn parse_sse_response_static(text: &str) -> Result<StreamingEvent, DiagnyxError> {
    let mut event_type = String::new();
    let mut data = String::new();

    for line in text.lines() {
        if line.starts_with("event: ") {
            event_type = line[7..].to_string();
        } else if line.starts_with("data: ") {
            data = line[6..].to_string();
        }
    }

    if event_type.is_empty() || data.is_empty() {
        // Try parsing as raw JSON
        if let Ok(event) = serde_json::from_str::<serde_json::Value>(text) {
            if let Some(event_type_val) = event.get("event_type") {
                event_type = event_type_val
                    .as_str()
                    .unwrap_or("error")
                    .to_string();
                data = text.to_string();
            }
        }

        if event_type.is_empty() {
            return Err(DiagnyxError::ConfigError(
                "Invalid SSE response format".to_string(),
            ));
        }
    }

    StreamingEvent::from_sse(&event_type, &data).map_err(|e| DiagnyxError::SerializationError(e))
}

/// Wrap an async token stream with guardrail evaluation.
///
/// This is a convenience function that yields tokens while checking them against
/// guardrails. If a blocking violation is detected, it returns an error.
pub async fn stream_with_guardrails<S>(
    config: StreamingGuardrailsConfig,
    token_stream: S,
    input: Option<&str>,
) -> Result<impl futures::Stream<Item = Result<String, GuardrailViolationError>>, DiagnyxError>
where
    S: futures::Stream<Item = String> + Send + 'static,
{
    let client = StreamingGuardrails::new(config);
    let mut events_rx = client.stream_with_guardrails(token_stream, input).await?;
    let session = client.get_session().await;

    let (tx, rx) = mpsc::channel(100);
    let session = Arc::new(Mutex::new(session));

    tokio::spawn(async move {
        while let Some(result) = events_rx.recv().await {
            match result {
                Ok(event) => {
                    // Update session
                    {
                        let mut session_lock = session.lock().await;
                        if let Some(ref mut s) = *session_lock {
                            s.update(&event);
                        }
                    }

                    match event {
                        StreamingEvent::TokenAllowed(data) => {
                            let _ = tx.send(Ok(data.token)).await;
                        }
                        StreamingEvent::EarlyTermination(data) => {
                            let session = session.lock().await.clone().unwrap_or_else(|| {
                                GuardrailSession::new(
                                    crate::guardrails::types::SessionStartedData {
                                        session_id: data.session_id.clone(),
                                        organization_id: String::new(),
                                        project_id: String::new(),
                                        active_policies: vec![],
                                    },
                                )
                            });
                            let _ = tx
                                .send(Err(GuardrailViolationError {
                                    violation: data.violation,
                                    session,
                                }))
                                .await;
                            return;
                        }
                        StreamingEvent::ViolationDetected(_) => {
                            // Advisory/warning violations don't stop the stream
                        }
                        StreamingEvent::SessionComplete(_) => {
                            // Stream complete
                            return;
                        }
                        _ => {}
                    }
                }
                Err(_) => {
                    // Error in evaluation, stop stream
                    return;
                }
            }
        }
    });

    Ok(tokio_stream::wrappers::ReceiverStream::new(rx))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_streaming_guardrails_new() {
        let config = StreamingGuardrailsConfig::new("api-key", "org-1", "proj-1");
        let _ = StreamingGuardrails::new(config);
    }

    #[test]
    fn test_guardrail_violation_error_display() {
        let violation = GuardrailViolation {
            policy_id: "pol-1".to_string(),
            policy_type: "pii_detection".to_string(),
            message: "PII detected in output".to_string(),
            severity: crate::guardrails::types::EnforcementLevel::Blocking,
            details: None,
        };

        let session = GuardrailSession::new(crate::guardrails::types::SessionStartedData {
            session_id: "sess-123".to_string(),
            organization_id: "org-1".to_string(),
            project_id: "proj-1".to_string(),
            active_policies: vec![],
        });

        let error = GuardrailViolationError { violation, session };
        assert_eq!(
            error.to_string(),
            "Guardrail violation: PII detected in output"
        );
    }

    #[test]
    fn test_parse_sse_response() {
        let text = "event: token_allowed\ndata: {\"session_id\":\"sess-123\",\"token\":\"hello\",\"tokens_processed\":1}\n\n";
        let event = parse_sse_response_static(text).unwrap();

        match event {
            StreamingEvent::TokenAllowed(data) => {
                assert_eq!(data.session_id, "sess-123");
                assert_eq!(data.token, "hello");
                assert_eq!(data.tokens_processed, 1);
            }
            _ => panic!("Expected TokenAllowed event"),
        }
    }

    #[test]
    fn test_parse_sse_response_violation() {
        let text = "event: violation_detected\ndata: {\"session_id\":\"sess-123\",\"violation\":{\"policy_id\":\"pol-1\",\"policy_type\":\"pii\",\"message\":\"PII found\",\"severity\":\"warning\",\"details\":null},\"tokens_processed\":5}\n\n";
        let event = parse_sse_response_static(text).unwrap();

        match event {
            StreamingEvent::ViolationDetected(data) => {
                assert_eq!(data.session_id, "sess-123");
                assert_eq!(data.violation.policy_id, "pol-1");
                assert_eq!(
                    data.violation.severity,
                    crate::guardrails::types::EnforcementLevel::Warning
                );
            }
            _ => panic!("Expected ViolationDetected event"),
        }
    }
}
