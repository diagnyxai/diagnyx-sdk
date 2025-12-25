# Diagnyx Go SDK

Track and monitor your LLM API costs with Diagnyx.

## Installation

```bash
go get github.com/diagnyxai/diagnyx-go
```

## Quick Start

```go
package main

import (
    "context"
    "github.com/diagnyxai/diagnyx-go"
    "github.com/sashabaranov/go-openai"
)

func main() {
    // Initialize Diagnyx client
    dx := diagnyx.NewClient("dx_live_your_api_key")
    defer dx.Close()

    // Wrap your OpenAI client
    openaiClient := openai.NewClient("your-openai-key")
    wrapped := diagnyx.WrapOpenAI(openaiClient, dx)

    // All calls are now automatically tracked
    resp, err := wrapped.CreateChatCompletion(context.Background(), openai.ChatCompletionRequest{
        Model: openai.GPT4,
        Messages: []openai.ChatCompletionMessage{
            {Role: openai.ChatMessageRoleUser, Content: "Hello!"},
        },
    })
    // ...
}
```

## Configuration

```go
config := diagnyx.Config{
    APIKey:          "dx_live_your_api_key",
    BaseURL:         "https://api.diagnyx.io",
    BatchSize:       100,   // Flush after 100 calls
    FlushIntervalMs: 5000,  // Flush every 5 seconds
    MaxRetries:      3,
    Debug:           false,
}

client := diagnyx.NewClientWithConfig(config)
```

## Manual Tracking

```go
// Track any LLM call manually
err := diagnyx.TrackCall(dx, diagnyx.ProviderAnthropic, "claude-3-sonnet", func() (int, int, error) {
    // Your LLM call here
    return inputTokens, outputTokens, nil
}, diagnyx.TrackOptions{
    ProjectID:   "my-project",
    Environment: "production",
})
```

## Track Options

```go
opts := diagnyx.TrackOptions{
    ProjectID:      "my-project",
    Environment:    "production",
    UserIdentifier: "user-123",
    TraceID:        "trace-abc",
    SpanID:         "span-xyz",
    Metadata: map[string]interface{}{
        "custom_field": "value",
    },
}

wrapped := diagnyx.WrapOpenAI(openaiClient, dx, opts)
```

## License

MIT
