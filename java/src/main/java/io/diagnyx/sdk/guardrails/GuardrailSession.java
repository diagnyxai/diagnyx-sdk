package io.diagnyx.sdk.guardrails;

import java.util.ArrayList;
import java.util.List;

/**
 * Represents a streaming guardrails session state.
 */
public class GuardrailSession {
    private final String sessionId;
    private final String organizationId;
    private final String projectId;
    private final List<String> activePolicies;
    private int tokensProcessed;
    private final List<GuardrailViolation> violations;
    private boolean terminated;
    private String terminationReason;
    private boolean allowed;

    public GuardrailSession(String sessionId, String organizationId, String projectId, List<String> activePolicies) {
        this.sessionId = sessionId;
        this.organizationId = organizationId;
        this.projectId = projectId;
        this.activePolicies = activePolicies != null ? new ArrayList<>(activePolicies) : new ArrayList<>();
        this.tokensProcessed = 0;
        this.violations = new ArrayList<>();
        this.terminated = false;
        this.allowed = true;
    }

    public String getSessionId() { return sessionId; }
    public String getOrganizationId() { return organizationId; }
    public String getProjectId() { return projectId; }
    public List<String> getActivePolicies() { return activePolicies; }
    public int getTokensProcessed() { return tokensProcessed; }
    public List<GuardrailViolation> getViolations() { return violations; }
    public boolean isTerminated() { return terminated; }
    public String getTerminationReason() { return terminationReason; }
    public boolean isAllowed() { return allowed; }

    void setTokensProcessed(int tokensProcessed) { this.tokensProcessed = tokensProcessed; }
    void setTerminated(boolean terminated) { this.terminated = terminated; }
    void setTerminationReason(String terminationReason) { this.terminationReason = terminationReason; }
    void setAllowed(boolean allowed) { this.allowed = allowed; }
    void addViolation(GuardrailViolation violation) { this.violations.add(violation); }
}
