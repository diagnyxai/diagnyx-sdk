use thiserror::Error;

/// Errors that can occur when using the Diagnyx client.
#[derive(Error, Debug)]
pub enum DiagnyxError {
    #[error("HTTP request failed: {0}")]
    HttpError(#[from] reqwest::Error),

    #[error("JSON serialization error: {0}")]
    SerializationError(#[from] serde_json::Error),

    #[error("API error: HTTP {status_code} - {message}")]
    ApiError { status_code: u16, message: String },

    #[error("Configuration error: {0}")]
    ConfigError(String),

    #[error("Max retries exceeded")]
    MaxRetriesExceeded,

    #[error("Guardrail violation: {0}")]
    ViolationError(Box<dyn std::error::Error + Send + Sync>),
}
