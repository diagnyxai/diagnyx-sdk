// Package guardrails provides streaming guardrails for LLM responses
package guardrails

// EventType represents the type of streaming evaluation event
type EventType string

const (
	EventSessionStarted   EventType = "session_started"
	EventTokenAllowed     EventType = "token_allowed"
	EventViolationDetected EventType = "violation_detected"
	EventEarlyTermination EventType = "early_termination"
	EventSessionComplete  EventType = "session_complete"
	EventError            EventType = "error"
)

// EnforcementLevel represents the policy enforcement level
type EnforcementLevel string

const (
	EnforcementAdvisory EnforcementLevel = "advisory"
	EnforcementWarning  EnforcementLevel = "warning"
	EnforcementBlocking EnforcementLevel = "blocking"
)

// Event is the base streaming event interface
type Event interface {
	GetType() EventType
	GetSessionID() string
	GetTimestamp() int64
}

// BaseEvent contains common event fields
type BaseEvent struct {
	Type      EventType `json:"type"`
	SessionID string    `json:"sessionId"`
	Timestamp int64     `json:"timestamp"`
}

func (e BaseEvent) GetType() EventType    { return e.Type }
func (e BaseEvent) GetSessionID() string  { return e.SessionID }
func (e BaseEvent) GetTimestamp() int64   { return e.Timestamp }

// SessionStartedEvent is emitted when a streaming session starts
type SessionStartedEvent struct {
	BaseEvent
	ActivePolicies []string `json:"activePolicies"`
}

// TokenAllowedEvent is emitted when a token passes guardrail checks
type TokenAllowedEvent struct {
	BaseEvent
	TokenIndex        int `json:"tokenIndex"`
	AccumulatedLength int `json:"accumulatedLength"`
}

// Violation represents a guardrail violation
type Violation struct {
	PolicyID         string                 `json:"policyId"`
	PolicyName       string                 `json:"policyName"`
	PolicyType       string                 `json:"policyType"`
	ViolationType    string                 `json:"violationType"`
	Message          string                 `json:"message"`
	Severity         string                 `json:"severity"`
	EnforcementLevel EnforcementLevel       `json:"enforcementLevel"`
	Details          map[string]interface{} `json:"details,omitempty"`
}

// ViolationDetectedEvent is emitted when a guardrail violation is detected
type ViolationDetectedEvent struct {
	BaseEvent
	PolicyID         string                 `json:"policyId"`
	PolicyName       string                 `json:"policyName"`
	PolicyType       string                 `json:"policyType"`
	ViolationType    string                 `json:"violationType"`
	Message          string                 `json:"message"`
	Severity         string                 `json:"severity"`
	EnforcementLevel string                 `json:"enforcementLevel"`
	Details          map[string]interface{} `json:"details,omitempty"`
}

// ToViolation converts the event to a Violation struct
func (e ViolationDetectedEvent) ToViolation() Violation {
	level := EnforcementAdvisory
	if e.EnforcementLevel != "" {
		level = EnforcementLevel(e.EnforcementLevel)
	}
	return Violation{
		PolicyID:         e.PolicyID,
		PolicyName:       e.PolicyName,
		PolicyType:       e.PolicyType,
		ViolationType:    e.ViolationType,
		Message:          e.Message,
		Severity:         e.Severity,
		EnforcementLevel: level,
		Details:          e.Details,
	}
}

// EarlyTerminationEvent is emitted when stream is terminated early
type EarlyTerminationEvent struct {
	BaseEvent
	Reason            string                  `json:"reason"`
	BlockingViolation *ViolationDetectedEvent `json:"blockingViolation,omitempty"`
	TokensProcessed   int                     `json:"tokensProcessed"`
}

// SessionCompleteEvent is emitted when a streaming session completes
type SessionCompleteEvent struct {
	BaseEvent
	TotalTokens     int  `json:"totalTokens"`
	TotalViolations int  `json:"totalViolations"`
	Allowed         bool `json:"allowed"`
	LatencyMs       int  `json:"latencyMs"`
}

// ErrorEvent is emitted when an error occurs
type ErrorEvent struct {
	BaseEvent
	Error string `json:"error"`
	Code  string `json:"code,omitempty"`
}

// Session represents a streaming guardrails session state
type Session struct {
	SessionID         string
	OrganizationID    string
	ProjectID         string
	ActivePolicies    []string
	TokensProcessed   int
	Violations        []Violation
	Terminated        bool
	TerminationReason string
	Allowed           bool
}

// Config holds configuration for the StreamingGuardrails client
type Config struct {
	APIKey                 string
	OrganizationID         string
	ProjectID              string
	BaseURL                string
	Timeout                int // in seconds
	EvaluateEveryNTokens   int
	EnableEarlyTermination bool
	Debug                  bool
}

// DefaultConfig returns a Config with default values
func DefaultConfig(apiKey, organizationID, projectID string) Config {
	return Config{
		APIKey:                 apiKey,
		OrganizationID:         organizationID,
		ProjectID:              projectID,
		BaseURL:                "https://api.diagnyx.io",
		Timeout:                30,
		EvaluateEveryNTokens:   10,
		EnableEarlyTermination: true,
		Debug:                  false,
	}
}

// StartSessionRequest is the request body for starting a session
type StartSessionRequest struct {
	ProjectID              string `json:"projectId"`
	SessionID              string `json:"sessionId,omitempty"`
	Input                  string `json:"input,omitempty"`
	EvaluateEveryNTokens   int    `json:"evaluateEveryNTokens,omitempty"`
	EnableEarlyTermination bool   `json:"enableEarlyTermination"`
}

// EvaluateTokenRequest is the request body for evaluating a token
type EvaluateTokenRequest struct {
	SessionID  string `json:"sessionId"`
	Token      string `json:"token"`
	TokenIndex *int   `json:"tokenIndex,omitempty"`
	IsLast     bool   `json:"isLast,omitempty"`
}
