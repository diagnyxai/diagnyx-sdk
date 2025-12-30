use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Supported LLM providers.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum Provider {
    OpenAI,
    Anthropic,
    Google,
    Azure,
    Aws,
    Custom,
}

/// Status of an LLM call.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum CallStatus {
    Success,
    Error,
    Timeout,
    RateLimited,
}

impl Default for CallStatus {
    fn default() -> Self {
        CallStatus::Success
    }
}

/// Configuration for the Diagnyx client.
#[derive(Debug, Clone)]
pub struct DiagnyxConfig {
    pub api_key: String,
    pub base_url: String,
    pub batch_size: usize,
    pub flush_interval_ms: u64,
    pub max_retries: u32,
    pub debug: bool,
    /// Enable capturing full prompt/response content. Default: false (privacy-first)
    pub capture_full_content: bool,
    /// Maximum length for captured content before truncation. Default: 10000
    pub content_max_length: usize,
}

impl DiagnyxConfig {
    pub fn new(api_key: impl Into<String>) -> Self {
        Self {
            api_key: api_key.into(),
            base_url: "https://api.diagnyx.io".to_string(),
            batch_size: 100,
            flush_interval_ms: 5000,
            max_retries: 3,
            debug: false,
            capture_full_content: false,
            content_max_length: 10000,
        }
    }

    pub fn base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = url.into();
        self
    }

    pub fn batch_size(mut self, size: usize) -> Self {
        self.batch_size = size;
        self
    }

    pub fn flush_interval_ms(mut self, interval: u64) -> Self {
        self.flush_interval_ms = interval;
        self
    }

    pub fn max_retries(mut self, retries: u32) -> Self {
        self.max_retries = retries;
        self
    }

    pub fn debug(mut self, debug: bool) -> Self {
        self.debug = debug;
        self
    }

    pub fn capture_full_content(mut self, capture: bool) -> Self {
        self.capture_full_content = capture;
        self
    }

    pub fn content_max_length(mut self, length: usize) -> Self {
        self.content_max_length = length;
        self
    }
}

/// Represents a single LLM API call.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LLMCall {
    pub provider: Provider,
    pub model: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub endpoint: Option<String>,
    pub input_tokens: i32,
    pub output_tokens: i32,
    pub latency_ms: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ttft_ms: Option<i64>,
    pub status: CallStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub environment: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_identifier: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub span_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<HashMap<String, serde_json::Value>>,
    pub timestamp: DateTime<Utc>,
    /// Full prompt content (only captured if capture_full_content=true)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub full_prompt: Option<String>,
    /// Full response content (only captured if capture_full_content=true)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub full_response: Option<String>,
}

impl LLMCall {
    pub fn builder() -> LLMCallBuilder {
        LLMCallBuilder::default()
    }
}

/// Builder for LLMCall.
#[derive(Default)]
pub struct LLMCallBuilder {
    provider: Option<Provider>,
    model: Option<String>,
    endpoint: Option<String>,
    input_tokens: i32,
    output_tokens: i32,
    latency_ms: i64,
    ttft_ms: Option<i64>,
    status: CallStatus,
    error_code: Option<String>,
    error_message: Option<String>,
    project_id: Option<String>,
    environment: Option<String>,
    user_identifier: Option<String>,
    trace_id: Option<String>,
    span_id: Option<String>,
    metadata: Option<HashMap<String, serde_json::Value>>,
    full_prompt: Option<String>,
    full_response: Option<String>,
}

impl LLMCallBuilder {
    pub fn provider(mut self, provider: Provider) -> Self {
        self.provider = Some(provider);
        self
    }

    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    pub fn endpoint(mut self, endpoint: impl Into<String>) -> Self {
        self.endpoint = Some(endpoint.into());
        self
    }

    pub fn input_tokens(mut self, tokens: i32) -> Self {
        self.input_tokens = tokens;
        self
    }

    pub fn output_tokens(mut self, tokens: i32) -> Self {
        self.output_tokens = tokens;
        self
    }

    pub fn latency_ms(mut self, latency: i64) -> Self {
        self.latency_ms = latency;
        self
    }

    pub fn ttft_ms(mut self, ttft: i64) -> Self {
        self.ttft_ms = Some(ttft);
        self
    }

    pub fn status(mut self, status: CallStatus) -> Self {
        self.status = status;
        self
    }

    pub fn error_code(mut self, code: impl Into<String>) -> Self {
        self.error_code = Some(code.into());
        self
    }

    pub fn error_message(mut self, message: impl Into<String>) -> Self {
        self.error_message = Some(message.into());
        self
    }

    pub fn project_id(mut self, id: impl Into<String>) -> Self {
        self.project_id = Some(id.into());
        self
    }

    pub fn environment(mut self, env: impl Into<String>) -> Self {
        self.environment = Some(env.into());
        self
    }

    pub fn user_identifier(mut self, id: impl Into<String>) -> Self {
        self.user_identifier = Some(id.into());
        self
    }

    pub fn trace_id(mut self, id: impl Into<String>) -> Self {
        self.trace_id = Some(id.into());
        self
    }

    pub fn span_id(mut self, id: impl Into<String>) -> Self {
        self.span_id = Some(id.into());
        self
    }

    pub fn metadata(mut self, metadata: HashMap<String, serde_json::Value>) -> Self {
        self.metadata = Some(metadata);
        self
    }

    pub fn full_prompt(mut self, prompt: impl Into<String>) -> Self {
        self.full_prompt = Some(prompt.into());
        self
    }

    pub fn full_response(mut self, response: impl Into<String>) -> Self {
        self.full_response = Some(response.into());
        self
    }

    pub fn build(self) -> LLMCall {
        LLMCall {
            provider: self.provider.expect("provider is required"),
            model: self.model.expect("model is required"),
            endpoint: self.endpoint,
            input_tokens: self.input_tokens,
            output_tokens: self.output_tokens,
            latency_ms: self.latency_ms,
            ttft_ms: self.ttft_ms,
            status: self.status,
            error_code: self.error_code,
            error_message: self.error_message,
            project_id: self.project_id,
            environment: self.environment,
            user_identifier: self.user_identifier,
            trace_id: self.trace_id,
            span_id: self.span_id,
            metadata: self.metadata,
            timestamp: Utc::now(),
            full_prompt: self.full_prompt,
            full_response: self.full_response,
        }
    }
}

/// Request body for batch ingestion.
#[derive(Debug, Serialize)]
pub(crate) struct BatchRequest {
    pub calls: Vec<LLMCall>,
}

/// Response from batch ingestion.
#[derive(Debug, Deserialize)]
pub struct BatchResponse {
    pub tracked: i32,
    pub total_cost: f64,
    pub total_tokens: i32,
    pub ids: Vec<String>,
}

/// Options for tracking calls.
#[derive(Debug, Clone, Default)]
pub struct TrackOptions {
    pub project_id: Option<String>,
    pub environment: Option<String>,
    pub user_identifier: Option<String>,
    pub trace_id: Option<String>,
    pub span_id: Option<String>,
    pub metadata: Option<HashMap<String, serde_json::Value>>,
}

impl TrackOptions {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn project_id(mut self, id: impl Into<String>) -> Self {
        self.project_id = Some(id.into());
        self
    }

    pub fn environment(mut self, env: impl Into<String>) -> Self {
        self.environment = Some(env.into());
        self
    }

    pub fn user_identifier(mut self, id: impl Into<String>) -> Self {
        self.user_identifier = Some(id.into());
        self
    }

    pub fn trace_id(mut self, id: impl Into<String>) -> Self {
        self.trace_id = Some(id.into());
        self
    }

    pub fn span_id(mut self, id: impl Into<String>) -> Self {
        self.span_id = Some(id.into());
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_provider_serialization() {
        let provider = Provider::OpenAI;
        let json = serde_json::to_string(&provider).unwrap();
        assert_eq!(json, "\"openai\"");

        let provider = Provider::Anthropic;
        let json = serde_json::to_string(&provider).unwrap();
        assert_eq!(json, "\"anthropic\"");

        let provider = Provider::Google;
        let json = serde_json::to_string(&provider).unwrap();
        assert_eq!(json, "\"google\"");
    }

    #[test]
    fn test_call_status_serialization() {
        let status = CallStatus::Success;
        let json = serde_json::to_string(&status).unwrap();
        assert_eq!(json, "\"success\"");

        let status = CallStatus::Error;
        let json = serde_json::to_string(&status).unwrap();
        assert_eq!(json, "\"error\"");

        let status = CallStatus::RateLimited;
        let json = serde_json::to_string(&status).unwrap();
        assert_eq!(json, "\"rate_limited\"");
    }

    #[test]
    fn test_call_status_default() {
        let status = CallStatus::default();
        assert_eq!(status, CallStatus::Success);
    }

    #[test]
    fn test_diagnyx_config_default_values() {
        let config = DiagnyxConfig::new("test-api-key");
        assert_eq!(config.api_key, "test-api-key");
        assert_eq!(config.base_url, "https://api.diagnyx.io");
        assert_eq!(config.batch_size, 100);
        assert_eq!(config.flush_interval_ms, 5000);
        assert_eq!(config.max_retries, 3);
        assert!(!config.debug);
        assert!(!config.capture_full_content);
        assert_eq!(config.content_max_length, 10000);
    }

    #[test]
    fn test_diagnyx_config_builder_pattern() {
        let config = DiagnyxConfig::new("my-key")
            .base_url("https://custom.api.com")
            .batch_size(50)
            .flush_interval_ms(10000)
            .max_retries(5)
            .debug(true)
            .capture_full_content(true)
            .content_max_length(5000);

        assert_eq!(config.api_key, "my-key");
        assert_eq!(config.base_url, "https://custom.api.com");
        assert_eq!(config.batch_size, 50);
        assert_eq!(config.flush_interval_ms, 10000);
        assert_eq!(config.max_retries, 5);
        assert!(config.debug);
        assert!(config.capture_full_content);
        assert_eq!(config.content_max_length, 5000);
    }

    #[test]
    fn test_llm_call_builder() {
        let call = LLMCall::builder()
            .provider(Provider::OpenAI)
            .model("gpt-4")
            .input_tokens(100)
            .output_tokens(50)
            .latency_ms(500)
            .status(CallStatus::Success)
            .build();

        assert_eq!(call.provider, Provider::OpenAI);
        assert_eq!(call.model, "gpt-4");
        assert_eq!(call.input_tokens, 100);
        assert_eq!(call.output_tokens, 50);
        assert_eq!(call.latency_ms, 500);
        assert_eq!(call.status, CallStatus::Success);
    }

    #[test]
    fn test_llm_call_with_optional_fields() {
        let mut metadata = HashMap::new();
        metadata.insert("key".to_string(), serde_json::json!("value"));

        let call = LLMCall::builder()
            .provider(Provider::Anthropic)
            .model("claude-3")
            .endpoint("/v1/messages")
            .input_tokens(200)
            .output_tokens(100)
            .latency_ms(750)
            .ttft_ms(50)
            .status(CallStatus::Success)
            .project_id("proj-123")
            .environment("production")
            .user_identifier("user-456")
            .trace_id("trace-789")
            .span_id("span-abc")
            .metadata(metadata)
            .full_prompt("Hello, Claude!")
            .full_response("Hi there!")
            .build();

        assert_eq!(call.endpoint, Some("/v1/messages".to_string()));
        assert_eq!(call.ttft_ms, Some(50));
        assert_eq!(call.project_id, Some("proj-123".to_string()));
        assert_eq!(call.environment, Some("production".to_string()));
        assert_eq!(call.trace_id, Some("trace-789".to_string()));
        assert_eq!(call.full_prompt, Some("Hello, Claude!".to_string()));
    }

    #[test]
    fn test_llm_call_with_error() {
        let call = LLMCall::builder()
            .provider(Provider::OpenAI)
            .model("gpt-4")
            .status(CallStatus::Error)
            .error_code("rate_limit_exceeded")
            .error_message("You exceeded your quota")
            .build();

        assert_eq!(call.status, CallStatus::Error);
        assert_eq!(call.error_code, Some("rate_limit_exceeded".to_string()));
        assert_eq!(call.error_message, Some("You exceeded your quota".to_string()));
    }

    #[test]
    fn test_llm_call_json_serialization() {
        let call = LLMCall::builder()
            .provider(Provider::OpenAI)
            .model("gpt-4")
            .input_tokens(100)
            .output_tokens(50)
            .latency_ms(500)
            .status(CallStatus::Success)
            .build();

        let json = serde_json::to_string(&call).unwrap();
        assert!(json.contains("\"provider\":\"openai\""));
        assert!(json.contains("\"model\":\"gpt-4\""));
        assert!(json.contains("\"input_tokens\":100"));
        assert!(json.contains("\"output_tokens\":50"));
        assert!(json.contains("\"status\":\"success\""));
    }

    #[test]
    fn test_llm_call_omits_null_optional_fields() {
        let call = LLMCall::builder()
            .provider(Provider::OpenAI)
            .model("gpt-4")
            .build();

        let json = serde_json::to_string(&call).unwrap();
        // Optional fields should be omitted, not null
        assert!(!json.contains("\"endpoint\""));
        assert!(!json.contains("\"project_id\""));
        assert!(!json.contains("\"error_code\""));
        assert!(!json.contains("\"full_prompt\""));
    }

    #[test]
    fn test_track_options_builder() {
        let opts = TrackOptions::new()
            .project_id("proj-123")
            .environment("production")
            .user_identifier("user-456")
            .trace_id("trace-789")
            .span_id("span-abc");

        assert_eq!(opts.project_id, Some("proj-123".to_string()));
        assert_eq!(opts.environment, Some("production".to_string()));
        assert_eq!(opts.user_identifier, Some("user-456".to_string()));
        assert_eq!(opts.trace_id, Some("trace-789".to_string()));
        assert_eq!(opts.span_id, Some("span-abc".to_string()));
    }
}
