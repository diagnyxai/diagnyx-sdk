package io.diagnyx.sdk.feedback;

import java.time.Instant;

/**
 * Options for listing feedback.
 */
public class ListFeedbackOptions {
    private int limit;
    private int offset;
    private FeedbackType feedbackType;
    private FeedbackSentiment sentiment;
    private String tag;
    private Instant startDate;
    private Instant endDate;

    private ListFeedbackOptions(Builder builder) {
        this.limit = builder.limit;
        this.offset = builder.offset;
        this.feedbackType = builder.feedbackType;
        this.sentiment = builder.sentiment;
        this.tag = builder.tag;
        this.startDate = builder.startDate;
        this.endDate = builder.endDate;
    }

    public static Builder builder() {
        return new Builder();
    }

    public int getLimit() {
        return limit;
    }

    public int getOffset() {
        return offset;
    }

    public FeedbackType getFeedbackType() {
        return feedbackType;
    }

    public FeedbackSentiment getSentiment() {
        return sentiment;
    }

    public String getTag() {
        return tag;
    }

    public Instant getStartDate() {
        return startDate;
    }

    public Instant getEndDate() {
        return endDate;
    }

    public static class Builder {
        private int limit = 50;
        private int offset = 0;
        private FeedbackType feedbackType;
        private FeedbackSentiment sentiment;
        private String tag;
        private Instant startDate;
        private Instant endDate;

        public Builder limit(int limit) {
            this.limit = limit;
            return this;
        }

        public Builder offset(int offset) {
            this.offset = offset;
            return this;
        }

        public Builder feedbackType(FeedbackType feedbackType) {
            this.feedbackType = feedbackType;
            return this;
        }

        public Builder sentiment(FeedbackSentiment sentiment) {
            this.sentiment = sentiment;
            return this;
        }

        public Builder tag(String tag) {
            this.tag = tag;
            return this;
        }

        public Builder startDate(Instant startDate) {
            this.startDate = startDate;
            return this;
        }

        public Builder endDate(Instant endDate) {
            this.endDate = endDate;
            return this;
        }

        public ListFeedbackOptions build() {
            return new ListFeedbackOptions(this);
        }
    }
}
