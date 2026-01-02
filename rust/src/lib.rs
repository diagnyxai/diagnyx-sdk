//! Diagnyx Rust SDK for LLM cost tracking and analytics.
//!
//! # Quick Start
//!
//! ```rust,no_run
//! use diagnyx::{DiagnyxClient, LLMCall, Provider, CallStatus};
//!
//! #[tokio::main]
//! async fn main() {
//!     let client = DiagnyxClient::new("dx_live_your_api_key");
//!
//!     // Track an LLM call
//!     client.track(LLMCall::builder()
//!         .provider(Provider::OpenAI)
//!         .model("gpt-4")
//!         .input_tokens(100)
//!         .output_tokens(50)
//!         .latency_ms(250)
//!         .build()
//!     ).await;
//!
//!     // Flush remaining calls before exit
//!     client.flush().await.unwrap();
//! }
//! ```
//!
//! # Streaming Guardrails
//!
//! ```rust,no_run
//! use diagnyx::guardrails::{StreamingGuardrails, StreamingGuardrailsConfig, StreamingEvent};
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let config = StreamingGuardrailsConfig::new(
//!         "dx_live_your_api_key",
//!         "org-123",
//!         "proj-456",
//!     );
//!
//!     let client = StreamingGuardrails::new(config);
//!
//!     // Start a session and evaluate tokens
//!     let session = client.start_session(Some("What is 2+2?")).await?;
//!
//!     for token in vec!["The", "answer", "is", "4"] {
//!         match client.evaluate_token(token).await? {
//!             StreamingEvent::TokenAllowed(data) => println!("OK: {}", data.token),
//!             StreamingEvent::EarlyTermination(data) => {
//!                 println!("Blocked: {}", data.reason);
//!                 break;
//!             }
//!             _ => {}
//!         }
//!     }
//!
//!     let result = client.complete_session().await?;
//!     println!("Allowed: {}", result.allowed);
//!     Ok(())
//! }
//! ```

mod client;
mod types;
mod error;
pub mod callbacks;
pub mod guardrails;
pub mod feedback;

pub use client::DiagnyxClient;
pub use types::*;
pub use error::DiagnyxError;
pub use callbacks::{DiagnyxCallbackHandler, CallbackOptions};
pub use feedback::{
    FeedbackClient, FeedbackClientConfig, Feedback, FeedbackType, FeedbackSentiment,
    FeedbackOptions, FeedbackOptionsBuilder, FeedbackSummary, ListFeedbackOptions,
    FeedbackListResult,
};
