package io.diagnyx.sdk;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.*;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for DiagnyxClient.
 */
class DiagnyxClientTest {

    private MockWebServer mockServer;
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() throws IOException {
        mockServer = new MockWebServer();
        mockServer.start();
        objectMapper = new ObjectMapper();
    }

    @AfterEach
    void tearDown() throws IOException {
        mockServer.shutdown();
    }

    @Test
    @DisplayName("Should create client with API key")
    void createClientWithApiKey() {
        DiagnyxClient client = DiagnyxClient.create("test-api-key");
        assertNotNull(client);
        client.close();
    }

    @Test
    @DisplayName("Should throw exception for null API key")
    void throwExceptionForNullApiKey() {
        assertThrows(IllegalArgumentException.class, () -> {
            DiagnyxClient.create((String) null);
        });
    }

    @Test
    @DisplayName("Should throw exception for empty API key")
    void throwExceptionForEmptyApiKey() {
        assertThrows(IllegalArgumentException.class, () -> {
            DiagnyxClient.create("");
        });
    }

    @Test
    @DisplayName("Should add call to buffer")
    void addCallToBuffer() {
        // Enqueue response for the flush that happens on close()
        mockServer.enqueue(new MockResponse()
                .setBody("{\"tracked\": 1}")
                .setResponseCode(200));

        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        LLMCall call = LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .inputTokens(100)
                .outputTokens(50)
                .status(CallStatus.SUCCESS)
                .build();

        client.track(call);

        assertEquals(1, client.getBufferSize());
        client.close();
    }

    @Test
    @DisplayName("Should add multiple calls with trackAll")
    void addMultipleCallsWithTrackAll() {
        // Enqueue response for the flush that happens on close()
        mockServer.enqueue(new MockResponse()
                .setBody("{\"tracked\": 3}")
                .setResponseCode(200));

        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        List<LLMCall> calls = List.of(
                LLMCall.builder().provider(Provider.OPENAI).model("gpt-4").build(),
                LLMCall.builder().provider(Provider.ANTHROPIC).model("claude-3").build(),
                LLMCall.builder().provider(Provider.GOOGLE).model("gemini").build()
        );

        client.trackAll(calls);

        assertEquals(3, client.getBufferSize());
        client.close();
    }

    @Test
    @DisplayName("Should flush buffer to API")
    void flushBufferToApi() throws Exception {
        mockServer.enqueue(new MockResponse()
                .setBody("{\"tracked\": 1, \"total_cost\": 0.001, \"ids\": [\"id-1\"]}")
                .setResponseCode(200));

        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        client.track(LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .inputTokens(100)
                .outputTokens(50)
                .build());

        client.flush();

        assertEquals(0, client.getBufferSize());

        RecordedRequest request = mockServer.takeRequest(5, TimeUnit.SECONDS);
        assertNotNull(request);
        assertTrue(request.getPath().endsWith("/api/v1/ingest/llm/batch"));
        assertEquals("POST", request.getMethod());
        assertTrue(request.getHeader("Authorization").startsWith("Bearer "));

        client.close();
    }

    @Test
    @DisplayName("Should auto-flush when batch size reached")
    void autoFlushWhenBatchSizeReached() throws Exception {
        mockServer.enqueue(new MockResponse()
                .setBody("{\"tracked\": 5}")
                .setResponseCode(200));

        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .batchSize(5)
                .flushIntervalMs(60000)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        for (int i = 0; i < 5; i++) {
            client.track(LLMCall.builder()
                    .provider(Provider.OPENAI)
                    .model("gpt-4")
                    .build());
        }

        // Wait for async flush
        Thread.sleep(100);

        assertEquals(0, client.getBufferSize());
        assertEquals(1, mockServer.getRequestCount());
        client.close();
    }

    @Test
    @DisplayName("Should restore buffer on flush error")
    void restoreBufferOnFlushError() throws Exception {
        // First flush attempt fails
        mockServer.enqueue(new MockResponse()
                .setResponseCode(500)
                .setBody("{\"error\": \"Server error\"}"));
        // Second flush on close() succeeds
        mockServer.enqueue(new MockResponse()
                .setBody("{\"tracked\": 1}")
                .setResponseCode(200));

        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .maxRetries(1)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        client.track(LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .build());

        client.flush();

        assertEquals(1, client.getBufferSize());
        client.close();
    }

    @Test
    @DisplayName("Should retry on server error")
    void retryOnServerError() throws Exception {
        mockServer.enqueue(new MockResponse().setResponseCode(500));
        mockServer.enqueue(new MockResponse()
                .setBody("{\"tracked\": 1}")
                .setResponseCode(200));

        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .maxRetries(3)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        client.track(LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .build());

        client.flush();

        assertEquals(0, client.getBufferSize());
        assertEquals(2, mockServer.getRequestCount());
        client.close();
    }

    @Test
    @DisplayName("Should not retry on client error (4xx)")
    void noRetryOnClientError() throws Exception {
        // First flush fails with 4xx
        mockServer.enqueue(new MockResponse()
                .setResponseCode(400)
                .setBody("{\"error\": \"Bad request\"}"));
        // Second flush on close() succeeds
        mockServer.enqueue(new MockResponse()
                .setBody("{\"tracked\": 1}")
                .setResponseCode(200));

        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .maxRetries(1)  // Only 1 attempt, so no retries
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        client.track(LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .build());

        client.flush();

        // With maxRetries=1, should make exactly 1 request
        int requestsAfterFlush = mockServer.getRequestCount();
        assertEquals(1, requestsAfterFlush);
        // Buffer should be restored due to error
        assertEquals(1, client.getBufferSize());

        // close() will flush again successfully
        client.close();
        assertEquals(2, mockServer.getRequestCount());
    }

    @Test
    @DisplayName("Should flush on close")
    void flushOnClose() throws Exception {
        mockServer.enqueue(new MockResponse()
                .setBody("{\"tracked\": 1}")
                .setResponseCode(200));

        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        client.track(LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .build());

        client.close();

        assertEquals(1, mockServer.getRequestCount());
    }

    @Test
    @DisplayName("Should throw exception when tracking after close")
    void throwExceptionWhenTrackingAfterClose() {
        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);
        client.close();

        assertThrows(IllegalStateException.class, () -> {
            client.track(LLMCall.builder()
                    .provider(Provider.OPENAI)
                    .model("gpt-4")
                    .build());
        });
    }

    @Test
    @DisplayName("Should serialize call data correctly in request")
    void serializeCallDataCorrectly() throws Exception {
        mockServer.enqueue(new MockResponse()
                .setBody("{\"tracked\": 1}")
                .setResponseCode(200));

        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        client.track(LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .inputTokens(100)
                .outputTokens(50)
                .latencyMs(500)
                .status(CallStatus.SUCCESS)
                .environment("production")
                .metadata(Map.of("key", "value"))
                .build());

        client.flush();

        RecordedRequest request = mockServer.takeRequest(5, TimeUnit.SECONDS);
        String body = request.getBody().readUtf8();
        JsonNode json = objectMapper.readTree(body);

        assertTrue(json.has("calls"));
        JsonNode calls = json.get("calls");
        assertEquals(1, calls.size());

        JsonNode call = calls.get(0);
        assertEquals("openai", call.get("provider").asText());
        assertEquals("gpt-4", call.get("model").asText());
        assertEquals(100, call.get("input_tokens").asInt());
        assertEquals(50, call.get("output_tokens").asInt());
        assertEquals("success", call.get("status").asText());
        assertEquals("production", call.get("environment").asText());

        client.close();
    }

    @Test
    @DisplayName("Should handle empty flush gracefully")
    void handleEmptyFlushGracefully() {
        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .baseUrl(mockServer.url("/").toString())
                .flushIntervalMs(60000)
                .build();
        DiagnyxClient client = DiagnyxClient.create(config);

        // Flush with empty buffer should not throw
        assertDoesNotThrow(() -> client.flush());
        assertEquals(0, mockServer.getRequestCount());

        client.close();
    }
}
