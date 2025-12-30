//! Callback handlers for LLM framework integrations.
//!
//! This module provides callback handlers for tracking LLM calls made through
//! various Rust LLM frameworks like langchain-rust.
//!
//! # Example
//!
//! ```rust,ignore
//! use diagnyx::{DiagnyxClient, callbacks::DiagnyxCallbackHandler};
//! use std::sync::Arc;
//!
//! #[tokio::main]
//! async fn main() {
//!     let client = Arc::new(DiagnyxClient::new("dx_live_xxx"));
//!     let handler = DiagnyxCallbackHandler::new(client.clone())
//!         .with_project_id("my-project")
//!         .with_environment("production");
//!
//!     // Use with langchain-rust or other frameworks
//!     let run_id = handler.on_llm_start("gpt-4", "Hello, world!");
//!     // ... LLM call happens ...
//!     handler.on_llm_end(&run_id, "gpt-4", "Hi there!", 10, 5);
//!
//!     client.shutdown().await.unwrap();
//! }
//! ```

use crate::{CallStatus, DiagnyxClient, LLMCall, Provider};
use chrono::Utc;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Instant;
use uuid::Uuid;

/// Context for a single LLM call being tracked.
#[derive(Debug, Clone)]
struct CallContext {
    start_time: Instant,
    model: String,
    prompt: Option<String>,
}

/// Options for configuring the DiagnyxCallbackHandler.
#[derive(Debug, Clone, Default)]
pub struct CallbackOptions {
    /// Project ID for categorizing calls.
    pub project_id: Option<String>,
    /// Environment name (production, staging, etc.).
    pub environment: Option<String>,
    /// User identifier for tracking.
    pub user_identifier: Option<String>,
    /// Whether to capture full prompt/response content.
    pub capture_content: bool,
    /// Maximum length for captured content before truncation.
    pub content_max_length: usize,
}

impl CallbackOptions {
    /// Creates new callback options with default values.
    pub fn new() -> Self {
        Self {
            content_max_length: 10000,
            ..Default::default()
        }
    }

    /// Sets the project ID.
    pub fn project_id(mut self, id: impl Into<String>) -> Self {
        self.project_id = Some(id.into());
        self
    }

    /// Sets the environment.
    pub fn environment(mut self, env: impl Into<String>) -> Self {
        self.environment = Some(env.into());
        self
    }

    /// Sets the user identifier.
    pub fn user_identifier(mut self, id: impl Into<String>) -> Self {
        self.user_identifier = Some(id.into());
        self
    }

    /// Enables content capture.
    pub fn capture_content(mut self, capture: bool) -> Self {
        self.capture_content = capture;
        self
    }

    /// Sets the maximum content length.
    pub fn content_max_length(mut self, length: usize) -> Self {
        self.content_max_length = length;
        self
    }
}

/// LangChain callback handler for Diagnyx cost tracking.
///
/// This handler can be used with langchain-rust or any other Rust LLM framework
/// that supports callback-based tracking.
pub struct DiagnyxCallbackHandler {
    client: Arc<DiagnyxClient>,
    options: CallbackOptions,
    call_contexts: Arc<Mutex<HashMap<String, CallContext>>>,
}

impl DiagnyxCallbackHandler {
    /// Creates a new callback handler with the given Diagnyx client.
    pub fn new(client: Arc<DiagnyxClient>) -> Self {
        Self {
            client,
            options: CallbackOptions::new(),
            call_contexts: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Sets the project ID for categorizing calls.
    pub fn with_project_id(mut self, id: impl Into<String>) -> Self {
        self.options.project_id = Some(id.into());
        self
    }

    /// Sets the environment name.
    pub fn with_environment(mut self, env: impl Into<String>) -> Self {
        self.options.environment = Some(env.into());
        self
    }

    /// Sets the user identifier for tracking.
    pub fn with_user_identifier(mut self, id: impl Into<String>) -> Self {
        self.options.user_identifier = Some(id.into());
        self
    }

    /// Enables capturing full prompt/response content.
    pub fn with_capture_content(mut self, capture: bool) -> Self {
        self.options.capture_content = capture;
        self
    }

    /// Sets the maximum content length before truncation.
    pub fn with_content_max_length(mut self, length: usize) -> Self {
        self.options.content_max_length = length;
        self
    }

    /// Called when an LLM call starts.
    ///
    /// Returns a run ID that should be passed to `on_llm_end` or `on_llm_error`.
    pub fn on_llm_start(&self, model: &str, prompt: &str) -> String {
        let run_id = Uuid::new_v4().to_string();
        self.on_llm_start_with_id(&run_id, model, prompt);
        run_id
    }

    /// Called when an LLM call starts with a specific run ID.
    pub fn on_llm_start_with_id(&self, run_id: &str, model: &str, prompt: &str) {
        let ctx = CallContext {
            start_time: Instant::now(),
            model: model.to_string(),
            prompt: if self.options.capture_content {
                Some(prompt.to_string())
            } else {
                None
            },
        };

        if let Ok(mut contexts) = self.call_contexts.lock() {
            contexts.insert(run_id.to_string(), ctx);
        }
    }

    /// Called when an LLM call completes successfully.
    pub fn on_llm_end(
        &self,
        run_id: &str,
        model: &str,
        response: &str,
        input_tokens: i32,
        output_tokens: i32,
    ) {
        let ctx = if let Ok(mut contexts) = self.call_contexts.lock() {
            contexts.remove(run_id)
        } else {
            None
        };

        let latency_ms = ctx
            .as_ref()
            .map(|c| c.start_time.elapsed().as_millis() as i64)
            .unwrap_or(0);

        let actual_model = if !model.is_empty() {
            model.to_string()
        } else {
            ctx.as_ref()
                .map(|c| c.model.clone())
                .unwrap_or_else(|| "unknown".to_string())
        };

        let provider = detect_provider(&actual_model);

        let mut call = LLMCall::builder()
            .provider(provider)
            .model(&actual_model)
            .input_tokens(input_tokens)
            .output_tokens(output_tokens)
            .latency_ms(latency_ms)
            .status(CallStatus::Success);

        if let Some(ref project_id) = self.options.project_id {
            call = call.project_id(project_id);
        }
        if let Some(ref environment) = self.options.environment {
            call = call.environment(environment);
        }
        if let Some(ref user_identifier) = self.options.user_identifier {
            call = call.user_identifier(user_identifier);
        }

        if self.options.capture_content {
            let max_len = self.options.content_max_length;

            if let Some(ref c) = ctx {
                if let Some(ref prompt) = c.prompt {
                    let truncated = if prompt.len() > max_len {
                        format!("{}... [truncated]", &prompt[..max_len])
                    } else {
                        prompt.clone()
                    };
                    call = call.full_prompt(truncated);
                }
            }

            let response_truncated = if response.len() > max_len {
                format!("{}... [truncated]", &response[..max_len])
            } else {
                response.to_string()
            };
            call = call.full_response(response_truncated);
        }

        let client = Arc::clone(&self.client);
        let call = call.build();
        tokio::spawn(async move {
            client.track(call).await;
        });
    }

    /// Called when an LLM call fails with an error.
    pub fn on_llm_error(&self, run_id: &str, model: &str, error: &str) {
        let ctx = if let Ok(mut contexts) = self.call_contexts.lock() {
            contexts.remove(run_id)
        } else {
            None
        };

        let latency_ms = ctx
            .as_ref()
            .map(|c| c.start_time.elapsed().as_millis() as i64)
            .unwrap_or(0);

        let actual_model = if !model.is_empty() {
            model.to_string()
        } else {
            ctx.as_ref()
                .map(|c| c.model.clone())
                .unwrap_or_else(|| "unknown".to_string())
        };

        let provider = detect_provider(&actual_model);

        let error_msg = if error.len() > 500 {
            &error[..500]
        } else {
            error
        };

        let mut call = LLMCall::builder()
            .provider(provider)
            .model(&actual_model)
            .input_tokens(0)
            .output_tokens(0)
            .latency_ms(latency_ms)
            .status(CallStatus::Error)
            .error_message(error_msg);

        if let Some(ref project_id) = self.options.project_id {
            call = call.project_id(project_id);
        }
        if let Some(ref environment) = self.options.environment {
            call = call.environment(environment);
        }
        if let Some(ref user_identifier) = self.options.user_identifier {
            call = call.user_identifier(user_identifier);
        }

        let client = Arc::clone(&self.client);
        let call = call.build();
        tokio::spawn(async move {
            client.track(call).await;
        });
    }

    /// Called when a chain starts. No-op for cost tracking.
    pub fn on_chain_start(&self, _chain_name: &str, _inputs: &str) {
        // No-op for cost tracking
    }

    /// Called when a chain ends. No-op for cost tracking.
    pub fn on_chain_end(&self, _outputs: &str) {
        // No-op for cost tracking
    }

    /// Called when a chain errors. No-op for cost tracking.
    pub fn on_chain_error(&self, _error: &str) {
        // No-op for cost tracking
    }

    /// Called when a tool starts. No-op for cost tracking.
    pub fn on_tool_start(&self, _tool_name: &str, _input: &str) {
        // No-op for cost tracking
    }

    /// Called when a tool ends. No-op for cost tracking.
    pub fn on_tool_end(&self, _output: &str) {
        // No-op for cost tracking
    }

    /// Called when a tool errors. No-op for cost tracking.
    pub fn on_tool_error(&self, _error: &str) {
        // No-op for cost tracking
    }
}

/// Detects the LLM provider from the model name.
pub fn detect_provider(model: &str) -> Provider {
    let model_lower = model.to_lowercase();

    if model_lower.starts_with("gpt-") || model_lower.starts_with("o1-") {
        return Provider::OpenAI;
    }
    if model_lower.starts_with("claude-") {
        return Provider::Anthropic;
    }
    if model_lower.starts_with("gemini-") {
        return Provider::Google;
    }

    Provider::Custom
}

#[cfg(test)]
mod tests {
    use super::*;

    // Provider detection tests don't need async runtime
    #[test]
    fn test_detect_provider_openai() {
        assert_eq!(detect_provider("gpt-4"), Provider::OpenAI);
        assert_eq!(detect_provider("gpt-3.5-turbo"), Provider::OpenAI);
        assert_eq!(detect_provider("o1-preview"), Provider::OpenAI);
        assert_eq!(detect_provider("GPT-4"), Provider::OpenAI);
    }

    #[test]
    fn test_detect_provider_anthropic() {
        assert_eq!(detect_provider("claude-3-opus"), Provider::Anthropic);
        assert_eq!(detect_provider("claude-2"), Provider::Anthropic);
        assert_eq!(detect_provider("CLAUDE-3"), Provider::Anthropic);
    }

    #[test]
    fn test_detect_provider_google() {
        assert_eq!(detect_provider("gemini-pro"), Provider::Google);
        assert_eq!(detect_provider("gemini-1.5-pro"), Provider::Google);
    }

    #[test]
    fn test_detect_provider_custom() {
        assert_eq!(detect_provider("mistral-large"), Provider::Custom);
        assert_eq!(detect_provider("unknown-model"), Provider::Custom);
    }

    #[test]
    fn test_callback_options_builder() {
        let opts = CallbackOptions::new()
            .project_id("my-project")
            .environment("production")
            .user_identifier("user-123")
            .capture_content(true)
            .content_max_length(5000);

        assert_eq!(opts.project_id, Some("my-project".to_string()));
        assert_eq!(opts.environment, Some("production".to_string()));
        assert_eq!(opts.user_identifier, Some("user-123".to_string()));
        assert!(opts.capture_content);
        assert_eq!(opts.content_max_length, 5000);
    }

    // Tests that require tokio runtime
    #[tokio::test]
    async fn test_handler_creation() {
        let client = Arc::new(DiagnyxClient::with_config(
            crate::DiagnyxConfig::new("test-key").base_url("http://localhost:9999"),
        ));
        let handler = DiagnyxCallbackHandler::new(client.clone());
        assert!(handler.call_contexts.lock().unwrap().is_empty());
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_handler_builder_pattern() {
        let client = Arc::new(DiagnyxClient::with_config(
            crate::DiagnyxConfig::new("test-key").base_url("http://localhost:9999"),
        ));
        let handler = DiagnyxCallbackHandler::new(client.clone())
            .with_project_id("test-project")
            .with_environment("test")
            .with_user_identifier("test-user")
            .with_capture_content(true)
            .with_content_max_length(5000);

        assert_eq!(handler.options.project_id, Some("test-project".to_string()));
        assert_eq!(handler.options.environment, Some("test".to_string()));
        assert_eq!(
            handler.options.user_identifier,
            Some("test-user".to_string())
        );
        assert!(handler.options.capture_content);
        assert_eq!(handler.options.content_max_length, 5000);
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_on_llm_start_generates_run_id() {
        let client = Arc::new(DiagnyxClient::with_config(
            crate::DiagnyxConfig::new("test-key").base_url("http://localhost:9999"),
        ));
        let handler = DiagnyxCallbackHandler::new(client.clone());

        let run_id = handler.on_llm_start("gpt-4", "Hello");

        assert!(!run_id.is_empty());
        // Verify it's a valid UUID format
        assert!(uuid::Uuid::parse_str(&run_id).is_ok());
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_on_llm_start_stores_context() {
        let client = Arc::new(DiagnyxClient::with_config(
            crate::DiagnyxConfig::new("test-key").base_url("http://localhost:9999"),
        ));
        let handler = DiagnyxCallbackHandler::new(client.clone());

        let run_id = handler.on_llm_start("gpt-4", "Hello");

        let contexts = handler.call_contexts.lock().unwrap();
        assert!(contexts.contains_key(&run_id));
        assert_eq!(contexts.get(&run_id).unwrap().model, "gpt-4");
        drop(contexts);
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_on_llm_end_removes_context() {
        let client = Arc::new(DiagnyxClient::with_config(
            crate::DiagnyxConfig::new("test-key").base_url("http://localhost:9999"),
        ));
        let handler = DiagnyxCallbackHandler::new(client.clone());

        let run_id = handler.on_llm_start("gpt-4", "Hello");
        handler.on_llm_end(&run_id, "gpt-4", "Hi there!", 10, 5);

        // Give the spawned task a moment to complete
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;

        let contexts = handler.call_contexts.lock().unwrap();
        assert!(!contexts.contains_key(&run_id));
        drop(contexts);
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_on_llm_error_removes_context() {
        let client = Arc::new(DiagnyxClient::with_config(
            crate::DiagnyxConfig::new("test-key").base_url("http://localhost:9999"),
        ));
        let handler = DiagnyxCallbackHandler::new(client.clone());

        let run_id = handler.on_llm_start("gpt-4", "Hello");
        handler.on_llm_error(&run_id, "gpt-4", "API error");

        // Give the spawned task a moment to complete
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;

        let contexts = handler.call_contexts.lock().unwrap();
        assert!(!contexts.contains_key(&run_id));
        drop(contexts);
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_chain_callbacks_are_no_ops() {
        let client = Arc::new(DiagnyxClient::with_config(
            crate::DiagnyxConfig::new("test-key").base_url("http://localhost:9999"),
        ));
        let handler = DiagnyxCallbackHandler::new(client.clone());

        // These should not panic
        handler.on_chain_start("test-chain", "{}");
        handler.on_chain_end("{}");
        handler.on_chain_error("error");
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_tool_callbacks_are_no_ops() {
        let client = Arc::new(DiagnyxClient::with_config(
            crate::DiagnyxConfig::new("test-key").base_url("http://localhost:9999"),
        ));
        let handler = DiagnyxCallbackHandler::new(client.clone());

        // These should not panic
        handler.on_tool_start("test-tool", "input");
        handler.on_tool_end("output");
        handler.on_tool_error("error");
        let _ = client.shutdown().await;
    }

    #[tokio::test]
    async fn test_concurrent_calls() {
        let client = Arc::new(DiagnyxClient::with_config(
            crate::DiagnyxConfig::new("test-key").base_url("http://localhost:9999"),
        ));
        let handler = DiagnyxCallbackHandler::new(client.clone());

        // Start two concurrent calls
        let run_id1 = handler.on_llm_start("gpt-4", "First");
        let run_id2 = handler.on_llm_start("claude-3", "Second");

        // End in reverse order
        handler.on_llm_end(&run_id2, "claude-3", "Second response", 10, 5);
        handler.on_llm_end(&run_id1, "gpt-4", "First response", 8, 4);

        // Give the spawned tasks a moment to complete
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;

        let contexts = handler.call_contexts.lock().unwrap();
        assert!(contexts.is_empty());
        drop(contexts);
        let _ = client.shutdown().await;
    }
}
