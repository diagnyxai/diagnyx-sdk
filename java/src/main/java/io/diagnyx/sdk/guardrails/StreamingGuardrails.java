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
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;

/**
 * Client for streaming guardrails evaluation.
 *
 * Provides real-time validation of LLM response tokens against configured
 * guardrail policies with support for early termination on blocking violations.
 *
 * Example:
 * <pre>
 * StreamingGuardrailsConfig config = new StreamingGuardrailsConfig(
 *     "dx_...", "org_123", "proj_456"
 * );
 * StreamingGuardrails guardrails = new StreamingGuardrails(config);
 *
 * StreamingEvent.SessionStarted session = guardrails.startSession(null, null);
 *
 * for (ChatCompletionChunk chunk : openaiStream) {
 *     guardrails.evaluateToken(
 *         session.getSessionId(),
 *         chunk.getChoices().get(0).getDelta().getContent(),
 *         tokenIndex,
 *         chunk.getChoices().get(0).getFinishReason() != null,
 *         event -> handleEvent(event)
 *     );
 *     yield chunk;
 * }
 * </pre>
 */
public class StreamingGuardrails implements AutoCloseable {
    private final StreamingGuardrailsConfig config;
    private final ObjectMapper objectMapper;
    private final Map<String, GuardrailSession> sessions;

    public StreamingGuardrails(StreamingGuardrailsConfig config) {
        this.config = config;
        this.objectMapper = new ObjectMapper();
        this.sessions = new ConcurrentHashMap<>();
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
     * Start a new streaming guardrails session.
     *
     * @param sessionId Optional session ID (generated if not provided)
     * @param input Optional input text to pre-evaluate
     * @return SessionStarted event with session details
     * @throws GuardrailsException if session creation fails
     */
    public StreamingEvent.SessionStarted startSession(String sessionId, String input) throws GuardrailsException {
        try {
            ObjectNode payload = objectMapper.createObjectNode();
            payload.put("projectId", config.getProjectId());
            payload.put("evaluateEveryNTokens", config.getEvaluateEveryNTokens());
            payload.put("enableEarlyTermination", config.isEnableEarlyTermination());
            if (sessionId != null) {
                payload.put("sessionId", sessionId);
            }
            if (input != null) {
                payload.put("input", input);
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
            StreamingEvent event = parseEvent(data);

            if (event instanceof StreamingEvent.SessionStarted) {
                StreamingEvent.SessionStarted startedEvent = (StreamingEvent.SessionStarted) event;
                GuardrailSession session = new GuardrailSession(
                    startedEvent.getSessionId(),
                    config.getOrganizationId(),
                    config.getProjectId(),
                    startedEvent.getActivePolicies()
                );
                sessions.put(startedEvent.getSessionId(), session);
                log("Session started: " + startedEvent.getSessionId());
                return startedEvent;
            } else if (event instanceof StreamingEvent.Error) {
                throw new GuardrailsException("Failed to start session: " + ((StreamingEvent.Error) event).getError());
            }

            throw new GuardrailsException("Unexpected response type");
        } catch (GuardrailsException e) {
            throw e;
        } catch (Exception e) {
            throw new GuardrailsException("Failed to start session", e);
        }
    }

    /**
     * Evaluate a token against guardrail policies.
     *
     * @param sessionId The session ID from startSession
     * @param token The token text to evaluate
     * @param tokenIndex Optional token index
     * @param isLast Whether this is the last token
     * @param eventHandler Callback for each event
     * @throws GuardrailsException if evaluation fails
     * @throws GuardrailViolationException if a blocking violation occurs
     */
    public void evaluateToken(
            String sessionId,
            String token,
            Integer tokenIndex,
            boolean isLast,
            Consumer<StreamingEvent> eventHandler) throws GuardrailsException, GuardrailViolationException {

        GuardrailSession session = sessions.get(sessionId);
        if (session == null) {
            StreamingEvent.Error error = new StreamingEvent.Error(
                sessionId, System.currentTimeMillis(), "Session not found", "SESSION_NOT_FOUND"
            );
            eventHandler.accept(error);
            return;
        }

        try {
            ObjectNode payload = objectMapper.createObjectNode();
            payload.put("sessionId", sessionId);
            payload.put("token", token);
            payload.put("isLast", isLast);
            if (tokenIndex != null) {
                payload.put("tokenIndex", tokenIndex);
            }

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
                        StreamingEvent event = parseEvent(data);
                        updateSession(session, event);
                        eventHandler.accept(event);

                        if (event instanceof StreamingEvent.EarlyTermination) {
                            StreamingEvent.EarlyTermination termEvent = (StreamingEvent.EarlyTermination) event;
                            if (termEvent.getBlockingViolation() != null) {
                                throw new GuardrailViolationException(
                                    termEvent.getBlockingViolation().toViolation(),
                                    session
                                );
                            }
                            return;
                        }

                        if (event instanceof StreamingEvent.SessionComplete ||
                            event instanceof StreamingEvent.Error) {
                            return;
                        }
                    } catch (GuardrailViolationException e) {
                        throw e;
                    } catch (Exception e) {
                        log("Failed to parse event: " + e.getMessage());
                    }
                }
            }
        } catch (GuardrailsException | GuardrailViolationException e) {
            throw e;
        } catch (Exception e) {
            throw new GuardrailsException("Token evaluation failed", e);
        }
    }

    /**
     * Complete a streaming session manually.
     *
     * @param sessionId The session ID to complete
     * @param eventHandler Callback for each event
     * @throws GuardrailsException if completion fails
     */
    public void completeSession(String sessionId, Consumer<StreamingEvent> eventHandler) throws GuardrailsException {
        try {
            URL url = new URL(getBaseEndpoint() + "/evaluate/stream/" + sessionId + "/complete");
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
                        eventHandler.accept(parseEvent(data));
                    } catch (Exception e) {
                        // Skip invalid JSON
                    }
                }
            }

            sessions.remove(sessionId);
        } catch (GuardrailsException e) {
            throw e;
        } catch (Exception e) {
            throw new GuardrailsException("Failed to complete session", e);
        }
    }

    /**
     * Cancel a streaming session.
     *
     * @param sessionId The session ID to cancel
     * @return true if cancelled, false otherwise
     * @throws GuardrailsException if cancellation fails
     */
    public boolean cancelSession(String sessionId) throws GuardrailsException {
        try {
            URL url = new URL(getBaseEndpoint() + "/evaluate/stream/" + sessionId);
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
            sessions.remove(sessionId);
            return data.has("cancelled") && data.get("cancelled").asBoolean();
        } catch (GuardrailsException e) {
            throw e;
        } catch (Exception e) {
            throw new GuardrailsException("Failed to cancel session", e);
        }
    }

    /**
     * Get the current state of a session.
     *
     * @param sessionId The session ID
     * @return GuardrailSession or null if not found
     */
    public GuardrailSession getSession(String sessionId) {
        return sessions.get(sessionId);
    }

    private void updateSession(GuardrailSession session, StreamingEvent event) {
        if (event instanceof StreamingEvent.ViolationDetected) {
            StreamingEvent.ViolationDetected vEvent = (StreamingEvent.ViolationDetected) event;
            session.addViolation(vEvent.toViolation());
            if ("blocking".equals(vEvent.getEnforcementLevel())) {
                session.setAllowed(false);
            }
        } else if (event instanceof StreamingEvent.EarlyTermination) {
            StreamingEvent.EarlyTermination tEvent = (StreamingEvent.EarlyTermination) event;
            session.setTerminated(true);
            session.setTerminationReason(tEvent.getReason());
            session.setAllowed(false);
            session.setTokensProcessed(tEvent.getTokensProcessed());
        } else if (event instanceof StreamingEvent.SessionComplete) {
            StreamingEvent.SessionComplete cEvent = (StreamingEvent.SessionComplete) event;
            session.setTokensProcessed(cEvent.getTotalTokens());
            session.setAllowed(cEvent.isAllowed());
        }
    }

    private StreamingEvent parseEvent(JsonNode data) {
        String type = getString(data, "type");
        String sessionId = getString(data, "sessionId", "session_id");
        long timestamp = getLong(data, "timestamp");

        switch (StreamingEventType.fromValue(type)) {
            case SESSION_STARTED:
                return new StreamingEvent.SessionStarted(
                    sessionId, timestamp, getStringList(data, "activePolicies", "active_policies")
                );
            case TOKEN_ALLOWED:
                return new StreamingEvent.TokenAllowed(
                    sessionId, timestamp,
                    getInt(data, "tokenIndex", "token_index"),
                    getInt(data, "accumulatedLength", "accumulated_length")
                );
            case VIOLATION_DETECTED:
                return new StreamingEvent.ViolationDetected(
                    sessionId, timestamp,
                    getString(data, "policyId", "policy_id"),
                    getString(data, "policyName", "policy_name"),
                    getString(data, "policyType", "policy_type"),
                    getString(data, "violationType", "violation_type"),
                    getString(data, "message"),
                    getString(data, "severity"),
                    getString(data, "enforcementLevel", "enforcement_level"),
                    getMap(data, "details")
                );
            case EARLY_TERMINATION:
                StreamingEvent.ViolationDetected blocking = null;
                JsonNode blockingNode = data.has("blockingViolation") ? data.get("blockingViolation") : data.get("blocking_violation");
                if (blockingNode != null && !blockingNode.isNull()) {
                    blocking = new StreamingEvent.ViolationDetected(
                        sessionId, getLong(blockingNode, "timestamp"),
                        getString(blockingNode, "policyId", "policy_id"),
                        getString(blockingNode, "policyName", "policy_name"),
                        getString(blockingNode, "policyType", "policy_type"),
                        getString(blockingNode, "violationType", "violation_type"),
                        getString(blockingNode, "message"),
                        getString(blockingNode, "severity"),
                        getString(blockingNode, "enforcementLevel", "enforcement_level"),
                        getMap(blockingNode, "details")
                    );
                }
                return new StreamingEvent.EarlyTermination(
                    sessionId, timestamp, getString(data, "reason"),
                    blocking, getInt(data, "tokensProcessed", "tokens_processed")
                );
            case SESSION_COMPLETE:
                return new StreamingEvent.SessionComplete(
                    sessionId, timestamp,
                    getInt(data, "totalTokens", "total_tokens"),
                    getInt(data, "totalViolations", "total_violations"),
                    getBoolean(data, "allowed"),
                    getInt(data, "latencyMs", "latency_ms")
                );
            case ERROR:
            default:
                return new StreamingEvent.Error(
                    sessionId, timestamp, getString(data, "error"), getString(data, "code")
                );
        }
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

    private long getLong(JsonNode node, String... keys) {
        for (String key : keys) {
            if (node.has(key) && !node.get(key).isNull()) {
                return node.get(key).asLong();
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
        sessions.clear();
    }
}
