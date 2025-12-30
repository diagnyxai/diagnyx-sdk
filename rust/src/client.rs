use crate::error::DiagnyxError;
use crate::types::{BatchRequest, DiagnyxConfig, LLMCall};
use chrono::Utc;
use reqwest::Client;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;
use tokio::time::interval;

/// The Diagnyx client for tracking LLM calls.
pub struct DiagnyxClient {
    config: DiagnyxConfig,
    http_client: Client,
    buffer: Arc<Mutex<Vec<LLMCall>>>,
    shutdown: Arc<Mutex<bool>>,
}

impl DiagnyxClient {
    /// Create a new DiagnyxClient with the given API key.
    pub fn new(api_key: impl Into<String>) -> Self {
        Self::with_config(DiagnyxConfig::new(api_key))
    }

    /// Create a new DiagnyxClient with custom configuration.
    pub fn with_config(config: DiagnyxConfig) -> Self {
        let client = Self {
            config,
            http_client: Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("Failed to create HTTP client"),
            buffer: Arc::new(Mutex::new(Vec::new())),
            shutdown: Arc::new(Mutex::new(false)),
        };

        // Start background flush task
        client.start_flush_task();

        client
    }

    /// Track a single LLM call.
    pub async fn track(&self, mut call: LLMCall) {
        if call.timestamp == DateTime::<Utc>::default() {
            call.timestamp = Utc::now();
        }

        let should_flush = {
            let mut buffer = self.buffer.lock().await;
            buffer.push(call);
            buffer.len() >= self.config.batch_size
        };

        if should_flush {
            let _ = self.flush().await;
        }
    }

    /// Track multiple LLM calls.
    pub async fn track_all(&self, calls: Vec<LLMCall>) {
        let now = Utc::now();
        let calls: Vec<LLMCall> = calls
            .into_iter()
            .map(|mut c| {
                if c.timestamp == DateTime::<Utc>::default() {
                    c.timestamp = now;
                }
                c
            })
            .collect();

        let should_flush = {
            let mut buffer = self.buffer.lock().await;
            buffer.extend(calls);
            buffer.len() >= self.config.batch_size
        };

        if should_flush {
            let _ = self.flush().await;
        }
    }

    /// Flush all buffered calls to the API.
    pub async fn flush(&self) -> Result<(), DiagnyxError> {
        let calls = {
            let mut buffer = self.buffer.lock().await;
            if buffer.is_empty() {
                return Ok(());
            }
            std::mem::take(&mut *buffer)
        };

        match self.send_batch(&calls).await {
            Ok(_) => {
                self.log(&format!("Flushed {} calls", calls.len()));
                Ok(())
            }
            Err(e) => {
                // Put calls back in buffer on error
                let mut buffer = self.buffer.lock().await;
                let mut restored = calls;
                restored.append(&mut *buffer);
                *buffer = restored;
                self.log(&format!("Flush failed: {}", e));
                Err(e)
            }
        }
    }

    /// Get the current buffer size.
    pub async fn buffer_size(&self) -> usize {
        self.buffer.lock().await.len()
    }

    /// Shutdown the client, flushing any remaining calls.
    pub async fn shutdown(&self) -> Result<(), DiagnyxError> {
        *self.shutdown.lock().await = true;
        self.flush().await
    }

    fn start_flush_task(&self) {
        let buffer = Arc::clone(&self.buffer);
        let shutdown = Arc::clone(&self.shutdown);
        let config = self.config.clone();
        let http_client = self.http_client.clone();

        tokio::spawn(async move {
            let mut ticker = interval(Duration::from_millis(config.flush_interval_ms));

            loop {
                ticker.tick().await;

                if *shutdown.lock().await {
                    break;
                }

                let calls = {
                    let mut buf = buffer.lock().await;
                    if buf.is_empty() {
                        continue;
                    }
                    std::mem::take(&mut *buf)
                };

                if let Err(e) = Self::send_batch_static(&http_client, &config, &calls).await {
                    if config.debug {
                        eprintln!("[Diagnyx] Background flush error: {}", e);
                    }
                    // Put calls back
                    let mut buf = buffer.lock().await;
                    let mut restored = calls;
                    restored.append(&mut *buf);
                    *buf = restored;
                } else if config.debug {
                    println!("[Diagnyx] Flushed {} calls", calls.len());
                }
            }
        });
    }

    async fn send_batch(&self, calls: &[LLMCall]) -> Result<(), DiagnyxError> {
        Self::send_batch_static(&self.http_client, &self.config, calls).await
    }

    async fn send_batch_static(
        http_client: &Client,
        config: &DiagnyxConfig,
        calls: &[LLMCall],
    ) -> Result<(), DiagnyxError> {
        let payload = BatchRequest {
            calls: calls.to_vec(),
        };

        let url = format!("{}/api/v1/ingest/llm/batch", config.base_url);

        let mut last_error = None;

        for attempt in 0..config.max_retries {
            let result = http_client
                .post(&url)
                .header("Content-Type", "application/json")
                .header("Authorization", format!("Bearer {}", config.api_key))
                .json(&payload)
                .send()
                .await;

            match result {
                Ok(response) => {
                    let status = response.status();
                    if status.is_success() {
                        return Ok(());
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

            if attempt < config.max_retries - 1 {
                tokio::time::sleep(Duration::from_secs(2u64.pow(attempt))).await;
            }
        }

        Err(last_error.unwrap_or(DiagnyxError::MaxRetriesExceeded))
    }

    fn log(&self, message: &str) {
        if self.config.debug {
            println!("[Diagnyx] {}", message);
        }
    }
}

use chrono::DateTime;

/// Track an LLM call with automatic timing.
pub async fn track_call<F, T>(
    client: &DiagnyxClient,
    provider: crate::Provider,
    model: impl Into<String>,
    f: F,
) -> Result<T, DiagnyxError>
where
    F: FnOnce() -> Result<(T, i32, i32), Box<dyn std::error::Error + Send + Sync>>,
{
    let model = model.into();
    let start = std::time::Instant::now();

    match f() {
        Ok((result, input_tokens, output_tokens)) => {
            let latency_ms = start.elapsed().as_millis() as i64;

            let call = LLMCall::builder()
                .provider(provider)
                .model(&model)
                .input_tokens(input_tokens)
                .output_tokens(output_tokens)
                .latency_ms(latency_ms)
                .status(crate::CallStatus::Success)
                .build();

            client.track(call).await;
            Ok(result)
        }
        Err(e) => {
            let latency_ms = start.elapsed().as_millis() as i64;

            let call = LLMCall::builder()
                .provider(provider)
                .model(&model)
                .input_tokens(0)
                .output_tokens(0)
                .latency_ms(latency_ms)
                .status(crate::CallStatus::Error)
                .error_message(e.to_string())
                .build();

            client.track(call).await;
            Err(DiagnyxError::ConfigError(e.to_string()))
        }
    }
}

/// Track an LLM call with full content capture.
/// Use this for providers without dedicated wrappers (like Anthropic).
pub async fn track_call_with_content(
    client: &DiagnyxClient,
    provider: crate::Provider,
    model: impl Into<String>,
    prompt: impl Into<String>,
    response: impl Into<String>,
    input_tokens: i32,
    output_tokens: i32,
    latency_ms: i64,
) {
    let config = client.config.clone();
    let model = model.into();
    let prompt = prompt.into();
    let response = response.into();

    let mut builder = LLMCall::builder()
        .provider(provider)
        .model(&model)
        .input_tokens(input_tokens)
        .output_tokens(output_tokens)
        .latency_ms(latency_ms)
        .status(crate::CallStatus::Success);

    if config.capture_full_content {
        let max_len = if config.content_max_length > 0 {
            config.content_max_length
        } else {
            10000
        };

        let truncated_prompt = if prompt.len() > max_len {
            format!("{}... [truncated]", &prompt[..max_len])
        } else {
            prompt
        };

        let truncated_response = if response.len() > max_len {
            format!("{}... [truncated]", &response[..max_len])
        } else {
            response
        };

        builder = builder
            .full_prompt(truncated_prompt)
            .full_response(truncated_response);
    }

    client.track(builder.build()).await;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CallStatus, DiagnyxConfig, LLMCall, Provider};
    use wiremock::matchers::{header, method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    async fn create_mock_client(server: &MockServer) -> DiagnyxClient {
        DiagnyxClient::with_config(
            DiagnyxConfig::new("test-api-key")
                .base_url(&server.uri())
                .flush_interval_ms(60000) // Disable auto-flush
                .max_retries(1),
        )
    }

    #[tokio::test]
    async fn test_create_client_with_api_key() {
        let client = DiagnyxClient::new("test-api-key");
        assert_eq!(client.buffer_size().await, 0);
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_track_adds_to_buffer() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/api/v1/ingest/llm/batch"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tracked": 1,
                "total_cost": 0.001,
                "total_tokens": 150,
                "ids": ["id-1"]
            })))
            .mount(&server)
            .await;

        let client = create_mock_client(&server).await;

        let call = LLMCall::builder()
            .provider(Provider::OpenAI)
            .model("gpt-4")
            .input_tokens(100)
            .output_tokens(50)
            .status(CallStatus::Success)
            .build();

        client.track(call).await;

        assert_eq!(client.buffer_size().await, 1);
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_track_all_adds_multiple() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/api/v1/ingest/llm/batch"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tracked": 3,
                "total_cost": 0.003,
                "total_tokens": 450,
                "ids": ["id-1", "id-2", "id-3"]
            })))
            .mount(&server)
            .await;

        let client = create_mock_client(&server).await;

        let calls = vec![
            LLMCall::builder()
                .provider(Provider::OpenAI)
                .model("gpt-4")
                .build(),
            LLMCall::builder()
                .provider(Provider::Anthropic)
                .model("claude-3")
                .build(),
            LLMCall::builder()
                .provider(Provider::Google)
                .model("gemini")
                .build(),
        ];

        client.track_all(calls).await;

        assert_eq!(client.buffer_size().await, 3);
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_flush_sends_to_api() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/api/v1/ingest/llm/batch"))
            .and(header("Authorization", "Bearer test-api-key"))
            .and(header("Content-Type", "application/json"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tracked": 1
            })))
            .expect(1)
            .mount(&server)
            .await;

        let client = create_mock_client(&server).await;

        let call = LLMCall::builder()
            .provider(Provider::OpenAI)
            .model("gpt-4")
            .input_tokens(100)
            .output_tokens(50)
            .build();

        client.track(call).await;
        assert_eq!(client.buffer_size().await, 1);

        let result = client.flush().await;
        assert!(result.is_ok());
        assert_eq!(client.buffer_size().await, 0);
    }

    #[tokio::test]
    async fn test_flush_empty_buffer_succeeds() {
        let server = MockServer::start().await;
        let client = create_mock_client(&server).await;

        // Flush with empty buffer should succeed
        let result = client.flush().await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_flush_restores_buffer_on_error() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/api/v1/ingest/llm/batch"))
            .respond_with(ResponseTemplate::new(500).set_body_json(serde_json::json!({
                "error": "Server error"
            })))
            .mount(&server)
            .await;

        let client = create_mock_client(&server).await;

        let call = LLMCall::builder()
            .provider(Provider::OpenAI)
            .model("gpt-4")
            .build();

        client.track(call).await;
        assert_eq!(client.buffer_size().await, 1);

        let result = client.flush().await;
        assert!(result.is_err());

        // Buffer should be restored
        assert_eq!(client.buffer_size().await, 1);
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_auto_flush_when_batch_size_reached() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/api/v1/ingest/llm/batch"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tracked": 5
            })))
            .expect(1)
            .mount(&server)
            .await;

        let client = DiagnyxClient::with_config(
            DiagnyxConfig::new("test-api-key")
                .base_url(&server.uri())
                .batch_size(5)
                .flush_interval_ms(60000),
        );

        for _ in 0..5 {
            let call = LLMCall::builder()
                .provider(Provider::OpenAI)
                .model("gpt-4")
                .build();
            client.track(call).await;
        }

        // Wait a bit for async flush
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;

        assert_eq!(client.buffer_size().await, 0);
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_shutdown_flushes_buffer() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/api/v1/ingest/llm/batch"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tracked": 1
            })))
            .expect(1)
            .mount(&server)
            .await;

        let client = create_mock_client(&server).await;

        let call = LLMCall::builder()
            .provider(Provider::OpenAI)
            .model("gpt-4")
            .build();

        client.track(call).await;
        assert_eq!(client.buffer_size().await, 1);

        let result = client.shutdown().await;
        assert!(result.is_ok());
        assert_eq!(client.buffer_size().await, 0);
    }

    #[tokio::test]
    async fn test_no_retry_on_client_error() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/api/v1/ingest/llm/batch"))
            .respond_with(ResponseTemplate::new(400).set_body_json(serde_json::json!({
                "error": "Bad request"
            })))
            .expect(1) // Should only be called once (no retries on 4xx)
            .mount(&server)
            .await;

        let client = DiagnyxClient::with_config(
            DiagnyxConfig::new("test-api-key")
                .base_url(&server.uri())
                .flush_interval_ms(60000)
                .max_retries(3), // Set retries to 3 but it should still only call once
        );

        let call = LLMCall::builder()
            .provider(Provider::OpenAI)
            .model("gpt-4")
            .build();

        client.track(call).await;
        let result = client.flush().await;

        assert!(result.is_err());
        // Buffer should be restored
        assert_eq!(client.buffer_size().await, 1);
    }
}
