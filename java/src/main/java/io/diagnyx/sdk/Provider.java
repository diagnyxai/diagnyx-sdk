package io.diagnyx.sdk;

import com.fasterxml.jackson.annotation.JsonValue;

/**
 * Supported LLM providers.
 */
public enum Provider {
    OPENAI("openai"),
    ANTHROPIC("anthropic"),
    GOOGLE("google"),
    AZURE("azure"),
    AWS("aws"),
    CUSTOM("custom");

    private final String value;

    Provider(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }
}
