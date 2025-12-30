package io.diagnyx.sdk.callbacks;

import io.diagnyx.sdk.*;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * LangChain4j ChatModelListener for Diagnyx cost tracking.
 *
 * <p>This listener automatically tracks LLM calls made through LangChain4j,
 * capturing token usage, latency, and errors.</p>
 *
 * <p>Example usage:</p>
 * <pre>{@code
 * DiagnyxClient diagnyx = DiagnyxClient.create("dx_live_xxx");
 * DiagnyxChatModelListener listener = new DiagnyxChatModelListener(diagnyx)
 *     .projectId("my-project")
 *     .environment("production");
 *
 * ChatLanguageModel model = OpenAiChatModel.builder()
 *     .apiKey(apiKey)
 *     .listeners(List.of(listener))
 *     .build();
 * }</pre>
 */
public class DiagnyxChatModelListener {

    private final DiagnyxClient client;
    private String projectId;
    private String environment;
    private String userIdentifier;
    private boolean captureContent;
    private int contentMaxLength = 10000;

    private final Map<String, CallContext> callContexts = new ConcurrentHashMap<>();

    /**
     * Context for tracking a single LLM call.
     */
    private static class CallContext {
        final long startTime;
        final String model;
        final String prompt;

        CallContext(long startTime, String model, String prompt) {
            this.startTime = startTime;
            this.model = model;
            this.prompt = prompt;
        }
    }

    /**
     * Creates a new DiagnyxChatModelListener.
     *
     * @param client The Diagnyx client for tracking calls
     */
    public DiagnyxChatModelListener(DiagnyxClient client) {
        this.client = client;
    }

    /**
     * Sets the project ID for categorizing calls.
     *
     * @param projectId The project ID
     * @return this listener for chaining
     */
    public DiagnyxChatModelListener projectId(String projectId) {
        this.projectId = projectId;
        return this;
    }

    /**
     * Sets the environment name.
     *
     * @param environment The environment (e.g., "production", "staging")
     * @return this listener for chaining
     */
    public DiagnyxChatModelListener environment(String environment) {
        this.environment = environment;
        return this;
    }

    /**
     * Sets the user identifier for tracking.
     *
     * @param userIdentifier The user identifier
     * @return this listener for chaining
     */
    public DiagnyxChatModelListener userIdentifier(String userIdentifier) {
        this.userIdentifier = userIdentifier;
        return this;
    }

    /**
     * Enables or disables capturing full prompt/response content.
     *
     * @param capture Whether to capture content
     * @return this listener for chaining
     */
    public DiagnyxChatModelListener captureContent(boolean capture) {
        this.captureContent = capture;
        return this;
    }

    /**
     * Sets the maximum length for captured content before truncation.
     *
     * @param maxLength The maximum content length
     * @return this listener for chaining
     */
    public DiagnyxChatModelListener contentMaxLength(int maxLength) {
        this.contentMaxLength = maxLength;
        return this;
    }

    /**
     * Called when a chat model request starts.
     *
     * @param requestId Unique identifier for the request
     * @param model The model name
     * @param prompt The input prompt/messages
     */
    public void onRequest(String requestId, String model, String prompt) {
        if (requestId == null) {
            requestId = UUID.randomUUID().toString();
        }
        callContexts.put(requestId, new CallContext(System.currentTimeMillis(), model, prompt));
    }

    /**
     * Called when a chat model request completes successfully.
     *
     * @param requestId Unique identifier for the request
     * @param model The model name
     * @param response The response text
     * @param inputTokens Number of input tokens
     * @param outputTokens Number of output tokens
     */
    public void onResponse(String requestId, String model, String response,
                          int inputTokens, int outputTokens) {
        CallContext ctx = callContexts.remove(requestId);
        long latencyMs = ctx != null ? System.currentTimeMillis() - ctx.startTime : 0;
        String actualModel = model != null ? model : (ctx != null ? ctx.model : "unknown");

        LLMCall.Builder callBuilder = LLMCall.builder()
            .provider(detectProvider(actualModel))
            .model(actualModel)
            .inputTokens(inputTokens)
            .outputTokens(outputTokens)
            .status(CallStatus.SUCCESS)
            .latencyMs(latencyMs)
            .timestamp(Instant.now());

        if (projectId != null) {
            callBuilder.projectId(projectId);
        }
        if (environment != null) {
            callBuilder.environment(environment);
        }
        if (userIdentifier != null) {
            callBuilder.userIdentifier(userIdentifier);
        }

        if (captureContent) {
            if (ctx != null && ctx.prompt != null) {
                String prompt = ctx.prompt;
                if (prompt.length() > contentMaxLength) {
                    prompt = prompt.substring(0, contentMaxLength) + "... [truncated]";
                }
                callBuilder.fullPrompt(prompt);
            }
            if (response != null) {
                String resp = response;
                if (resp.length() > contentMaxLength) {
                    resp = resp.substring(0, contentMaxLength) + "... [truncated]";
                }
                callBuilder.fullResponse(resp);
            }
        }

        client.track(callBuilder.build());
    }

    /**
     * Called when a chat model request fails.
     *
     * @param requestId Unique identifier for the request
     * @param model The model name
     * @param error The error that occurred
     */
    public void onError(String requestId, String model, Throwable error) {
        CallContext ctx = callContexts.remove(requestId);
        long latencyMs = ctx != null ? System.currentTimeMillis() - ctx.startTime : 0;
        String actualModel = model != null ? model : (ctx != null ? ctx.model : "unknown");

        String errorMessage = error.getMessage();
        if (errorMessage != null && errorMessage.length() > 500) {
            errorMessage = errorMessage.substring(0, 500);
        }

        LLMCall.Builder callBuilder = LLMCall.builder()
            .provider(detectProvider(actualModel))
            .model(actualModel)
            .inputTokens(0)
            .outputTokens(0)
            .status(CallStatus.ERROR)
            .latencyMs(latencyMs)
            .errorMessage(errorMessage)
            .timestamp(Instant.now());

        if (projectId != null) {
            callBuilder.projectId(projectId);
        }
        if (environment != null) {
            callBuilder.environment(environment);
        }
        if (userIdentifier != null) {
            callBuilder.userIdentifier(userIdentifier);
        }

        client.track(callBuilder.build());
    }

    /**
     * Detects the LLM provider from the model name.
     *
     * @param model The model name
     * @return The detected provider
     */
    static Provider detectProvider(String model) {
        if (model == null) {
            return Provider.CUSTOM;
        }

        String modelLower = model.toLowerCase();

        if (modelLower.startsWith("gpt-") || modelLower.startsWith("o1-")) {
            return Provider.OPENAI;
        }
        if (modelLower.startsWith("claude-")) {
            return Provider.ANTHROPIC;
        }
        if (modelLower.startsWith("gemini-")) {
            return Provider.GOOGLE;
        }
        if (modelLower.startsWith("mistral") || modelLower.startsWith("mixtral")) {
            return Provider.CUSTOM;
        }
        if (modelLower.startsWith("command")) {
            return Provider.CUSTOM; // Cohere
        }

        return Provider.CUSTOM;
    }
}
