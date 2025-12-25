package io.diagnyx.sdk;

/**
 * Configuration for the Diagnyx client.
 */
public class DiagnyxConfig {
    private String apiKey;
    private String baseUrl = "https://api.diagnyx.io";
    private int batchSize = 100;
    private int flushIntervalMs = 5000;
    private int maxRetries = 3;
    private boolean debug = false;

    public DiagnyxConfig(String apiKey) {
        if (apiKey == null || apiKey.isEmpty()) {
            throw new IllegalArgumentException("API key is required");
        }
        this.apiKey = apiKey;
    }

    public static Builder builder(String apiKey) {
        return new Builder(apiKey);
    }

    public static class Builder {
        private final DiagnyxConfig config;

        public Builder(String apiKey) {
            this.config = new DiagnyxConfig(apiKey);
        }

        public Builder baseUrl(String baseUrl) {
            config.baseUrl = baseUrl;
            return this;
        }

        public Builder batchSize(int batchSize) {
            config.batchSize = batchSize;
            return this;
        }

        public Builder flushIntervalMs(int flushIntervalMs) {
            config.flushIntervalMs = flushIntervalMs;
            return this;
        }

        public Builder maxRetries(int maxRetries) {
            config.maxRetries = maxRetries;
            return this;
        }

        public Builder debug(boolean debug) {
            config.debug = debug;
            return this;
        }

        public DiagnyxConfig build() {
            return config;
        }
    }

    // Getters
    public String getApiKey() { return apiKey; }
    public String getBaseUrl() { return baseUrl; }
    public int getBatchSize() { return batchSize; }
    public int getFlushIntervalMs() { return flushIntervalMs; }
    public int getMaxRetries() { return maxRetries; }
    public boolean isDebug() { return debug; }
}
