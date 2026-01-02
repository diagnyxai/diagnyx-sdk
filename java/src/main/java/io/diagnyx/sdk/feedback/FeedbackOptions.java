package io.diagnyx.sdk.feedback;

import java.util.List;
import java.util.Map;

/**
 * Options for feedback submission.
 */
public class FeedbackOptions {
    private String spanId;
    private String comment;
    private List<String> tags;
    private Map<String, Object> metadata;
    private String userId;
    private String sessionId;

    private FeedbackOptions(Builder builder) {
        this.spanId = builder.spanId;
        this.comment = builder.comment;
        this.tags = builder.tags;
        this.metadata = builder.metadata;
        this.userId = builder.userId;
        this.sessionId = builder.sessionId;
    }

    public static Builder builder() {
        return new Builder();
    }

    public String getSpanId() {
        return spanId;
    }

    public String getComment() {
        return comment;
    }

    public List<String> getTags() {
        return tags;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public String getUserId() {
        return userId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public static class Builder {
        private String spanId;
        private String comment;
        private List<String> tags;
        private Map<String, Object> metadata;
        private String userId;
        private String sessionId;

        public Builder spanId(String spanId) {
            this.spanId = spanId;
            return this;
        }

        public Builder comment(String comment) {
            this.comment = comment;
            return this;
        }

        public Builder tags(List<String> tags) {
            this.tags = tags;
            return this;
        }

        public Builder metadata(Map<String, Object> metadata) {
            this.metadata = metadata;
            return this;
        }

        public Builder userId(String userId) {
            this.userId = userId;
            return this;
        }

        public Builder sessionId(String sessionId) {
            this.sessionId = sessionId;
            return this;
        }

        public FeedbackOptions build() {
            return new FeedbackOptions(this);
        }
    }
}
