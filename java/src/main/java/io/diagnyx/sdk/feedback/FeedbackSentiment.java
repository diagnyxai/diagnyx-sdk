package io.diagnyx.sdk.feedback;

import com.fasterxml.jackson.annotation.JsonValue;

/**
 * Sentiment classification of feedback.
 */
public enum FeedbackSentiment {
    POSITIVE("positive"),
    NEGATIVE("negative"),
    NEUTRAL("neutral");

    private final String value;

    FeedbackSentiment(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    public static FeedbackSentiment fromValue(String value) {
        for (FeedbackSentiment sentiment : values()) {
            if (sentiment.value.equals(value)) {
                return sentiment;
            }
        }
        throw new IllegalArgumentException("Unknown sentiment: " + value);
    }
}
