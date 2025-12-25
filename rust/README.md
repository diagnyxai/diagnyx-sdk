# Diagnyx Rust SDK

Track and monitor your LLM API costs with Diagnyx.

## Installation

Add to your `Cargo.toml`:

```toml
[dependencies]
diagnyx = "0.1"
tokio = { version = "1", features = ["rt-multi-thread"] }
```

## Quick Start

```rust
use diagnyx::{DiagnyxClient, LLMCall, Provider, CallStatus};

#[tokio::main]
async fn main() {
    // Initialize client
    let client = DiagnyxClient::new("dx_live_your_api_key");

    // Track an LLM call
    client.track(LLMCall::builder()
        .provider(Provider::OpenAI)
        .model("gpt-4")
        .input_tokens(100)
        .output_tokens(50)
        .latency_ms(250)
        .build()
    ).await;

    // Flush remaining calls before exit
    client.shutdown().await.unwrap();
}
```

## Configuration

```rust
use diagnyx::{DiagnyxClient, DiagnyxConfig};

let config = DiagnyxConfig::new("dx_live_your_api_key")
    .base_url("https://api.diagnyx.io")
    .batch_size(100)
    .flush_interval_ms(5000)
    .max_retries(3)
    .debug(true);

let client = DiagnyxClient::with_config(config);
```

## Building LLM Calls

```rust
use diagnyx::{LLMCall, Provider, CallStatus};
use std::collections::HashMap;

let call = LLMCall::builder()
    .provider(Provider::Anthropic)
    .model("claude-3-sonnet")
    .endpoint("/v1/messages")
    .input_tokens(150)
    .output_tokens(75)
    .latency_ms(320)
    .ttft_ms(80)
    .status(CallStatus::Success)
    .project_id("my-project")
    .environment("production")
    .user_identifier("user-123")
    .trace_id("trace-abc")
    .span_id("span-xyz")
    .metadata(HashMap::from([
        ("custom".to_string(), serde_json::json!("value"))
    ]))
    .build();

client.track(call).await;
```

## Track with Timing Helper

```rust
use diagnyx::{DiagnyxClient, Provider, track_call};

let result = track_call(&client, Provider::OpenAI, "gpt-4", || {
    // Your LLM call here
    // Return (result, input_tokens, output_tokens)
    Ok(("Hello from GPT-4!".to_string(), 50, 20))
}).await?;
```

## Error Handling

Errors are automatically tracked:

```rust
let call = LLMCall::builder()
    .provider(Provider::OpenAI)
    .model("gpt-4")
    .input_tokens(0)
    .output_tokens(0)
    .latency_ms(150)
    .status(CallStatus::Error)
    .error_code("rate_limit")
    .error_message("Rate limit exceeded")
    .build();

client.track(call).await;
```

## Batch Tracking

```rust
let calls = vec![
    LLMCall::builder()
        .provider(Provider::OpenAI)
        .model("gpt-4")
        .input_tokens(100)
        .output_tokens(50)
        .latency_ms(200)
        .build(),
    LLMCall::builder()
        .provider(Provider::Anthropic)
        .model("claude-3-haiku")
        .input_tokens(80)
        .output_tokens(40)
        .latency_ms(150)
        .build(),
];

client.track_all(calls).await;
```

## License

MIT
