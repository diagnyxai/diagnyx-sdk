//! Streaming guardrails module for real-time LLM output validation.
//!
//! This module provides streaming guardrail evaluation capabilities, allowing
//! you to validate LLM outputs token-by-token with early termination on blocking
//! policy violations.
//!
//! # Example
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
//!     // Start a session
//!     let session = client.start_session(Some("What is the weather?")).await?;
//!     println!("Session started: {}", session.session_id);
//!
//!     // Evaluate tokens
//!     for token in vec!["The", "weather", "is", "sunny"] {
//!         let event = client.evaluate_token(token).await?;
//!         match event {
//!             StreamingEvent::TokenAllowed(data) => {
//!                 println!("Token allowed: {}", data.token);
//!             }
//!             StreamingEvent::EarlyTermination(data) => {
//!                 println!("Terminated: {}", data.reason);
//!                 break;
//!             }
//!             _ => {}
//!         }
//!     }
//!
//!     // Complete the session
//!     let final_session = client.complete_session().await?;
//!     println!("Session complete, allowed: {}", final_session.allowed);
//!
//!     Ok(())
//! }
//! ```

mod client;
mod types;

pub use client::{stream_with_guardrails, GuardrailViolationError, StreamingGuardrails};
pub use types::{
    EarlyTerminationData, EnforcementLevel, ErrorData, GuardrailSession, GuardrailViolation,
    SessionCompleteData, SessionStartedData, StreamingEvent, StreamingEventType,
    StreamingGuardrailsConfig, TokenAllowedData, ViolationDetectedData,
};
