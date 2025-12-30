package io.diagnyx.sdk;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.*;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for LLMCall.
 */
class LLMCallTest {

    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());
    }

    @Test
    @DisplayName("Should create call with builder")
    void createCallWithBuilder() {
        LLMCall call = LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .inputTokens(100)
                .outputTokens(50)
                .latencyMs(500)
                .status(CallStatus.SUCCESS)
                .build();

        assertEquals(Provider.OPENAI, call.getProvider());
        assertEquals("gpt-4", call.getModel());
        assertEquals(100, call.getInputTokens());
        assertEquals(50, call.getOutputTokens());
        assertEquals(500, call.getLatencyMs());
        assertEquals(CallStatus.SUCCESS, call.getStatus());
    }

    @Test
    @DisplayName("Should have default timestamp")
    void haveDefaultTimestamp() {
        LLMCall call = LLMCall.builder().build();
        assertNotNull(call.getTimestamp());
    }

    @Test
    @DisplayName("Should have default status of SUCCESS")
    void haveDefaultSuccessStatus() {
        LLMCall call = LLMCall.builder().build();
        assertEquals(CallStatus.SUCCESS, call.getStatus());
    }

    @Test
    @DisplayName("Should serialize to JSON with correct field names")
    void serializeToJsonWithCorrectFieldNames() throws Exception {
        Instant timestamp = Instant.parse("2024-01-15T10:00:00Z");
        LLMCall call = LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .endpoint("/v1/chat/completions")
                .inputTokens(100)
                .outputTokens(50)
                .latencyMs(500)
                .ttftMs(100L)
                .status(CallStatus.SUCCESS)
                .projectId("proj-123")
                .environment("production")
                .userIdentifier("user-456")
                .traceId("trace-789")
                .spanId("span-abc")
                .metadata(Map.of("key", "value"))
                .timestamp(timestamp)
                .fullPrompt("Hello, how are you?")
                .fullResponse("I'm doing well!")
                .build();

        String json = objectMapper.writeValueAsString(call);
        JsonNode node = objectMapper.readTree(json);

        assertEquals("openai", node.get("provider").asText());
        assertEquals("gpt-4", node.get("model").asText());
        assertEquals("/v1/chat/completions", node.get("endpoint").asText());
        assertEquals(100, node.get("input_tokens").asInt());
        assertEquals(50, node.get("output_tokens").asInt());
        assertEquals(500, node.get("latency_ms").asInt());
        assertEquals(100, node.get("ttft_ms").asInt());
        assertEquals("success", node.get("status").asText());
        assertEquals("proj-123", node.get("project_id").asText());
        assertEquals("production", node.get("environment").asText());
        assertEquals("user-456", node.get("user_identifier").asText());
        assertEquals("trace-789", node.get("trace_id").asText());
        assertEquals("span-abc", node.get("span_id").asText());
        assertEquals("value", node.get("metadata").get("key").asText());
        assertEquals("Hello, how are you?", node.get("full_prompt").asText());
        assertEquals("I'm doing well!", node.get("full_response").asText());
    }

    @Test
    @DisplayName("Should omit null fields in JSON")
    void omitNullFieldsInJson() throws Exception {
        LLMCall call = LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .status(CallStatus.SUCCESS)
                .build();

        String json = objectMapper.writeValueAsString(call);
        JsonNode node = objectMapper.readTree(json);

        assertFalse(node.has("endpoint"));
        assertFalse(node.has("project_id"));
        assertFalse(node.has("error_code"));
        assertFalse(node.has("error_message"));
        assertFalse(node.has("ttft_ms"));
        assertFalse(node.has("metadata"));
        assertFalse(node.has("full_prompt"));
        assertFalse(node.has("full_response"));
    }

    @Test
    @DisplayName("Should deserialize from JSON")
    void deserializeFromJson() throws Exception {
        String json = "{" +
                "\"provider\": \"anthropic\"," +
                "\"model\": \"claude-3\"," +
                "\"input_tokens\": 200," +
                "\"output_tokens\": 100," +
                "\"latency_ms\": 750," +
                "\"status\": \"success\"," +
                "\"environment\": \"staging\"" +
                "}";

        LLMCall call = objectMapper.readValue(json, LLMCall.class);

        assertEquals(Provider.ANTHROPIC, call.getProvider());
        assertEquals("claude-3", call.getModel());
        assertEquals(200, call.getInputTokens());
        assertEquals(100, call.getOutputTokens());
        assertEquals(750, call.getLatencyMs());
        assertEquals(CallStatus.SUCCESS, call.getStatus());
        assertEquals("staging", call.getEnvironment());
    }

    @Test
    @DisplayName("Should create call with error details")
    void createCallWithErrorDetails() {
        LLMCall call = LLMCall.builder()
                .provider(Provider.OPENAI)
                .model("gpt-4")
                .status(CallStatus.ERROR)
                .errorCode("rate_limit_exceeded")
                .errorMessage("You exceeded your current quota")
                .build();

        assertEquals(CallStatus.ERROR, call.getStatus());
        assertEquals("rate_limit_exceeded", call.getErrorCode());
        assertEquals("You exceeded your current quota", call.getErrorMessage());
    }

    @Test
    @DisplayName("Should support all providers")
    void supportAllProviders() throws Exception {
        for (Provider provider : Provider.values()) {
            LLMCall call = LLMCall.builder().provider(provider).build();
            String json = objectMapper.writeValueAsString(call);

            assertTrue(json.contains("\"provider\":\"" + provider.getValue() + "\""),
                    "Provider " + provider + " should serialize to " + provider.getValue());
        }
    }

    @Test
    @DisplayName("Should support all call statuses")
    void supportAllCallStatuses() throws Exception {
        for (CallStatus status : CallStatus.values()) {
            LLMCall call = LLMCall.builder().status(status).build();
            String json = objectMapper.writeValueAsString(call);

            assertTrue(json.contains("\"status\":\"" + status.getValue() + "\""),
                    "Status " + status + " should serialize to " + status.getValue());
        }
    }
}
