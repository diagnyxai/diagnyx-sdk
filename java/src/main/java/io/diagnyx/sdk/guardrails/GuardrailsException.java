package io.diagnyx.sdk.guardrails;

/**
 * Exception thrown when guardrails operations fail.
 */
public class GuardrailsException extends Exception {
    public GuardrailsException(String message) {
        super(message);
    }

    public GuardrailsException(String message, Throwable cause) {
        super(message, cause);
    }
}
