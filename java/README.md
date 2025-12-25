# Diagnyx Java SDK

Track and monitor your LLM API costs with Diagnyx.

## Installation

### Maven
```xml
<dependency>
    <groupId>io.diagnyx</groupId>
    <artifactId>diagnyx-sdk</artifactId>
    <version>0.1.0</version>
</dependency>
```

### Gradle
```groovy
implementation 'io.diagnyx:diagnyx-sdk:0.1.0'
```

## Quick Start

```java
import io.diagnyx.sdk.*;

public class Example {
    public static void main(String[] args) {
        // Initialize client
        try (DiagnyxClient diagnyx = DiagnyxClient.create("dx_live_your_api_key")) {

            // Create a tracking wrapper
            TrackingWrapper tracker = new TrackingWrapper(diagnyx);

            // Track an LLM call
            String response = tracker.track(Provider.OPENAI, "gpt-4", () -> {
                // Your LLM call here
                // Return TrackedResult with value and token counts
                return TrackingWrapper.TrackedResult.of(
                    "Hello from GPT-4!",
                    50,  // input tokens
                    20   // output tokens
                );
            });

            System.out.println(response);
        }
    }
}
```

## Configuration

```java
DiagnyxConfig config = DiagnyxConfig.builder("dx_live_your_api_key")
    .baseUrl("https://api.diagnyx.io")
    .batchSize(100)
    .flushIntervalMs(5000)
    .maxRetries(3)
    .debug(true)
    .build();

DiagnyxClient client = DiagnyxClient.create(config);
```

## Manual Tracking

```java
// Build and track an LLM call manually
LLMCall call = LLMCall.builder()
    .provider(Provider.ANTHROPIC)
    .model("claude-3-sonnet")
    .inputTokens(100)
    .outputTokens(50)
    .latencyMs(250)
    .status(CallStatus.SUCCESS)
    .projectId("my-project")
    .environment("production")
    .build();

diagnyx.track(call);
```

## Track Options

```java
TrackingWrapper.TrackOptions options = TrackingWrapper.TrackOptions.builder()
    .projectId("my-project")
    .environment("production")
    .userIdentifier("user-123")
    .traceId("trace-abc")
    .spanId("span-xyz")
    .metadata(Map.of("custom_field", "value"))
    .build();

TrackingWrapper tracker = new TrackingWrapper(diagnyx, options);
```

## Error Handling

Errors are automatically tracked with status `ERROR`:

```java
try {
    tracker.track(Provider.OPENAI, "gpt-4", () -> {
        throw new RuntimeException("API error");
    });
} catch (RuntimeException e) {
    // Error is logged, call is still tracked
}
```

## License

MIT
