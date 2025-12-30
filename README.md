# Diagnyx SDKs

Official SDKs for [Diagnyx](https://diagnyx.io) - LLM cost tracking and analytics platform.

Track every LLM API call with a single line of code. Get real-time visibility into costs, latency, and usage across all your AI applications.

## Available SDKs

| Language | Package | Install |
|----------|---------|---------|
| **Node.js/TypeScript** | [@diagnyx/node](./node) | `npm install @diagnyx/node` |
| **Python** | [diagnyx](./python) | `pip install diagnyx` |
| **Go** | [diagnyx-go](./go) | `go get github.com/diagnyxai/diagnyx-go` |
| **Java** | [diagnyx-sdk](./java) | Maven: `io.diagnyx:diagnyx-sdk:0.1.0` |
| **Rust** | [diagnyx](./rust) | `cargo add diagnyx` |

## Quick Start

### Node.js

```typescript
import { Diagnyx, wrapOpenAI } from '@diagnyx/node';
import OpenAI from 'openai';

const diagnyx = new Diagnyx({ apiKey: 'dx_live_xxx' });
const openai = wrapOpenAI(new OpenAI(), diagnyx);

// All calls are now automatically tracked
const response = await openai.chat.completions.create({
  model: 'gpt-4',
  messages: [{ role: 'user', content: 'Hello!' }]
});
```

### Python

```python
from diagnyx import Diagnyx, wrap_openai
from openai import OpenAI

with Diagnyx(api_key="dx_live_xxx") as diagnyx:
    client = wrap_openai(OpenAI(), diagnyx)

    # All calls are now automatically tracked
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello!"}]
    )
```

### Go

```go
import (
    "github.com/diagnyxai/diagnyx-go"
    "github.com/sashabaranov/go-openai"
)

dx := diagnyx.NewClient("dx_live_xxx")
defer dx.Close()

openaiClient := openai.NewClient("your-openai-key")
wrapped := diagnyx.WrapOpenAI(openaiClient, dx)

// All calls are now automatically tracked
resp, _ := wrapped.CreateChatCompletion(ctx, openai.ChatCompletionRequest{
    Model: openai.GPT4,
    Messages: []openai.ChatCompletionMessage{
        {Role: openai.ChatMessageRoleUser, Content: "Hello!"},
    },
})
```

### Java

```java
import io.diagnyx.sdk.*;

try (DiagnyxClient diagnyx = DiagnyxClient.create("dx_live_xxx")) {
    TrackingWrapper tracker = new TrackingWrapper(diagnyx);

    String response = tracker.track(Provider.OPENAI, "gpt-4", () -> {
        // Your LLM call here
        return TrackingWrapper.TrackedResult.of(result, inputTokens, outputTokens);
    });
}
```

### Rust

```rust
use diagnyx::{DiagnyxClient, LLMCall, Provider};

let client = DiagnyxClient::new("dx_live_xxx");

client.track(LLMCall::builder()
    .provider(Provider::OpenAI)
    .model("gpt-4")
    .input_tokens(100)
    .output_tokens(50)
    .latency_ms(250)
    .build()
).await;

client.shutdown().await?;
```

## LangChain Integration

Native callback handlers for LangChain across all supported languages:

### Python (LangChain)

```python
from diagnyx import Diagnyx, DiagnyxCallbackHandler
from langchain_openai import ChatOpenAI

diagnyx = Diagnyx(api_key="dx_live_xxx")
handler = DiagnyxCallbackHandler(diagnyx, project_id="my-project")

llm = ChatOpenAI(model="gpt-4", callbacks=[handler])
response = llm.invoke("Hello, world!")
```

### Node.js (LangChain.js)

```typescript
import { Diagnyx, DiagnyxCallbackHandler } from '@diagnyx/node';
import { ChatOpenAI } from '@langchain/openai';

const diagnyx = new Diagnyx({ apiKey: 'dx_live_xxx' });
const handler = new DiagnyxCallbackHandler(diagnyx, { projectId: 'my-project' });

const llm = new ChatOpenAI({ model: 'gpt-4', callbacks: [handler] });
const response = await llm.invoke('Hello, world!');
```

### Go (langchaingo)

```go
import (
    "github.com/diagnyxai/diagnyx-go"
    "github.com/diagnyxai/diagnyx-go/callbacks"
    "github.com/tmc/langchaingo/llms/openai"
)

dx := diagnyx.NewClient("dx_live_xxx")
defer dx.Close()

handler := callbacks.NewDiagnyxHandler(dx,
    callbacks.WithProjectID("my-project"),
    callbacks.WithEnvironment("production"),
)

llm, _ := openai.New(openai.WithModel("gpt-4"))
// Use handler with langchaingo callbacks
```

### Java (LangChain4j)

```java
import io.diagnyx.sdk.*;
import io.diagnyx.sdk.callbacks.DiagnyxChatModelListener;

try (DiagnyxClient diagnyx = DiagnyxClient.create("dx_live_xxx")) {
    DiagnyxChatModelListener listener = new DiagnyxChatModelListener(diagnyx)
        .projectId("my-project")
        .environment("production");

    // Use listener with LangChain4j ChatLanguageModel
}
```

### Rust (langchain-rust)

```rust
use diagnyx::{DiagnyxClient, DiagnyxCallbackHandler};
use std::sync::Arc;

let client = Arc::new(DiagnyxClient::new("dx_live_xxx"));
let handler = DiagnyxCallbackHandler::new(client.clone())
    .with_project_id("my-project")
    .with_environment("production");

// Track LLM calls
let run_id = handler.on_llm_start("gpt-4", "Hello!");
// ... LLM call happens ...
handler.on_llm_end(&run_id, "gpt-4", "Hi there!", 10, 5);
```

## Features

All SDKs include:

- **Automatic Batching** - Calls are batched and sent efficiently
- **Retry Logic** - Exponential backoff on failures
- **Non-blocking** - Tracking never slows down your LLM calls
- **Graceful Shutdown** - Flush remaining calls on exit
- **Debug Mode** - Optional logging for troubleshooting
- **LangChain Support** - Native callback handlers for LangChain/LangChain.js

## Supported Providers

- OpenAI (GPT-4, GPT-3.5, embeddings)
- Anthropic (Claude 3, Claude 2)
- Google (Gemini)
- Azure OpenAI
- AWS Bedrock
- Any custom LLM endpoint

## Getting Your API Key

1. Sign up at [diagnyx.io](https://diagnyx.io)
2. Go to Settings → API Keys
3. Create a new key with `inference:write` scope

## Documentation

- [Full Documentation](https://docs.diagnyx.io)
- [API Reference](https://docs.diagnyx.io/api)
- [Dashboard](https://app.diagnyx.io)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](./LICENSE) for details.
