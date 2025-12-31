package io.diagnyx.sdk.guardrails;

import java.util.Map;

/**
 * Represents a guardrail violation.
 */
public class GuardrailViolation {
    private final String policyId;
    private final String policyName;
    private final String policyType;
    private final String violationType;
    private final String message;
    private final String severity;
    private final EnforcementLevel enforcementLevel;
    private final Map<String, Object> details;

    public GuardrailViolation(
            String policyId,
            String policyName,
            String policyType,
            String violationType,
            String message,
            String severity,
            EnforcementLevel enforcementLevel,
            Map<String, Object> details) {
        this.policyId = policyId;
        this.policyName = policyName;
        this.policyType = policyType;
        this.violationType = violationType;
        this.message = message;
        this.severity = severity;
        this.enforcementLevel = enforcementLevel;
        this.details = details;
    }

    public String getPolicyId() { return policyId; }
    public String getPolicyName() { return policyName; }
    public String getPolicyType() { return policyType; }
    public String getViolationType() { return violationType; }
    public String getMessage() { return message; }
    public String getSeverity() { return severity; }
    public EnforcementLevel getEnforcementLevel() { return enforcementLevel; }
    public Map<String, Object> getDetails() { return details; }
}
