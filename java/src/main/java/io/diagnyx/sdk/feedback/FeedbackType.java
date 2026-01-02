package io.diagnyx.sdk.feedback;

import com.fasterxml.jackson.annotation.JsonValue;

/**
 * Types of feedback that can be submitted.
 */
public enum FeedbackType {
    THUMBS_UP("thumbs_up"),
    THUMBS_DOWN("thumbs_down"),
    RATING("rating"),
    TEXT("text"),
    CORRECTION("correction"),
    FLAG("flag");

    private final String value;

    FeedbackType(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    public static FeedbackType fromValue(String value) {
        for (FeedbackType type : values()) {
            if (type.value.equals(value)) {
                return type;
            }
        }
        throw new IllegalArgumentException("Unknown feedback type: " + value);
    }
}
