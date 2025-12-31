package io.diagnyx.sdk.guardrails;

/**
 * Policy enforcement levels.
 */
public enum EnforcementLevel {
    ADVISORY("advisory"),
    WARNING("warning"),
    BLOCKING("blocking");

    private final String value;

    EnforcementLevel(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public static EnforcementLevel fromValue(String value) {
        for (EnforcementLevel level : values()) {
            if (level.value.equals(value)) {
                return level;
            }
        }
        return ADVISORY;
    }
}
