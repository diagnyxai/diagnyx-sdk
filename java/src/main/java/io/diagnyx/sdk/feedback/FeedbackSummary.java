package io.diagnyx.sdk.feedback;

import java.util.Map;

/**
 * Contains feedback analytics summary.
 */
public class FeedbackSummary {
    private int totalFeedback;
    private int positiveCount;
    private int negativeCount;
    private int neutralCount;
    private double positiveRate;
    private double averageRating;
    private Map<String, Integer> feedbackByType;
    private Map<String, Integer> feedbackByTag;

    public FeedbackSummary() {}

    public int getTotalFeedback() {
        return totalFeedback;
    }

    public void setTotalFeedback(int totalFeedback) {
        this.totalFeedback = totalFeedback;
    }

    public int getPositiveCount() {
        return positiveCount;
    }

    public void setPositiveCount(int positiveCount) {
        this.positiveCount = positiveCount;
    }

    public int getNegativeCount() {
        return negativeCount;
    }

    public void setNegativeCount(int negativeCount) {
        this.negativeCount = negativeCount;
    }

    public int getNeutralCount() {
        return neutralCount;
    }

    public void setNeutralCount(int neutralCount) {
        this.neutralCount = neutralCount;
    }

    public double getPositiveRate() {
        return positiveRate;
    }

    public void setPositiveRate(double positiveRate) {
        this.positiveRate = positiveRate;
    }

    public double getAverageRating() {
        return averageRating;
    }

    public void setAverageRating(double averageRating) {
        this.averageRating = averageRating;
    }

    public Map<String, Integer> getFeedbackByType() {
        return feedbackByType;
    }

    public void setFeedbackByType(Map<String, Integer> feedbackByType) {
        this.feedbackByType = feedbackByType;
    }

    public Map<String, Integer> getFeedbackByTag() {
        return feedbackByTag;
    }

    public void setFeedbackByTag(Map<String, Integer> feedbackByTag) {
        this.feedbackByTag = feedbackByTag;
    }
}
