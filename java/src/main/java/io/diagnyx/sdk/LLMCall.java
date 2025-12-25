package io.diagnyx.sdk;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;
import java.util.Map;

/**
 * Represents a single LLM API call.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public class LLMCall {

    @JsonProperty("provider")
    private Provider provider;

    @JsonProperty("model")
    private String model;

    @JsonProperty("endpoint")
    private String endpoint;

    @JsonProperty("input_tokens")
    private int inputTokens;

    @JsonProperty("output_tokens")
    private int outputTokens;

    @JsonProperty("latency_ms")
    private long latencyMs;

    @JsonProperty("ttft_ms")
    private Long ttftMs;

    @JsonProperty("status")
    private CallStatus status;

    @JsonProperty("error_code")
    private String errorCode;

    @JsonProperty("error_message")
    private String errorMessage;

    @JsonProperty("project_id")
    private String projectId;

    @JsonProperty("environment")
    private String environment;

    @JsonProperty("user_identifier")
    private String userIdentifier;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("span_id")
    private String spanId;

    @JsonProperty("metadata")
    private Map<String, Object> metadata;

    @JsonProperty("timestamp")
    private Instant timestamp;

    public LLMCall() {
        this.timestamp = Instant.now();
        this.status = CallStatus.SUCCESS;
    }

    // Builder pattern
    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private final LLMCall call = new LLMCall();

        public Builder provider(Provider provider) {
            call.provider = provider;
            return this;
        }

        public Builder model(String model) {
            call.model = model;
            return this;
        }

        public Builder endpoint(String endpoint) {
            call.endpoint = endpoint;
            return this;
        }

        public Builder inputTokens(int inputTokens) {
            call.inputTokens = inputTokens;
            return this;
        }

        public Builder outputTokens(int outputTokens) {
            call.outputTokens = outputTokens;
            return this;
        }

        public Builder latencyMs(long latencyMs) {
            call.latencyMs = latencyMs;
            return this;
        }

        public Builder ttftMs(Long ttftMs) {
            call.ttftMs = ttftMs;
            return this;
        }

        public Builder status(CallStatus status) {
            call.status = status;
            return this;
        }

        public Builder errorCode(String errorCode) {
            call.errorCode = errorCode;
            return this;
        }

        public Builder errorMessage(String errorMessage) {
            call.errorMessage = errorMessage;
            return this;
        }

        public Builder projectId(String projectId) {
            call.projectId = projectId;
            return this;
        }

        public Builder environment(String environment) {
            call.environment = environment;
            return this;
        }

        public Builder userIdentifier(String userIdentifier) {
            call.userIdentifier = userIdentifier;
            return this;
        }

        public Builder traceId(String traceId) {
            call.traceId = traceId;
            return this;
        }

        public Builder spanId(String spanId) {
            call.spanId = spanId;
            return this;
        }

        public Builder metadata(Map<String, Object> metadata) {
            call.metadata = metadata;
            return this;
        }

        public Builder timestamp(Instant timestamp) {
            call.timestamp = timestamp;
            return this;
        }

        public LLMCall build() {
            return call;
        }
    }

    // Getters and setters
    public Provider getProvider() { return provider; }
    public void setProvider(Provider provider) { this.provider = provider; }

    public String getModel() { return model; }
    public void setModel(String model) { this.model = model; }

    public String getEndpoint() { return endpoint; }
    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }

    public int getInputTokens() { return inputTokens; }
    public void setInputTokens(int inputTokens) { this.inputTokens = inputTokens; }

    public int getOutputTokens() { return outputTokens; }
    public void setOutputTokens(int outputTokens) { this.outputTokens = outputTokens; }

    public long getLatencyMs() { return latencyMs; }
    public void setLatencyMs(long latencyMs) { this.latencyMs = latencyMs; }

    public Long getTtftMs() { return ttftMs; }
    public void setTtftMs(Long ttftMs) { this.ttftMs = ttftMs; }

    public CallStatus getStatus() { return status; }
    public void setStatus(CallStatus status) { this.status = status; }

    public String getErrorCode() { return errorCode; }
    public void setErrorCode(String errorCode) { this.errorCode = errorCode; }

    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }

    public String getProjectId() { return projectId; }
    public void setProjectId(String projectId) { this.projectId = projectId; }

    public String getEnvironment() { return environment; }
    public void setEnvironment(String environment) { this.environment = environment; }

    public String getUserIdentifier() { return userIdentifier; }
    public void setUserIdentifier(String userIdentifier) { this.userIdentifier = userIdentifier; }

    public String getTraceId() { return traceId; }
    public void setTraceId(String traceId) { this.traceId = traceId; }

    public String getSpanId() { return spanId; }
    public void setSpanId(String spanId) { this.spanId = spanId; }

    public Map<String, Object> getMetadata() { return metadata; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }

    public Instant getTimestamp() { return timestamp; }
    public void setTimestamp(Instant timestamp) { this.timestamp = timestamp; }
}
