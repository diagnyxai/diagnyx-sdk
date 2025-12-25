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

mod client;
mod types;
mod error;

pub use client::DiagnyxClient;
pub use types::*;
pub use error::DiagnyxError;
