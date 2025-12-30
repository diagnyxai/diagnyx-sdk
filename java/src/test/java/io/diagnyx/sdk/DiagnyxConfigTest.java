package io.diagnyx.sdk;

import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for DiagnyxConfig.
 */
class DiagnyxConfigTest {

    @Test
    @DisplayName("Should create config with default values")
    void createConfigWithDefaultValues() {
        DiagnyxConfig config = new DiagnyxConfig("test-api-key");

        assertEquals("test-api-key", config.getApiKey());
        assertEquals("https://api.diagnyx.io", config.getBaseUrl());
        assertEquals(100, config.getBatchSize());
        assertEquals(5000, config.getFlushIntervalMs());
        assertEquals(3, config.getMaxRetries());
        assertFalse(config.isDebug());
        assertFalse(config.isCaptureFullContent());
        assertEquals(10000, config.getContentMaxLength());
    }

    @Test
    @DisplayName("Should throw exception for null API key")
    void throwExceptionForNullApiKey() {
        assertThrows(IllegalArgumentException.class, () -> {
            new DiagnyxConfig(null);
        });
    }

    @Test
    @DisplayName("Should throw exception for empty API key")
    void throwExceptionForEmptyApiKey() {
        assertThrows(IllegalArgumentException.class, () -> {
            new DiagnyxConfig("");
        });
    }

    @Test
    @DisplayName("Should create config with builder")
    void createConfigWithBuilder() {
        DiagnyxConfig config = DiagnyxConfig.builder("my-api-key")
                .baseUrl("https://custom.api.com")
                .batchSize(50)
                .flushIntervalMs(10000)
                .maxRetries(5)
                .debug(true)
                .captureFullContent(true)
                .contentMaxLength(5000)
                .build();

        assertEquals("my-api-key", config.getApiKey());
        assertEquals("https://custom.api.com", config.getBaseUrl());
        assertEquals(50, config.getBatchSize());
        assertEquals(10000, config.getFlushIntervalMs());
        assertEquals(5, config.getMaxRetries());
        assertTrue(config.isDebug());
        assertTrue(config.isCaptureFullContent());
        assertEquals(5000, config.getContentMaxLength());
    }

    @Test
    @DisplayName("Should use default values for unset builder options")
    void useDefaultValuesForUnsetBuilderOptions() {
        DiagnyxConfig config = DiagnyxConfig.builder("test-key")
                .batchSize(200)
                .build();

        assertEquals("test-key", config.getApiKey());
        assertEquals("https://api.diagnyx.io", config.getBaseUrl());
        assertEquals(200, config.getBatchSize());
        assertEquals(5000, config.getFlushIntervalMs());
        assertEquals(3, config.getMaxRetries());
        assertFalse(config.isDebug());
    }

    @Test
    @DisplayName("Builder should chain methods fluently")
    void builderShouldChainMethodsFluently() {
        DiagnyxConfig.Builder builder = DiagnyxConfig.builder("key");

        // Ensure method chaining works (each returns Builder)
        assertDoesNotThrow(() -> {
            builder
                    .baseUrl("https://example.com")
                    .batchSize(10)
                    .flushIntervalMs(1000)
                    .maxRetries(2)
                    .debug(true)
                    .captureFullContent(true)
                    .contentMaxLength(1000)
                    .build();
        });
    }
}
