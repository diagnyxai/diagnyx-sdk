package io.diagnyx.sdk.guardrails;

/**
 * Types of streaming evaluation events.
 */
public enum StreamingEventType {
    SESSION_STARTED("session_started"),
    TOKEN_ALLOWED("token_allowed"),
    VIOLATION_DETECTED("violation_detected"),
    EARLY_TERMINATION("early_termination"),
    SESSION_COMPLETE("session_complete"),
    ERROR("error");

    private final String value;

    StreamingEventType(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public static StreamingEventType fromValue(String value) {
        for (StreamingEventType type : values()) {
            if (type.value.equals(value)) {
                return type;
            }
        }
        return ERROR;
    }
}
