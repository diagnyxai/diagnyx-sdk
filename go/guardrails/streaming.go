// Package guardrails provides streaming guardrails for real-time LLM output validation.
package guardrails

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// StreamingGuardrail provides token-by-token evaluation of LLM output
// against configured guardrail policies with early termination support.
//
// Example:
//
//	config := StreamingGuardrailConfig{
//		APIKey:         "dx_...",
//		OrganizationID: "org_123",
//		ProjectID:      "proj_456",
//	}
//	guardrail := NewStreamingGuardrail(config)
//
//	session, err := guardrail.StartSession(ctx, nil)
//	if err != nil {
//		log.Fatal(err)
//	}
//
//	for token := range tokenStream {
//		filtered, err := guardrail.Evaluate(ctx, token, false)
//		if err != nil {
//			var violationErr *ViolationError
//			if errors.As(err, &violationErr) {
//				log.Printf("Blocked: %s", violationErr.Violation.Message)
//				break
//			}
//			log.Fatal(err)
//		}
//		fmt.Print(filtered)
//	}
type StreamingGuardrail struct {
	config     StreamingGuardrailConfig
	httpClient *http.Client
	session    *StreamingGuardrailSession
	tokenIndex int
	mu         sync.RWMutex
}

// StreamingGuardrailConfig holds configuration for StreamingGuardrail
type StreamingGuardrailConfig struct {
	APIKey                 string
	OrganizationID         string
	ProjectID              string
	BaseURL                string
	Timeout                time.Duration
	EvaluateEveryNTokens   int
	EnableEarlyTermination bool
	Debug                  bool
}

// StreamingGuardrailSession represents an active streaming session
type StreamingGuardrailSession struct {
	SessionID        string
	OrganizationID   string
	ProjectID        string
	ActivePolicies   []string
	TokensProcessed  int
	Violations       []Violation
	Terminated       bool
	TerminationReason string
	Allowed          bool
	AccumulatedText  string
}

// ViolationError is returned when a blocking guardrail violation occurs
type ViolationError struct {
	Violation Violation
	Session   *StreamingGuardrailSession
}

func (e *ViolationError) Error() string {
	return fmt.Sprintf("guardrail violation: %s", e.Violation.Message)
}

// EvaluateOptions contains options for token evaluation
type EvaluateOptions struct {
	TokenIndex *int
	IsLast     bool
}

// NewStreamingGuardrail creates a new streaming guardrail client
func NewStreamingGuardrail(config StreamingGuardrailConfig) *StreamingGuardrail {
	if config.BaseURL == "" {
		config.BaseURL = "https://api.diagnyx.io"
	}
	if config.Timeout == 0 {
		config.Timeout = 30 * time.Second
	}
	if config.EvaluateEveryNTokens == 0 {
		config.EvaluateEveryNTokens = 10
	}

	return &StreamingGuardrail{
		config: config,
		httpClient: &http.Client{
			Timeout: config.Timeout,
		},
	}
}

func (sg *StreamingGuardrail) log(msg string) {
	if sg.config.Debug {
		fmt.Printf("[DiagnyxGuardrails] %s\n", msg)
	}
}

func (sg *StreamingGuardrail) getBaseEndpoint() string {
	return fmt.Sprintf("%s/api/v1/organizations/%s/guardrails",
		strings.TrimSuffix(sg.config.BaseURL, "/"),
		sg.config.OrganizationID)
}

// StartSession starts a new streaming guardrail session
func (sg *StreamingGuardrail) StartSession(ctx context.Context, input *string) (*StreamingGuardrailSession, error) {
	sg.mu.Lock()
	defer sg.mu.Unlock()

	payload := map[string]interface{}{
		"projectId":              sg.config.ProjectID,
		"evaluateEveryNTokens":   sg.config.EvaluateEveryNTokens,
		"enableEarlyTermination": sg.config.EnableEarlyTermination,
	}
	if input != nil {
		payload["input"] = *input
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		sg.getBaseEndpoint()+"/evaluate/stream/start", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+sg.config.APIKey)
	req.Header.Set("Accept", "application/json")

	resp, err := sg.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	var data map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	eventType, _ := data["type"].(string)
	if eventType == "session_started" {
		sessionID, _ := data["sessionId"].(string)
		policies := getStringSlice(data, "activePolicies")

		sg.session = &StreamingGuardrailSession{
			SessionID:      sessionID,
			OrganizationID: sg.config.OrganizationID,
			ProjectID:      sg.config.ProjectID,
			ActivePolicies: policies,
			Allowed:        true,
		}
		sg.tokenIndex = 0
		sg.log(fmt.Sprintf("Session started: %s", sessionID))
		return sg.session, nil
	} else if eventType == "error" {
		errorMsg, _ := data["error"].(string)
		return nil, fmt.Errorf("failed to start session: %s", errorMsg)
	}

	return nil, errors.New("unexpected response type")
}

// Evaluate evaluates a token against guardrail policies
// Returns the token if it passes validation, empty string if blocked,
// and an error if a blocking violation occurred.
func (sg *StreamingGuardrail) Evaluate(ctx context.Context, token string, isLast bool) (string, error) {
	return sg.EvaluateWithOptions(ctx, token, EvaluateOptions{IsLast: isLast})
}

// EvaluateWithOptions evaluates a token with additional options
func (sg *StreamingGuardrail) EvaluateWithOptions(ctx context.Context, token string, opts EvaluateOptions) (string, error) {
	sg.mu.Lock()
	defer sg.mu.Unlock()

	if sg.session == nil {
		return "", errors.New("no active session, call StartSession first")
	}

	tokenIndex := sg.tokenIndex
	if opts.TokenIndex != nil {
		tokenIndex = *opts.TokenIndex
	}
	sg.tokenIndex++

	sg.session.AccumulatedText += token

	payload := map[string]interface{}{
		"sessionId":  sg.session.SessionID,
		"token":      token,
		"tokenIndex": tokenIndex,
		"isLast":     opts.IsLast,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("failed to marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		sg.getBaseEndpoint()+"/evaluate/stream", bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+sg.config.APIKey)
	req.Header.Set("Accept", "text/event-stream")

	resp, err := sg.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	reader := bufio.NewReader(resp.Body)
	var result string

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			if err == io.EOF {
				break
			}
			return result, fmt.Errorf("error reading stream: %w", err)
		}

		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "data: ") {
			continue
		}

		jsonData := line[6:]
		var data map[string]interface{}
		if err := json.Unmarshal([]byte(jsonData), &data); err != nil {
			sg.log(fmt.Sprintf("Failed to parse event: %v", err))
			continue
		}

		eventType, _ := data["type"].(string)

		switch eventType {
		case "token_allowed":
			idx, _ := data["tokenIndex"].(float64)
			sg.session.TokensProcessed = int(idx) + 1
			result = token

		case "violation_detected":
			violation := sg.parseViolation(data)
			sg.session.Violations = append(sg.session.Violations, violation)
			if violation.EnforcementLevel == EnforcementBlocking {
				sg.session.Allowed = false
			}

		case "early_termination":
			blockingData, _ := data["blockingViolation"].(map[string]interface{})
			violation := sg.parseViolation(blockingData)
			sg.session.Terminated = true
			reason, _ := data["reason"].(string)
			sg.session.TerminationReason = reason
			sg.session.Allowed = false
			return "", &ViolationError{
				Violation: violation,
				Session:   sg.session,
			}

		case "session_complete":
			totalTokens, _ := data["totalTokens"].(float64)
			allowed, _ := data["allowed"].(bool)
			sg.session.TokensProcessed = int(totalTokens)
			sg.session.Allowed = allowed

		case "error":
			errorMsg, _ := data["error"].(string)
			sg.log(fmt.Sprintf("Error: %s", errorMsg))
		}
	}

	return result, nil
}

// EvaluateChannel evaluates tokens from a channel and sends results to output channel
func (sg *StreamingGuardrail) EvaluateChannel(ctx context.Context, tokens <-chan string, markLast func(string) bool) (<-chan string, <-chan error) {
	results := make(chan string, 10)
	errors := make(chan error, 1)

	go func() {
		defer close(results)
		defer close(errors)

		for token := range tokens {
			select {
			case <-ctx.Done():
				errors <- ctx.Err()
				return
			default:
				isLast := markLast != nil && markLast(token)
				result, err := sg.Evaluate(ctx, token, isLast)
				if err != nil {
					errors <- err
					return
				}
				if result != "" {
					results <- result
				}
			}
		}
	}()

	return results, errors
}

// CompleteSession completes the current session
func (sg *StreamingGuardrail) CompleteSession(ctx context.Context) (*StreamingGuardrailSession, error) {
	sg.mu.Lock()
	defer sg.mu.Unlock()

	if sg.session == nil {
		return nil, errors.New("no active session")
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		fmt.Sprintf("%s/evaluate/stream/%s/complete", sg.getBaseEndpoint(), sg.session.SessionID), nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+sg.config.APIKey)
	req.Header.Set("Accept", "text/event-stream")

	resp, err := sg.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	reader := bufio.NewReader(resp.Body)
	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			if err == io.EOF {
				break
			}
			break
		}

		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "data: ") {
			continue
		}

		var data map[string]interface{}
		if err := json.Unmarshal([]byte(line[6:]), &data); err != nil {
			continue
		}

		if data["type"] == "session_complete" {
			totalTokens, _ := data["totalTokens"].(float64)
			allowed, _ := data["allowed"].(bool)
			sg.session.TokensProcessed = int(totalTokens)
			sg.session.Allowed = allowed
		}
	}

	session := sg.session
	sg.session = nil
	return session, nil
}

// CancelSession cancels the current session
func (sg *StreamingGuardrail) CancelSession(ctx context.Context) (bool, error) {
	sg.mu.Lock()
	defer sg.mu.Unlock()

	if sg.session == nil {
		return false, nil
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodDelete,
		fmt.Sprintf("%s/evaluate/stream/%s", sg.getBaseEndpoint(), sg.session.SessionID), nil)
	if err != nil {
		return false, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+sg.config.APIKey)

	resp, err := sg.httpClient.Do(req)
	if err != nil {
		return false, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	var result struct {
		Cancelled bool `json:"cancelled"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return false, fmt.Errorf("failed to decode response: %w", err)
	}

	sg.session = nil
	return result.Cancelled, nil
}

// GetSession returns the current session
func (sg *StreamingGuardrail) GetSession() *StreamingGuardrailSession {
	sg.mu.RLock()
	defer sg.mu.RUnlock()
	return sg.session
}

// IsActive returns true if there's an active session
func (sg *StreamingGuardrail) IsActive() bool {
	sg.mu.RLock()
	defer sg.mu.RUnlock()
	return sg.session != nil && !sg.session.Terminated
}

func (sg *StreamingGuardrail) parseViolation(data map[string]interface{}) Violation {
	if data == nil {
		return Violation{}
	}

	enforcement := getString(data, "enforcementLevel", "enforcement_level")
	level := EnforcementAdvisory
	if enforcement != "" {
		level = EnforcementLevel(enforcement)
	}

	return Violation{
		PolicyID:         getString(data, "policyId", "policy_id"),
		PolicyName:       getString(data, "policyName", "policy_name"),
		PolicyType:       getString(data, "policyType", "policy_type"),
		ViolationType:    getString(data, "violationType", "violation_type"),
		Message:          getString(data, "message"),
		Severity:         getString(data, "severity"),
		EnforcementLevel: level,
		Details:          getMap(data, "details"),
	}
}

// StreamWithGuardrails wraps a token channel with guardrail protection
func StreamWithGuardrails(
	ctx context.Context,
	config StreamingGuardrailConfig,
	tokens <-chan string,
	input *string,
	markLast func(string) bool,
) (<-chan string, <-chan error) {
	results := make(chan string, 10)
	errors := make(chan error, 1)

	go func() {
		defer close(results)
		defer close(errors)

		guardrail := NewStreamingGuardrail(config)

		_, err := guardrail.StartSession(ctx, input)
		if err != nil {
			errors <- err
			return
		}

		for token := range tokens {
			select {
			case <-ctx.Done():
				errors <- ctx.Err()
				return
			default:
				isLast := markLast != nil && markLast(token)
				result, err := guardrail.Evaluate(ctx, token, isLast)
				if err != nil {
					errors <- err
					return
				}
				if result != "" {
					results <- result
				}
			}
		}

		if guardrail.IsActive() {
			_, _ = guardrail.CompleteSession(ctx)
		}
	}()

	return results, errors
}
