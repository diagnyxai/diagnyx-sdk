package io.diagnyx.sdk.guardrails;

import java.util.List;
import java.util.Map;

/**
 * Base interface for streaming events.
 */
public abstract class StreamingEvent {
    protected final StreamingEventType type;
    protected final String sessionId;
    protected final long timestamp;

    protected StreamingEvent(StreamingEventType type, String sessionId, long timestamp) {
        this.type = type;
        this.sessionId = sessionId;
        this.timestamp = timestamp;
    }

    public StreamingEventType getType() { return type; }
    public String getSessionId() { return sessionId; }
    public long getTimestamp() { return timestamp; }

    /**
     * Session started event.
     */
    public static class SessionStarted extends StreamingEvent {
        private final List<String> activePolicies;

        public SessionStarted(String sessionId, long timestamp, List<String> activePolicies) {
            super(StreamingEventType.SESSION_STARTED, sessionId, timestamp);
            this.activePolicies = activePolicies;
        }

        public List<String> getActivePolicies() { return activePolicies; }
    }

    /**
     * Token allowed event.
     */
    public static class TokenAllowed extends StreamingEvent {
        private final int tokenIndex;
        private final int accumulatedLength;

        public TokenAllowed(String sessionId, long timestamp, int tokenIndex, int accumulatedLength) {
            super(StreamingEventType.TOKEN_ALLOWED, sessionId, timestamp);
            this.tokenIndex = tokenIndex;
            this.accumulatedLength = accumulatedLength;
        }

        public int getTokenIndex() { return tokenIndex; }
        public int getAccumulatedLength() { return accumulatedLength; }
    }

    /**
     * Violation detected event.
     */
    public static class ViolationDetected extends StreamingEvent {
        private final String policyId;
        private final String policyName;
        private final String policyType;
        private final String violationType;
        private final String message;
        private final String severity;
        private final String enforcementLevel;
        private final Map<String, Object> details;

        public ViolationDetected(
                String sessionId,
                long timestamp,
                String policyId,
                String policyName,
                String policyType,
                String violationType,
                String message,
                String severity,
                String enforcementLevel,
                Map<String, Object> details) {
            super(StreamingEventType.VIOLATION_DETECTED, sessionId, timestamp);
            this.policyId = policyId;
            this.policyName = policyName;
            this.policyType = policyType;
            this.violationType = violationType;
            this.message = message;
            this.severity = severity;
            this.enforcementLevel = enforcementLevel;
            this.details = details;
        }

        public String getPolicyId() { return policyId; }
        public String getPolicyName() { return policyName; }
        public String getPolicyType() { return policyType; }
        public String getViolationType() { return violationType; }
        public String getMessage() { return message; }
        public String getSeverity() { return severity; }
        public String getEnforcementLevel() { return enforcementLevel; }
        public Map<String, Object> getDetails() { return details; }

        public GuardrailViolation toViolation() {
            return new GuardrailViolation(
                policyId, policyName, policyType, violationType,
                message, severity, EnforcementLevel.fromValue(enforcementLevel), details
            );
        }
    }

    /**
     * Early termination event.
     */
    public static class EarlyTermination extends StreamingEvent {
        private final String reason;
        private final ViolationDetected blockingViolation;
        private final int tokensProcessed;

        public EarlyTermination(
                String sessionId,
                long timestamp,
                String reason,
                ViolationDetected blockingViolation,
                int tokensProcessed) {
            super(StreamingEventType.EARLY_TERMINATION, sessionId, timestamp);
            this.reason = reason;
            this.blockingViolation = blockingViolation;
            this.tokensProcessed = tokensProcessed;
        }

        public String getReason() { return reason; }
        public ViolationDetected getBlockingViolation() { return blockingViolation; }
        public int getTokensProcessed() { return tokensProcessed; }
    }

    /**
     * Session complete event.
     */
    public static class SessionComplete extends StreamingEvent {
        private final int totalTokens;
        private final int totalViolations;
        private final boolean allowed;
        private final int latencyMs;

        public SessionComplete(
                String sessionId,
                long timestamp,
                int totalTokens,
                int totalViolations,
                boolean allowed,
                int latencyMs) {
            super(StreamingEventType.SESSION_COMPLETE, sessionId, timestamp);
            this.totalTokens = totalTokens;
            this.totalViolations = totalViolations;
            this.allowed = allowed;
            this.latencyMs = latencyMs;
        }

        public int getTotalTokens() { return totalTokens; }
        public int getTotalViolations() { return totalViolations; }
        public boolean isAllowed() { return allowed; }
        public int getLatencyMs() { return latencyMs; }
    }

    /**
     * Error event.
     */
    public static class Error extends StreamingEvent {
        private final String error;
        private final String code;

        public Error(String sessionId, long timestamp, String error, String code) {
            super(StreamingEventType.ERROR, sessionId, timestamp);
            this.error = error;
            this.code = code;
        }

        public String getError() { return error; }
        public String getCode() { return code; }
    }
}
