package io.diagnyx.sdk.guardrails;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.stream.Stream;

/**
 * Token-by-token streaming guardrail for LLM output validation.
 * <p>
 * Provides real-time evaluation of LLM response tokens against configured
 * guardrail policies with support for early termination on blocking violations.
 * <p>
 * Example:
 * <pre>{@code
 * StreamingGuardrailConfig config = StreamingGuardrailConfig.builder()
 *     .apiKey("dx_...")
 *     .organizationId("org_123")
 *     .projectId("proj_456")
 *     .build();
 *
 * try (StreamingGuardrail guardrail = new StreamingGuardrail(config)) {
 *     StreamingGuardrailSession session = guardrail.startSession(null);
 *
 *     for (String token : tokenStream) {
 *         Optional<String> filtered = guardrail.evaluate(token, false);
 *         filtered.ifPresent(System.out::print);
 *     }
 *
 *     StreamingGuardrailSession completed = guardrail.completeSession();
 *     System.out.println("Allowed: " + completed.isAllowed());
 * }
 * }</pre>
 */
public class StreamingGuardrail implements AutoCloseable {
    private final StreamingGuardrailConfig config;
    private final ObjectMapper objectMapper;
    private StreamingGuardrailSession session;
    private final AtomicInteger tokenIndex;

    /**
     * Create a new streaming guardrail client.
     *
     * @param config Configuration for the guardrail
     */
    public StreamingGuardrail(StreamingGuardrailConfig config) {
        this.config = config;
        this.objectMapper = new ObjectMapper();
        this.tokenIndex = new AtomicInteger(0);
    }

    private void log(String message) {
        if (config.isDebug()) {
            System.out.println("[DiagnyxGuardrails] " + message);
        }
    }

    private String getBaseEndpoint() {
        String baseUrl = config.getBaseUrl().endsWith("/")
            ? config.getBaseUrl().substring(0, config.getBaseUrl().length() - 1)
            : config.getBaseUrl();
        return String.format("%s/api/v1/organizations/%s/guardrails", baseUrl, config.getOrganizationId());
    }

    /**
     * Start a new streaming guardrail session.
     *
     * @param inputText Optional input text to pre-evaluate
     * @return Session with details
     * @throws GuardrailsException if session creation fails
     */
    public StreamingGuardrailSession startSession(String inputText) throws GuardrailsException {
        try {
            ObjectNode payload = objectMapper.createObjectNode();
            payload.put("projectId", config.getProjectId());
            payload.put("evaluateEveryNTokens", config.getEvaluateEveryNTokens());
            payload.put("enableEarlyTermination", config.isEnableEarlyTermination());
            if (inputText != null) {
                payload.put("input", inputText);
            }

            URL url = new URL(getBaseEndpoint() + "/evaluate/stream/start");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Authorization", "Bearer " + config.getApiKey());
            conn.setRequestProperty("Accept", "application/json");
            conn.setConnectTimeout(config.getTimeout() * 1000);
            conn.setReadTimeout(config.getTimeout() * 1000);
            conn.setDoOutput(true);

            try (OutputStream os = conn.getOutputStream()) {
                os.write(objectMapper.writeValueAsBytes(payload));
            }

            int status = conn.getResponseCode();
            if (status != 200 && status != 201) {
                throw new GuardrailsException("Failed to start session: HTTP " + status);
            }

            JsonNode data = objectMapper.readTree(conn.getInputStream());
            String type = getString(data, "type");

            if ("session_started".equals(type)) {
                String sessionId = getString(data, "sessionId");
                List<String> policies = getStringList(data, "activePolicies");

                this.session = new StreamingGuardrailSession(
                    sessionId,
                    config.getOrganizationId(),
                    config.getProjectId(),
                    policies
                );
                this.tokenIndex.set(0);
                log("Session started: " + sessionId);
                return this.session;
            } else if ("error".equals(type)) {
                throw new GuardrailsException("Failed to start session: " + getString(data, "error"));
            }

            throw new GuardrailsException("Unexpected response type: " + type);
        } catch (GuardrailsException e) {
            throw e;
        } catch (Exception e) {
            throw new GuardrailsException("Failed to start session", e);
        }
    }

    /**
     * Evaluate a token against guardrail policies.
     *
     * @param token  The token text to evaluate
     * @param isLast Whether this is the last token
     * @return Optional containing the token if allowed, empty if blocked
     * @throws GuardrailsException        if evaluation fails
     * @throws GuardrailViolationException if a blocking violation occurs
     */
    public Optional<String> evaluate(String token, boolean isLast) throws GuardrailsException, GuardrailViolationException {
        return evaluate(token, null, isLast);
    }

    /**
     * Evaluate a token against guardrail policies with explicit index.
     *
     * @param token      The token text to evaluate
     * @param tokenIdx   Optional token index
     * @param isLast     Whether this is the last token
     * @return Optional containing the token if allowed, empty if blocked
     * @throws GuardrailsException        if evaluation fails
     * @throws GuardrailViolationException if a blocking violation occurs
     */
    public Optional<String> evaluate(String token, Integer tokenIdx, boolean isLast) throws GuardrailsException, GuardrailViolationException {
        if (session == null) {
            throw new GuardrailsException("No active session. Call startSession() first.");
        }

        int index = tokenIdx != null ? tokenIdx : tokenIndex.getAndIncrement();
        session.appendToAccumulatedText(token);

        try {
            ObjectNode payload = objectMapper.createObjectNode();
            payload.put("sessionId", session.getSessionId());
            payload.put("token", token);
            payload.put("tokenIndex", index);
            payload.put("isLast", isLast);

            URL url = new URL(getBaseEndpoint() + "/evaluate/stream");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Authorization", "Bearer " + config.getApiKey());
            conn.setRequestProperty("Accept", "text/event-stream");
            conn.setConnectTimeout(config.getTimeout() * 1000);
            conn.setReadTimeout(config.getTimeout() * 1000);
            conn.setDoOutput(true);

            try (OutputStream os = conn.getOutputStream()) {
                os.write(objectMapper.writeValueAsBytes(payload));
            }

            int status = conn.getResponseCode();
            if (status != 200) {
                throw new GuardrailsException("Token evaluation failed: HTTP " + status);
            }

            Optional<String> result = Optional.empty();

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    line = line.trim();
                    if (!line.startsWith("data: ")) {
                        continue;
                    }

                    try {
                        JsonNode data = objectMapper.readTree(line.substring(6));
                        String eventType = getString(data, "type");

                        switch (eventType) {
                            case "token_allowed":
                                session.setTokensProcessed(getInt(data, "tokenIndex") + 1);
                                result = Optional.of(token);
                                break;

                            case "violation_detected":
                                GuardrailViolation violation = parseViolation(data);
                                session.addViolation(violation);
                                if (violation.getEnforcementLevel() == EnforcementLevel.BLOCKING) {
                                    session.setAllowed(false);
                                }
                                break;

                            case "early_termination":
                                JsonNode blockingNode = data.has("blockingViolation")
                                    ? data.get("blockingViolation")
                                    : null;
                                GuardrailViolation blockingViolation = blockingNode != null
                                    ? parseViolation(blockingNode)
                                    : parseViolation(data);
                                session.setTerminated(true);
                                session.setTerminationReason(getString(data, "reason"));
                                session.setAllowed(false);
                                throw new GuardrailViolationException(blockingViolation, session);

                            case "session_complete":
                                session.setTokensProcessed(getInt(data, "totalTokens"));
                                session.setAllowed(getBoolean(data, "allowed"));
                                break;

                            case "error":
                                log("Error: " + getString(data, "error"));
                                break;
                        }
                    } catch (GuardrailViolationException e) {
                        throw e;
                    } catch (Exception e) {
                        log("Failed to parse event: " + e.getMessage());
                    }
                }
            }

            return result;
        } catch (GuardrailsException | GuardrailViolationException e) {
            throw e;
        } catch (Exception e) {
            throw new GuardrailsException("Token evaluation failed", e);
        }
    }

    /**
     * Evaluate tokens from a stream with guardrail protection.
     *
     * @param tokens     Stream of tokens to evaluate
     * @param markLast   Function to determine if a token is last
     * @param onFiltered Consumer for filtered tokens
     * @throws GuardrailsException        if evaluation fails
     * @throws GuardrailViolationException if a blocking violation occurs
     */
    public void evaluateStream(
            Stream<String> tokens,
            Function<String, Boolean> markLast,
            Consumer<String> onFiltered) throws GuardrailsException, GuardrailViolationException {
        tokens.forEach(token -> {
            try {
                boolean isLast = markLast != null && markLast.apply(token);
                Optional<String> filtered = evaluate(token, isLast);
                filtered.ifPresent(onFiltered);
            } catch (GuardrailViolationException e) {
                throw new RuntimeException(e);
            } catch (GuardrailsException e) {
                throw new RuntimeException(e);
            }
        });
    }

    /**
     * Evaluate a token asynchronously.
     *
     * @param token  The token text to evaluate
     * @param isLast Whether this is the last token
     * @return CompletableFuture with the filtered token or empty
     */
    public CompletableFuture<Optional<String>> evaluateAsync(String token, boolean isLast) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return evaluate(token, isLast);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        });
    }

    /**
     * Complete the current session.
     *
     * @return Final session state
     * @throws GuardrailsException if completion fails
     */
    public StreamingGuardrailSession completeSession() throws GuardrailsException {
        if (session == null) {
            throw new GuardrailsException("No active session");
        }

        try {
            URL url = new URL(getBaseEndpoint() + "/evaluate/stream/" + session.getSessionId() + "/complete");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Authorization", "Bearer " + config.getApiKey());
            conn.setRequestProperty("Accept", "text/event-stream");
            conn.setConnectTimeout(config.getTimeout() * 1000);
            conn.setReadTimeout(config.getTimeout() * 1000);

            int status = conn.getResponseCode();
            if (status != 200) {
                throw new GuardrailsException("Failed to complete session: HTTP " + status);
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    line = line.trim();
                    if (!line.startsWith("data: ")) {
                        continue;
                    }

                    try {
                        JsonNode data = objectMapper.readTree(line.substring(6));
                        if ("session_complete".equals(getString(data, "type"))) {
                            session.setTokensProcessed(getInt(data, "totalTokens"));
                            session.setAllowed(getBoolean(data, "allowed"));
                        }
                    } catch (Exception e) {
                        // Skip invalid JSON
                    }
                }
            }

            StreamingGuardrailSession completed = session;
            session = null;
            return completed;
        } catch (GuardrailsException e) {
            throw e;
        } catch (Exception e) {
            throw new GuardrailsException("Failed to complete session", e);
        }
    }

    /**
     * Cancel the current session.
     *
     * @return true if cancelled, false if no session
     * @throws GuardrailsException if cancellation fails
     */
    public boolean cancelSession() throws GuardrailsException {
        if (session == null) {
            return false;
        }

        try {
            URL url = new URL(getBaseEndpoint() + "/evaluate/stream/" + session.getSessionId());
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("DELETE");
            conn.setRequestProperty("Authorization", "Bearer " + config.getApiKey());
            conn.setConnectTimeout(config.getTimeout() * 1000);
            conn.setReadTimeout(config.getTimeout() * 1000);

            int status = conn.getResponseCode();
            if (status != 200) {
                throw new GuardrailsException("Failed to cancel session: HTTP " + status);
            }

            JsonNode data = objectMapper.readTree(conn.getInputStream());
            session = null;
            return data.has("cancelled") && data.get("cancelled").asBoolean();
        } catch (GuardrailsException e) {
            throw e;
        } catch (Exception e) {
            throw new GuardrailsException("Failed to cancel session", e);
        }
    }

    /**
     * Get the current session.
     *
     * @return Current session or null
     */
    public StreamingGuardrailSession getSession() {
        return session;
    }

    /**
     * Check if there's an active session.
     *
     * @return true if active session exists
     */
    public boolean isActive() {
        return session != null && !session.isTerminated();
    }

    private GuardrailViolation parseViolation(JsonNode data) {
        String enforcement = getString(data, "enforcementLevel", "enforcement_level");
        EnforcementLevel level = enforcement.isEmpty()
            ? EnforcementLevel.ADVISORY
            : EnforcementLevel.fromValue(enforcement);

        return new GuardrailViolation(
            getString(data, "policyId", "policy_id"),
            getString(data, "policyName", "policy_name"),
            getString(data, "policyType", "policy_type"),
            getString(data, "violationType", "violation_type"),
            getString(data, "message"),
            getString(data, "severity"),
            level,
            getMap(data, "details")
        );
    }

    // Helper methods for JSON parsing
    private String getString(JsonNode node, String... keys) {
        for (String key : keys) {
            if (node.has(key) && !node.get(key).isNull()) {
                return node.get(key).asText();
            }
        }
        return "";
    }

    private int getInt(JsonNode node, String... keys) {
        for (String key : keys) {
            if (node.has(key) && !node.get(key).isNull()) {
                return node.get(key).asInt();
            }
        }
        return 0;
    }

    private boolean getBoolean(JsonNode node, String... keys) {
        for (String key : keys) {
            if (node.has(key) && !node.get(key).isNull()) {
                return node.get(key).asBoolean();
            }
        }
        return false;
    }

    private List<String> getStringList(JsonNode node, String... keys) {
        List<String> result = new ArrayList<>();
        for (String key : keys) {
            if (node.has(key) && node.get(key).isArray()) {
                for (JsonNode item : node.get(key)) {
                    result.add(item.asText());
                }
                return result;
            }
        }
        return result;
    }

    private Map<String, Object> getMap(JsonNode node, String... keys) {
        for (String key : keys) {
            if (node.has(key) && node.get(key).isObject()) {
                Map<String, Object> result = new HashMap<>();
                Iterator<Map.Entry<String, JsonNode>> fields = node.get(key).fields();
                while (fields.hasNext()) {
                    Map.Entry<String, JsonNode> entry = fields.next();
                    result.put(entry.getKey(), nodeToObject(entry.getValue()));
                }
                return result;
            }
        }
        return null;
    }

    private Object nodeToObject(JsonNode node) {
        if (node.isTextual()) return node.asText();
        if (node.isNumber()) return node.numberValue();
        if (node.isBoolean()) return node.asBoolean();
        if (node.isNull()) return null;
        return node.toString();
    }

    @Override
    public void close() {
        session = null;
    }

    /**
     * Configuration builder for StreamingGuardrail.
     */
    public static class StreamingGuardrailConfig {
        private final String apiKey;
        private final String organizationId;
        private final String projectId;
        private String baseUrl = "https://api.diagnyx.io";
        private int timeout = 30;
        private int evaluateEveryNTokens = 10;
        private boolean enableEarlyTermination = true;
        private boolean debug = false;

        private StreamingGuardrailConfig(String apiKey, String organizationId, String projectId) {
            this.apiKey = apiKey;
            this.organizationId = organizationId;
            this.projectId = projectId;
        }

        public static Builder builder() {
            return new Builder();
        }

        public String getApiKey() { return apiKey; }
        public String getOrganizationId() { return organizationId; }
        public String getProjectId() { return projectId; }
        public String getBaseUrl() { return baseUrl; }
        public int getTimeout() { return timeout; }
        public int getEvaluateEveryNTokens() { return evaluateEveryNTokens; }
        public boolean isEnableEarlyTermination() { return enableEarlyTermination; }
        public boolean isDebug() { return debug; }

        public static class Builder {
            private String apiKey;
            private String organizationId;
            private String projectId;
            private String baseUrl = "https://api.diagnyx.io";
            private int timeout = 30;
            private int evaluateEveryNTokens = 10;
            private boolean enableEarlyTermination = true;
            private boolean debug = false;

            public Builder apiKey(String apiKey) {
                this.apiKey = apiKey;
                return this;
            }

            public Builder organizationId(String organizationId) {
                this.organizationId = organizationId;
                return this;
            }

            public Builder projectId(String projectId) {
                this.projectId = projectId;
                return this;
            }

            public Builder baseUrl(String baseUrl) {
                this.baseUrl = baseUrl;
                return this;
            }

            public Builder timeout(int timeout) {
                this.timeout = timeout;
                return this;
            }

            public Builder evaluateEveryNTokens(int n) {
                this.evaluateEveryNTokens = n;
                return this;
            }

            public Builder enableEarlyTermination(boolean enable) {
                this.enableEarlyTermination = enable;
                return this;
            }

            public Builder debug(boolean debug) {
                this.debug = debug;
                return this;
            }

            public StreamingGuardrailConfig build() {
                if (apiKey == null || organizationId == null || projectId == null) {
                    throw new IllegalArgumentException("apiKey, organizationId, and projectId are required");
                }
                StreamingGuardrailConfig config = new StreamingGuardrailConfig(apiKey, organizationId, projectId);
                config.baseUrl = this.baseUrl;
                config.timeout = this.timeout;
                config.evaluateEveryNTokens = this.evaluateEveryNTokens;
                config.enableEarlyTermination = this.enableEarlyTermination;
                config.debug = this.debug;
                return config;
            }
        }
    }

    /**
     * Session state for streaming guardrail.
     */
    public static class StreamingGuardrailSession {
        private final String sessionId;
        private final String organizationId;
        private final String projectId;
        private final List<String> activePolicies;
        private int tokensProcessed;
        private final List<GuardrailViolation> violations;
        private boolean terminated;
        private String terminationReason;
        private boolean allowed;
        private final StringBuilder accumulatedText;

        public StreamingGuardrailSession(String sessionId, String organizationId, String projectId, List<String> activePolicies) {
            this.sessionId = sessionId;
            this.organizationId = organizationId;
            this.projectId = projectId;
            this.activePolicies = activePolicies;
            this.violations = new ArrayList<>();
            this.allowed = true;
            this.accumulatedText = new StringBuilder();
        }

        public String getSessionId() { return sessionId; }
        public String getOrganizationId() { return organizationId; }
        public String getProjectId() { return projectId; }
        public List<String> getActivePolicies() { return activePolicies; }
        public int getTokensProcessed() { return tokensProcessed; }
        public List<GuardrailViolation> getViolations() { return violations; }
        public boolean isTerminated() { return terminated; }
        public String getTerminationReason() { return terminationReason; }
        public boolean isAllowed() { return allowed; }
        public String getAccumulatedText() { return accumulatedText.toString(); }

        void setTokensProcessed(int tokensProcessed) { this.tokensProcessed = tokensProcessed; }
        void addViolation(GuardrailViolation violation) { this.violations.add(violation); }
        void setTerminated(boolean terminated) { this.terminated = terminated; }
        void setTerminationReason(String reason) { this.terminationReason = reason; }
        void setAllowed(boolean allowed) { this.allowed = allowed; }
        void appendToAccumulatedText(String text) { this.accumulatedText.append(text); }
    }
}
