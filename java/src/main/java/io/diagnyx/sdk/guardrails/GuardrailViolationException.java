package io.diagnyx.sdk.guardrails;

/**
 * Exception thrown when a blocking guardrail violation occurs.
 */
public class GuardrailViolationException extends Exception {
    private final GuardrailViolation violation;
    private final GuardrailSession session;

    public GuardrailViolationException(GuardrailViolation violation, GuardrailSession session) {
        super("Guardrail violation: " + violation.getMessage());
        this.violation = violation;
        this.session = session;
    }

    public GuardrailViolation getViolation() {
        return violation;
    }

    public GuardrailSession getSession() {
        return session;
    }
}
