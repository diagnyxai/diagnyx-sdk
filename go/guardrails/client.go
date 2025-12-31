// Package guardrails provides streaming guardrails for LLM responses
package guardrails

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// ViolationError is returned when a blocking guardrail violation occurs
type ViolationError struct {
	Violation Violation
	Session   *Session
}

func (e *ViolationError) Error() string {
	return fmt.Sprintf("guardrail violation: %s", e.Violation.Message)
}

// Client provides streaming guardrails evaluation
type Client struct {
	config     Config
	httpClient *http.Client
	sessions   map[string]*Session
	mu         sync.RWMutex
}

// NewClient creates a new streaming guardrails client
func NewClient(config Config) *Client {
	if config.BaseURL == "" {
		config.BaseURL = "https://api.diagnyx.io"
	}
	if config.Timeout == 0 {
		config.Timeout = 30
	}
	if config.EvaluateEveryNTokens == 0 {
		config.EvaluateEveryNTokens = 10
	}

	return &Client{
		config: config,
		httpClient: &http.Client{
			Timeout: time.Duration(config.Timeout) * time.Second,
		},
		sessions: make(map[string]*Session),
	}
}

func (c *Client) log(msg string) {
	if c.config.Debug {
		fmt.Printf("[DiagnyxGuardrails] %s\n", msg)
	}
}

func (c *Client) getBaseEndpoint() string {
	return fmt.Sprintf("%s/api/v1/organizations/%s/guardrails",
		strings.TrimSuffix(c.config.BaseURL, "/"),
		c.config.OrganizationID)
}

// StartSession starts a new streaming guardrails session
func (c *Client) StartSession(ctx context.Context, sessionID, input string) (*SessionStartedEvent, error) {
	req := StartSessionRequest{
		ProjectID:              c.config.ProjectID,
		EvaluateEveryNTokens:   c.config.EvaluateEveryNTokens,
		EnableEarlyTermination: c.config.EnableEarlyTermination,
	}
	if sessionID != "" {
		req.SessionID = sessionID
	}
	if input != "" {
		req.Input = input
	}

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.getBaseEndpoint()+"/evaluate/stream/start", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.config.APIKey)
	httpReq.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(httpReq)
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

	event := parseEvent(data)
	if startEvent, ok := event.(*SessionStartedEvent); ok {
		c.mu.Lock()
		c.sessions[startEvent.SessionID] = &Session{
			SessionID:      startEvent.SessionID,
			OrganizationID: c.config.OrganizationID,
			ProjectID:      c.config.ProjectID,
			ActivePolicies: startEvent.ActivePolicies,
			Allowed:        true,
		}
		c.mu.Unlock()
		c.log(fmt.Sprintf("Session started: %s", startEvent.SessionID))
		return startEvent, nil
	}

	if errEvent, ok := event.(*ErrorEvent); ok {
		return nil, fmt.Errorf("failed to start session: %s", errEvent.Error)
	}

	return nil, fmt.Errorf("unexpected response type")
}

// EvaluateToken evaluates a token against guardrail policies
func (c *Client) EvaluateToken(ctx context.Context, sessionID, token string, tokenIndex *int, isLast bool) (<-chan Event, error) {
	c.mu.RLock()
	session := c.sessions[sessionID]
	c.mu.RUnlock()

	if session == nil {
		errChan := make(chan Event, 1)
		errChan <- &ErrorEvent{
			BaseEvent: BaseEvent{Type: EventError, SessionID: sessionID, Timestamp: time.Now().UnixMilli()},
			Error:     "Session not found",
			Code:      "SESSION_NOT_FOUND",
		}
		close(errChan)
		return errChan, nil
	}

	req := EvaluateTokenRequest{
		SessionID: sessionID,
		Token:     token,
		IsLast:    isLast,
	}
	if tokenIndex != nil {
		req.TokenIndex = tokenIndex
	}

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.getBaseEndpoint()+"/evaluate/stream", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.config.APIKey)
	httpReq.Header.Set("Accept", "text/event-stream")

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	events := make(chan Event, 10)

	go func() {
		defer close(events)
		defer resp.Body.Close()

		reader := bufio.NewReader(resp.Body)
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				if err != io.EOF {
					c.log(fmt.Sprintf("Error reading stream: %v", err))
				}
				return
			}

			line = strings.TrimSpace(line)
			if !strings.HasPrefix(line, "data: ") {
				continue
			}

			jsonData := line[6:]
			var data map[string]interface{}
			if err := json.Unmarshal([]byte(jsonData), &data); err != nil {
				c.log(fmt.Sprintf("Failed to parse event: %v", err))
				continue
			}

			event := parseEvent(data)
			c.updateSession(session, event)
			events <- event

			switch event.GetType() {
			case EventEarlyTermination, EventSessionComplete, EventError:
				return
			}
		}
	}()

	return events, nil
}

// CompleteSession completes a streaming session manually
func (c *Client) CompleteSession(ctx context.Context, sessionID string) (<-chan Event, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		fmt.Sprintf("%s/evaluate/stream/%s/complete", c.getBaseEndpoint(), sessionID), nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Authorization", "Bearer "+c.config.APIKey)
	httpReq.Header.Set("Accept", "text/event-stream")

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	events := make(chan Event, 10)

	go func() {
		defer close(events)
		defer resp.Body.Close()
		defer func() {
			c.mu.Lock()
			delete(c.sessions, sessionID)
			c.mu.Unlock()
		}()

		reader := bufio.NewReader(resp.Body)
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				return
			}

			line = strings.TrimSpace(line)
			if !strings.HasPrefix(line, "data: ") {
				continue
			}

			var data map[string]interface{}
			if err := json.Unmarshal([]byte(line[6:]), &data); err != nil {
				continue
			}

			events <- parseEvent(data)
		}
	}()

	return events, nil
}

// CancelSession cancels a streaming session
func (c *Client) CancelSession(ctx context.Context, sessionID string) (bool, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodDelete,
		fmt.Sprintf("%s/evaluate/stream/%s", c.getBaseEndpoint(), sessionID), nil)
	if err != nil {
		return false, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Authorization", "Bearer "+c.config.APIKey)

	resp, err := c.httpClient.Do(httpReq)
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

	c.mu.Lock()
	delete(c.sessions, sessionID)
	c.mu.Unlock()

	return result.Cancelled, nil
}

// GetSession returns the current state of a session
func (c *Client) GetSession(sessionID string) *Session {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.sessions[sessionID]
}

func (c *Client) updateSession(session *Session, event Event) {
	switch e := event.(type) {
	case *ViolationDetectedEvent:
		session.Violations = append(session.Violations, e.ToViolation())
		if e.EnforcementLevel == string(EnforcementBlocking) {
			session.Allowed = false
		}
	case *EarlyTerminationEvent:
		session.Terminated = true
		session.TerminationReason = e.Reason
		session.Allowed = false
		session.TokensProcessed = e.TokensProcessed
	case *SessionCompleteEvent:
		session.TokensProcessed = e.TotalTokens
		session.Allowed = e.Allowed
	}
}

func parseEvent(data map[string]interface{}) Event {
	eventType := EventType(getString(data, "type"))
	sessionID := getString(data, "sessionId")
	if sessionID == "" {
		sessionID = getString(data, "session_id")
	}
	timestamp := getInt64(data, "timestamp")

	base := BaseEvent{Type: eventType, SessionID: sessionID, Timestamp: timestamp}

	switch eventType {
	case EventSessionStarted:
		return &SessionStartedEvent{
			BaseEvent:      base,
			ActivePolicies: getStringSlice(data, "activePolicies", "active_policies"),
		}
	case EventTokenAllowed:
		return &TokenAllowedEvent{
			BaseEvent:         base,
			TokenIndex:        getInt(data, "tokenIndex", "token_index"),
			AccumulatedLength: getInt(data, "accumulatedLength", "accumulated_length"),
		}
	case EventViolationDetected:
		return &ViolationDetectedEvent{
			BaseEvent:        base,
			PolicyID:         getString(data, "policyId", "policy_id"),
			PolicyName:       getString(data, "policyName", "policy_name"),
			PolicyType:       getString(data, "policyType", "policy_type"),
			ViolationType:    getString(data, "violationType", "violation_type"),
			Message:          getString(data, "message"),
			Severity:         getString(data, "severity"),
			EnforcementLevel: getString(data, "enforcementLevel", "enforcement_level"),
			Details:          getMap(data, "details"),
		}
	case EventEarlyTermination:
		var blocking *ViolationDetectedEvent
		if blockingData, ok := data["blockingViolation"].(map[string]interface{}); ok {
			blocking = &ViolationDetectedEvent{
				BaseEvent: BaseEvent{
					Type:      EventViolationDetected,
					SessionID: sessionID,
					Timestamp: getInt64(blockingData, "timestamp"),
				},
				PolicyID:         getString(blockingData, "policyId", "policy_id"),
				PolicyName:       getString(blockingData, "policyName", "policy_name"),
				PolicyType:       getString(blockingData, "policyType", "policy_type"),
				ViolationType:    getString(blockingData, "violationType", "violation_type"),
				Message:          getString(blockingData, "message"),
				Severity:         getString(blockingData, "severity"),
				EnforcementLevel: getString(blockingData, "enforcementLevel", "enforcement_level"),
				Details:          getMap(blockingData, "details"),
			}
		}
		return &EarlyTerminationEvent{
			BaseEvent:         base,
			Reason:            getString(data, "reason"),
			BlockingViolation: blocking,
			TokensProcessed:   getInt(data, "tokensProcessed", "tokens_processed"),
		}
	case EventSessionComplete:
		return &SessionCompleteEvent{
			BaseEvent:       base,
			TotalTokens:     getInt(data, "totalTokens", "total_tokens"),
			TotalViolations: getInt(data, "totalViolations", "total_violations"),
			Allowed:         getBool(data, "allowed"),
			LatencyMs:       getInt(data, "latencyMs", "latency_ms"),
		}
	case EventError:
		return &ErrorEvent{
			BaseEvent: base,
			Error:     getString(data, "error"),
			Code:      getString(data, "code"),
		}
	default:
		return &ErrorEvent{
			BaseEvent: base,
			Error:     "Unknown event type",
		}
	}
}

// Helper functions for parsing
func getString(data map[string]interface{}, keys ...string) string {
	for _, key := range keys {
		if v, ok := data[key].(string); ok {
			return v
		}
	}
	return ""
}

func getInt(data map[string]interface{}, keys ...string) int {
	for _, key := range keys {
		if v, ok := data[key].(float64); ok {
			return int(v)
		}
	}
	return 0
}

func getInt64(data map[string]interface{}, keys ...string) int64 {
	for _, key := range keys {
		if v, ok := data[key].(float64); ok {
			return int64(v)
		}
	}
	return 0
}

func getBool(data map[string]interface{}, keys ...string) bool {
	for _, key := range keys {
		if v, ok := data[key].(bool); ok {
			return v
		}
	}
	return false
}

func getStringSlice(data map[string]interface{}, keys ...string) []string {
	for _, key := range keys {
		if v, ok := data[key].([]interface{}); ok {
			result := make([]string, len(v))
			for i, item := range v {
				if s, ok := item.(string); ok {
					result[i] = s
				}
			}
			return result
		}
	}
	return nil
}

func getMap(data map[string]interface{}, keys ...string) map[string]interface{} {
	for _, key := range keys {
		if v, ok := data[key].(map[string]interface{}); ok {
			return v
		}
	}
	return nil
}
