package io.diagnyx.sdk.feedback;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.*;

/**
 * Client for submitting and managing user feedback.
 *
 * <p>Feedback is linked to traces and can be used for:</p>
 * <ul>
 *   <li>Monitoring user satisfaction</li>
 *   <li>Identifying problematic responses</li>
 *   <li>Collecting data for fine-tuning</li>
 *   <li>Quality assurance</li>
 * </ul>
 *
 * <pre>{@code
 * FeedbackClient feedback = new FeedbackClient("dx_api_key", "org-123");
 *
 * // Submit thumbs up
 * feedback.thumbsUp("trace_123");
 *
 * // Submit rating
 * feedback.rating("trace_123", 4);
 *
 * // Submit with options
 * FeedbackOptions options = FeedbackOptions.builder()
 *     .tags(Arrays.asList("accurate", "helpful"))
 *     .userId("user_123")
 *     .build();
 * feedback.text("trace_123", "Great response!", options);
 * }</pre>
 */
public class FeedbackClient {
    private final String apiKey;
    private final String baseUrl;
    private final String organizationId;
    private final int maxRetries;
    private final boolean debug;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    /**
     * Creates a new FeedbackClient with default settings.
     */
    public FeedbackClient(String apiKey, String organizationId) {
        this(apiKey, organizationId, "https://api.diagnyx.io", 3, false);
    }

    /**
     * Creates a new FeedbackClient with custom settings.
     */
    public FeedbackClient(String apiKey, String organizationId, String baseUrl, int maxRetries, boolean debug) {
        this.apiKey = apiKey;
        this.organizationId = organizationId;
        this.baseUrl = baseUrl;
        this.maxRetries = maxRetries;
        this.debug = debug;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(30))
                .build();
        this.objectMapper = new ObjectMapper();
        this.objectMapper.registerModule(new JavaTimeModule());
    }

    /**
     * Submit positive thumbs up feedback.
     */
    public Feedback thumbsUp(String traceId) throws Exception {
        return thumbsUp(traceId, null);
    }

    /**
     * Submit positive thumbs up feedback with options.
     */
    public Feedback thumbsUp(String traceId, FeedbackOptions options) throws Exception {
        return submit(traceId, FeedbackType.THUMBS_UP, null, null, null, options);
    }

    /**
     * Submit negative thumbs down feedback.
     */
    public Feedback thumbsDown(String traceId) throws Exception {
        return thumbsDown(traceId, null);
    }

    /**
     * Submit negative thumbs down feedback with options.
     */
    public Feedback thumbsDown(String traceId, FeedbackOptions options) throws Exception {
        return submit(traceId, FeedbackType.THUMBS_DOWN, null, null, null, options);
    }

    /**
     * Submit a numeric rating (1-5).
     */
    public Feedback rating(String traceId, int value) throws Exception {
        return rating(traceId, value, null);
    }

    /**
     * Submit a numeric rating (1-5) with options.
     */
    public Feedback rating(String traceId, int value, FeedbackOptions options) throws Exception {
        if (value < 1 || value > 5) {
            throw new IllegalArgumentException("Rating value must be between 1 and 5");
        }
        return submit(traceId, FeedbackType.RATING, value, null, null, options);
    }

    /**
     * Submit text feedback.
     */
    public Feedback text(String traceId, String comment) throws Exception {
        return text(traceId, comment, null);
    }

    /**
     * Submit text feedback with options.
     */
    public Feedback text(String traceId, String comment, FeedbackOptions options) throws Exception {
        return submit(traceId, FeedbackType.TEXT, null, comment, null, options);
    }

    /**
     * Submit a correction for fine-tuning.
     */
    public Feedback correction(String traceId, String correction) throws Exception {
        return correction(traceId, correction, null);
    }

    /**
     * Submit a correction for fine-tuning with options.
     */
    public Feedback correction(String traceId, String correction, FeedbackOptions options) throws Exception {
        return submit(traceId, FeedbackType.CORRECTION, null, null, correction, options);
    }

    /**
     * Flag a response for review.
     */
    public Feedback flag(String traceId, String reason) throws Exception {
        return flag(traceId, reason, null);
    }

    /**
     * Flag a response for review with options.
     */
    public Feedback flag(String traceId, String reason, FeedbackOptions options) throws Exception {
        return submit(traceId, FeedbackType.FLAG, null, reason, null, options);
    }

    private Feedback submit(String traceId, FeedbackType type, Integer rating,
                            String comment, String correction, FeedbackOptions options) throws Exception {
        if (options == null) {
            options = FeedbackOptions.builder().build();
        }

        Map<String, Object> payload = new HashMap<>();
        payload.put("traceId", traceId);
        payload.put("feedbackType", type.getValue());

        if (options.getSpanId() != null) {
            payload.put("spanId", options.getSpanId());
        }
        if (rating != null) {
            payload.put("rating", rating);
        }
        if (comment != null) {
            payload.put("comment", comment);
        } else if (options.getComment() != null) {
            payload.put("comment", options.getComment());
        }
        if (correction != null) {
            payload.put("correction", correction);
        }
        if (options.getTags() != null && !options.getTags().isEmpty()) {
            payload.put("tags", options.getTags());
        }
        if (options.getMetadata() != null) {
            payload.put("metadata", options.getMetadata());
        }
        if (options.getUserId() != null) {
            payload.put("userId", options.getUserId());
        }
        if (options.getSessionId() != null) {
            payload.put("sessionId", options.getSessionId());
        }

        String body = objectMapper.writeValueAsString(payload);
        String responseBody = request("POST", "/api/v1/feedback", body);

        return objectMapper.readValue(responseBody, Feedback.class);
    }

    /**
     * List feedback with filters.
     */
    public FeedbackListResult list(ListFeedbackOptions options) throws Exception {
        if (options == null) {
            options = ListFeedbackOptions.builder().build();
        }

        StringBuilder path = new StringBuilder("/api/v1/organizations/")
                .append(organizationId)
                .append("/feedback");

        List<String> params = new ArrayList<>();
        if (options.getLimit() > 0) {
            params.add("limit=" + options.getLimit());
        }
        if (options.getOffset() > 0) {
            params.add("offset=" + options.getOffset());
        }
        if (options.getFeedbackType() != null) {
            params.add("feedbackType=" + options.getFeedbackType().getValue());
        }
        if (options.getSentiment() != null) {
            params.add("sentiment=" + options.getSentiment().getValue());
        }
        if (options.getTag() != null) {
            params.add("tag=" + options.getTag());
        }
        if (options.getStartDate() != null) {
            params.add("startDate=" + options.getStartDate().toString());
        }
        if (options.getEndDate() != null) {
            params.add("endDate=" + options.getEndDate().toString());
        }

        if (!params.isEmpty()) {
            path.append("?").append(String.join("&", params));
        }

        String responseBody = request("GET", path.toString(), null);
        return objectMapper.readValue(responseBody, FeedbackListResult.class);
    }

    /**
     * Get feedback summary/analytics.
     */
    public FeedbackSummary getSummary(Instant startDate, Instant endDate) throws Exception {
        StringBuilder path = new StringBuilder("/api/v1/organizations/")
                .append(organizationId)
                .append("/feedback/analytics");

        List<String> params = new ArrayList<>();
        if (startDate != null) {
            params.add("startDate=" + startDate.toString());
        }
        if (endDate != null) {
            params.add("endDate=" + endDate.toString());
        }

        if (!params.isEmpty()) {
            path.append("?").append(String.join("&", params));
        }

        String responseBody = request("GET", path.toString(), null);
        return objectMapper.readValue(responseBody, FeedbackSummary.class);
    }

    /**
     * Get feedback for a specific trace.
     */
    public List<Feedback> getForTrace(String traceId) throws Exception {
        String path = String.format("/api/v1/organizations/%s/feedback/trace/%s",
                organizationId, traceId);

        String responseBody = request("GET", path, null);
        return objectMapper.readValue(responseBody, new TypeReference<List<Feedback>>() {});
    }

    private String request(String method, String path, String body) throws Exception {
        Exception lastError = null;

        for (int attempt = 0; attempt < maxRetries; attempt++) {
            try {
                HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + path))
                        .header("Content-Type", "application/json")
                        .header("Authorization", "Bearer " + apiKey);

                if ("POST".equals(method)) {
                    requestBuilder.POST(HttpRequest.BodyPublishers.ofString(body));
                } else {
                    requestBuilder.GET();
                }

                HttpResponse<String> response = httpClient.send(
                        requestBuilder.build(),
                        HttpResponse.BodyHandlers.ofString()
                );

                if (response.statusCode() >= 200 && response.statusCode() < 300) {
                    return response.body();
                }

                lastError = new RuntimeException("HTTP " + response.statusCode() + ": " + response.body());
                log("Attempt %d failed: %s", attempt + 1, lastError.getMessage());

                if (response.statusCode() >= 400 && response.statusCode() < 500) {
                    throw lastError;
                }

                Thread.sleep((long) Math.pow(2, attempt) * 1000);

            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw e;
            } catch (Exception e) {
                lastError = e;
                log("Attempt %d failed: %s", attempt + 1, e.getMessage());
                if (attempt < maxRetries - 1) {
                    Thread.sleep((long) Math.pow(2, attempt) * 1000);
                }
            }
        }

        throw lastError != null ? lastError : new RuntimeException("Failed to send request");
    }

    private void log(String format, Object... args) {
        if (debug) {
            System.out.printf("[Diagnyx Feedback] " + format + "%n", args);
        }
    }

    /**
     * Result of listing feedback.
     */
    public static class FeedbackListResult {
        private List<Feedback> data;
        private int total;
        private int limit;
        private int offset;

        public List<Feedback> getData() {
            return data;
        }

        public void setData(List<Feedback> data) {
            this.data = data;
        }

        public int getTotal() {
            return total;
        }

        public void setTotal(int total) {
            this.total = total;
        }

        public int getLimit() {
            return limit;
        }

        public void setLimit(int limit) {
            this.limit = limit;
        }

        public int getOffset() {
            return offset;
        }

        public void setOffset(int offset) {
            this.offset = offset;
        }
    }
}
