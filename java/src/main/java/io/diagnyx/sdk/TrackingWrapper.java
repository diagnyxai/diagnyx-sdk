package io.diagnyx.sdk;

import java.time.Instant;
import java.util.Map;
import java.util.function.Supplier;

/**
 * Utility class for wrapping LLM calls with automatic tracking.
 */
public class TrackingWrapper {
    private final DiagnyxClient client;
    private final TrackOptions defaultOptions;

    public TrackingWrapper(DiagnyxClient client) {
        this(client, TrackOptions.builder().build());
    }

    public TrackingWrapper(DiagnyxClient client, TrackOptions defaultOptions) {
        this.client = client;
        this.defaultOptions = defaultOptions;
    }

    /**
     * Track an LLM call with automatic timing.
     *
     * @param provider The LLM provider
     * @param model The model name
     * @param call The function that makes the LLM call and returns token counts
     * @return The result of the LLM call
     */
    public <T> T track(Provider provider, String model, TrackedCall<T> call) {
        return track(provider, model, call, defaultOptions);
    }

    /**
     * Track an LLM call with automatic timing and custom options.
     */
    public <T> T track(Provider provider, String model, TrackedCall<T> call, TrackOptions options) {
        long startTime = System.currentTimeMillis();

        try {
            TrackedResult<T> result = call.execute();
            long latencyMs = System.currentTimeMillis() - startTime;

            LLMCall.Builder builder = LLMCall.builder()
                    .provider(provider)
                    .model(model)
                    .inputTokens(result.getInputTokens())
                    .outputTokens(result.getOutputTokens())
                    .latencyMs(latencyMs)
                    .status(CallStatus.SUCCESS)
                    .projectId(options.getProjectId())
                    .environment(options.getEnvironment())
                    .userIdentifier(options.getUserIdentifier())
                    .traceId(options.getTraceId())
                    .spanId(options.getSpanId())
                    .metadata(options.getMetadata())
                    .timestamp(Instant.now());

            // Add content if provided
            if (result.getFullPrompt() != null) {
                builder.fullPrompt(result.getFullPrompt());
            }
            if (result.getFullResponse() != null) {
                builder.fullResponse(result.getFullResponse());
            }

            client.track(builder.build());
            return result.getValue();

        } catch (Exception e) {
            long latencyMs = System.currentTimeMillis() - startTime;

            LLMCall llmCall = LLMCall.builder()
                    .provider(provider)
                    .model(model)
                    .inputTokens(0)
                    .outputTokens(0)
                    .latencyMs(latencyMs)
                    .status(CallStatus.ERROR)
                    .errorMessage(e.getMessage())
                    .projectId(options.getProjectId())
                    .environment(options.getEnvironment())
                    .userIdentifier(options.getUserIdentifier())
                    .traceId(options.getTraceId())
                    .spanId(options.getSpanId())
                    .metadata(options.getMetadata())
                    .timestamp(Instant.now())
                    .build();

            client.track(llmCall);
            throw e instanceof RuntimeException ? (RuntimeException) e : new RuntimeException(e);
        }
    }

    /**
     * Functional interface for tracked calls.
     */
    @FunctionalInterface
    public interface TrackedCall<T> {
        TrackedResult<T> execute() throws Exception;
    }

    /**
     * Result of a tracked call including token counts and optional content.
     */
    public static class TrackedResult<T> {
        private final T value;
        private final int inputTokens;
        private final int outputTokens;
        private final String fullPrompt;
        private final String fullResponse;

        public TrackedResult(T value, int inputTokens, int outputTokens) {
            this(value, inputTokens, outputTokens, null, null);
        }

        public TrackedResult(T value, int inputTokens, int outputTokens, String fullPrompt, String fullResponse) {
            this.value = value;
            this.inputTokens = inputTokens;
            this.outputTokens = outputTokens;
            this.fullPrompt = fullPrompt;
            this.fullResponse = fullResponse;
        }

        public static <T> TrackedResult<T> of(T value, int inputTokens, int outputTokens) {
            return new TrackedResult<>(value, inputTokens, outputTokens);
        }

        public static <T> TrackedResult<T> of(T value, int inputTokens, int outputTokens, String fullPrompt, String fullResponse) {
            return new TrackedResult<>(value, inputTokens, outputTokens, fullPrompt, fullResponse);
        }

        public T getValue() { return value; }
        public int getInputTokens() { return inputTokens; }
        public int getOutputTokens() { return outputTokens; }
        public String getFullPrompt() { return fullPrompt; }
        public String getFullResponse() { return fullResponse; }
    }

    /**
     * Options for tracking.
     */
    public static class TrackOptions {
        private String projectId;
        private String environment;
        private String userIdentifier;
        private String traceId;
        private String spanId;
        private Map<String, Object> metadata;

        private TrackOptions() {}

        public static Builder builder() {
            return new Builder();
        }

        public static class Builder {
            private final TrackOptions options = new TrackOptions();

            public Builder projectId(String projectId) {
                options.projectId = projectId;
                return this;
            }

            public Builder environment(String environment) {
                options.environment = environment;
                return this;
            }

            public Builder userIdentifier(String userIdentifier) {
                options.userIdentifier = userIdentifier;
                return this;
            }

            public Builder traceId(String traceId) {
                options.traceId = traceId;
                return this;
            }

            public Builder spanId(String spanId) {
                options.spanId = spanId;
                return this;
            }

            public Builder metadata(Map<String, Object> metadata) {
                options.metadata = metadata;
                return this;
            }

            public TrackOptions build() {
                return options;
            }
        }

        public String getProjectId() { return projectId; }
        public String getEnvironment() { return environment; }
        public String getUserIdentifier() { return userIdentifier; }
        public String getTraceId() { return traceId; }
        public String getSpanId() { return spanId; }
        public Map<String, Object> getMetadata() { return metadata; }
    }
}
