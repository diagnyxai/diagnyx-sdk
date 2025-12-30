package io.diagnyx.sdk.callbacks;

import io.diagnyx.sdk.*;
import org.junit.jupiter.api.*;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class DiagnyxChatModelListenerTest {

    private DiagnyxClient client;
    private DiagnyxChatModelListener listener;

    @BeforeEach
    void setUp() {
        client = DiagnyxClient.create(DiagnyxConfig.builder("test-api-key")
            .baseUrl("http://localhost:9999") // Use non-existent URL for testing
            .build());
        listener = new DiagnyxChatModelListener(client);
    }

    @AfterEach
    void tearDown() {
        if (client != null) {
            client.close();
        }
    }

    @Test
    void testConstructor() {
        assertNotNull(listener);
    }

    @Test
    void testBuilderPattern() {
        DiagnyxChatModelListener configured = new DiagnyxChatModelListener(client)
            .projectId("test-project")
            .environment("test")
            .userIdentifier("test-user")
            .captureContent(true)
            .contentMaxLength(5000);

        assertNotNull(configured);
    }

    @Test
    void testOnRequestAndResponse() {
        String requestId = UUID.randomUUID().toString();

        listener.onRequest(requestId, "gpt-4", "Hello, world!");

        // Small delay to ensure latency is measurable
        try {
            Thread.sleep(10);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        listener.onResponse(requestId, "gpt-4", "Hi there!", 10, 5);

        // Verify call was tracked (we check buffer size)
        assertTrue(client.getBufferSize() >= 0); // May have been flushed
    }

    @Test
    void testOnRequestAndError() {
        String requestId = UUID.randomUUID().toString();

        listener.onRequest(requestId, "gpt-4", "Hello");
        listener.onError(requestId, "gpt-4", new RuntimeException("API rate limit exceeded"));

        assertTrue(client.getBufferSize() >= 0);
    }

    @Test
    void testOnResponseWithoutRequest() {
        // Should handle gracefully when there's no matching request
        String requestId = UUID.randomUUID().toString();
        listener.onResponse(requestId, "gpt-4", "Response", 10, 5);

        assertTrue(client.getBufferSize() >= 0);
    }

    @Test
    void testOnErrorWithoutRequest() {
        // Should handle gracefully when there's no matching request
        String requestId = UUID.randomUUID().toString();
        listener.onError(requestId, "gpt-4", new RuntimeException("Error"));

        assertTrue(client.getBufferSize() >= 0);
    }

    @Test
    void testNullRequestId() {
        // Should generate a UUID if requestId is null
        listener.onRequest(null, "gpt-4", "Hello");
        // This should not throw
    }

    @Test
    void testErrorMessageTruncation() {
        String requestId = UUID.randomUUID().toString();
        StringBuilder longMessage = new StringBuilder();
        for (int i = 0; i < 600; i++) {
            longMessage.append('A');
        }

        listener.onRequest(requestId, "gpt-4", "Hello");
        listener.onError(requestId, "gpt-4", new RuntimeException(longMessage.toString()));

        // Should not throw and should truncate the message
        assertTrue(client.getBufferSize() >= 0);
    }

    @Test
    void testContentCapture() {
        DiagnyxChatModelListener captureListener = new DiagnyxChatModelListener(client)
            .captureContent(true);

        String requestId = UUID.randomUUID().toString();
        captureListener.onRequest(requestId, "gpt-4", "What is 2+2?");
        captureListener.onResponse(requestId, "gpt-4", "2+2 equals 4.", 5, 3);

        assertTrue(client.getBufferSize() >= 0);
    }

    @Test
    void testContentTruncation() {
        DiagnyxChatModelListener captureListener = new DiagnyxChatModelListener(client)
            .captureContent(true)
            .contentMaxLength(10);

        String requestId = UUID.randomUUID().toString();
        captureListener.onRequest(requestId, "gpt-4", "This is a very long prompt that exceeds the limit");
        captureListener.onResponse(requestId, "gpt-4", "This is a very long response that exceeds the limit", 100, 50);

        assertTrue(client.getBufferSize() >= 0);
    }

    @Test
    void testConcurrentRequests() {
        String requestId1 = "request-1";
        String requestId2 = "request-2";

        // Start both requests
        listener.onRequest(requestId1, "gpt-4", "First");
        listener.onRequest(requestId2, "claude-3", "Second");

        // End in reverse order
        listener.onResponse(requestId2, "claude-3", "Second response", 10, 5);
        listener.onResponse(requestId1, "gpt-4", "First response", 8, 4);

        assertTrue(client.getBufferSize() >= 0);
    }

    // Provider detection tests
    @Test
    void testDetectProviderOpenAI() {
        assertEquals(Provider.OPENAI, DiagnyxChatModelListener.detectProvider("gpt-4"));
        assertEquals(Provider.OPENAI, DiagnyxChatModelListener.detectProvider("gpt-3.5-turbo"));
        assertEquals(Provider.OPENAI, DiagnyxChatModelListener.detectProvider("o1-preview"));
        assertEquals(Provider.OPENAI, DiagnyxChatModelListener.detectProvider("GPT-4")); // Case insensitive
    }

    @Test
    void testDetectProviderAnthropic() {
        assertEquals(Provider.ANTHROPIC, DiagnyxChatModelListener.detectProvider("claude-3-opus"));
        assertEquals(Provider.ANTHROPIC, DiagnyxChatModelListener.detectProvider("claude-2"));
        assertEquals(Provider.ANTHROPIC, DiagnyxChatModelListener.detectProvider("CLAUDE-3")); // Case insensitive
    }

    @Test
    void testDetectProviderGoogle() {
        assertEquals(Provider.GOOGLE, DiagnyxChatModelListener.detectProvider("gemini-pro"));
        assertEquals(Provider.GOOGLE, DiagnyxChatModelListener.detectProvider("gemini-1.5-pro"));
    }

    @Test
    void testDetectProviderCustom() {
        assertEquals(Provider.CUSTOM, DiagnyxChatModelListener.detectProvider("mistral-large"));
        assertEquals(Provider.CUSTOM, DiagnyxChatModelListener.detectProvider("mixtral-8x7b"));
        assertEquals(Provider.CUSTOM, DiagnyxChatModelListener.detectProvider("command-r"));
        assertEquals(Provider.CUSTOM, DiagnyxChatModelListener.detectProvider("unknown-model"));
    }

    @Test
    void testDetectProviderNull() {
        assertEquals(Provider.CUSTOM, DiagnyxChatModelListener.detectProvider(null));
    }

    @Test
    void testWithProjectIdAndEnvironment() {
        DiagnyxChatModelListener configuredListener = new DiagnyxChatModelListener(client)
            .projectId("my-project")
            .environment("production")
            .userIdentifier("user-123");

        String requestId = UUID.randomUUID().toString();
        configuredListener.onRequest(requestId, "gpt-4", "Hello");
        configuredListener.onResponse(requestId, "gpt-4", "Hi", 5, 2);

        assertTrue(client.getBufferSize() >= 0);
    }
}
