package io.diagnyx.sdk.guardrails;

/**
 * Configuration for the StreamingGuardrails client.
 */
public class StreamingGuardrailsConfig {
    private final String apiKey;
    private final String organizationId;
    private final String projectId;
    private String baseUrl = "https://api.diagnyx.io";
    private int timeout = 30;
    private int evaluateEveryNTokens = 10;
    private boolean enableEarlyTermination = true;
    private boolean debug = false;

    public StreamingGuardrailsConfig(String apiKey, String organizationId, String projectId) {
        this.apiKey = apiKey;
        this.organizationId = organizationId;
        this.projectId = projectId;
    }

    public String getApiKey() { return apiKey; }
    public String getOrganizationId() { return organizationId; }
    public String getProjectId() { return projectId; }
    public String getBaseUrl() { return baseUrl; }
    public int getTimeout() { return timeout; }
    public int getEvaluateEveryNTokens() { return evaluateEveryNTokens; }
    public boolean isEnableEarlyTermination() { return enableEarlyTermination; }
    public boolean isDebug() { return debug; }

    public StreamingGuardrailsConfig withBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
        return this;
    }

    public StreamingGuardrailsConfig withTimeout(int timeout) {
        this.timeout = timeout;
        return this;
    }

    public StreamingGuardrailsConfig withEvaluateEveryNTokens(int evaluateEveryNTokens) {
        this.evaluateEveryNTokens = evaluateEveryNTokens;
        return this;
    }

    public StreamingGuardrailsConfig withEnableEarlyTermination(boolean enableEarlyTermination) {
        this.enableEarlyTermination = enableEarlyTermination;
        return this;
    }

    public StreamingGuardrailsConfig withDebug(boolean debug) {
        this.debug = debug;
        return this;
    }
}
