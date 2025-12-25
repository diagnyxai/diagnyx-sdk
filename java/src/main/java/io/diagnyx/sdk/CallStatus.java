package io.diagnyx.sdk;

import com.fasterxml.jackson.annotation.JsonValue;

/**
 * Status of an LLM call.
 */
public enum CallStatus {
    SUCCESS("success"),
    ERROR("error"),
    TIMEOUT("timeout"),
    RATE_LIMITED("rate_limited");

    private final String value;

    CallStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }
}
