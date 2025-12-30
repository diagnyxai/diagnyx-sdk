package diagnyx

import (
	"encoding/json"
	"testing"
	"time"
)

func TestLLMCallJSON(t *testing.T) {
	t.Run("marshals with all fields", func(t *testing.T) {
		ttft := int64(100)
		call := LLMCall{
			Provider:       ProviderOpenAI,
			Model:          "gpt-4",
			Endpoint:       "/v1/chat/completions",
			InputTokens:    100,
			OutputTokens:   50,
			LatencyMs:      500,
			TTFTMs:         &ttft,
			Status:         StatusSuccess,
			ProjectID:      "proj-123",
			Environment:    "production",
			UserIdentifier: "user-456",
			TraceID:        "trace-789",
			SpanID:         "span-abc",
			Metadata:       map[string]interface{}{"key": "value"},
			Timestamp:      time.Date(2024, 1, 15, 10, 0, 0, 0, time.UTC),
			FullPrompt:     "Hello, how are you?",
			FullResponse:   "I'm doing well!",
		}

		data, err := json.Marshal(call)
		if err != nil {
			t.Fatalf("failed to marshal: %v", err)
		}

		var result map[string]interface{}
		if err := json.Unmarshal(data, &result); err != nil {
			t.Fatalf("failed to unmarshal: %v", err)
		}

		if result["provider"] != "openai" {
			t.Errorf("expected provider 'openai', got '%v'", result["provider"])
		}
		if result["model"] != "gpt-4" {
			t.Errorf("expected model 'gpt-4', got '%v'", result["model"])
		}
		if result["status"] != "success" {
			t.Errorf("expected status 'success', got '%v'", result["status"])
		}
	})

	t.Run("omits empty optional fields", func(t *testing.T) {
		call := LLMCall{
			Provider:     ProviderOpenAI,
			Model:        "gpt-4",
			InputTokens:  100,
			OutputTokens: 50,
			Status:       StatusSuccess,
			Timestamp:    time.Now().UTC(),
		}

		data, err := json.Marshal(call)
		if err != nil {
			t.Fatalf("failed to marshal: %v", err)
		}

		var result map[string]interface{}
		if err := json.Unmarshal(data, &result); err != nil {
			t.Fatalf("failed to unmarshal: %v", err)
		}

		// These fields should be omitted
		if _, ok := result["endpoint"]; ok && result["endpoint"] != "" {
			t.Error("endpoint should be omitted when empty")
		}
		if _, ok := result["project_id"]; ok && result["project_id"] != "" {
			t.Error("project_id should be omitted when empty")
		}
	})

	t.Run("unmarshals correctly", func(t *testing.T) {
		jsonData := `{
			"provider": "anthropic",
			"model": "claude-3",
			"input_tokens": 200,
			"output_tokens": 100,
			"latency_ms": 750,
			"status": "success",
			"environment": "staging"
		}`

		var call LLMCall
		if err := json.Unmarshal([]byte(jsonData), &call); err != nil {
			t.Fatalf("failed to unmarshal: %v", err)
		}

		if call.Provider != ProviderAnthropic {
			t.Errorf("expected provider 'anthropic', got '%s'", call.Provider)
		}
		if call.Model != "claude-3" {
			t.Errorf("expected model 'claude-3', got '%s'", call.Model)
		}
		if call.InputTokens != 200 {
			t.Errorf("expected input tokens 200, got %d", call.InputTokens)
		}
		if call.Environment != "staging" {
			t.Errorf("expected environment 'staging', got '%s'", call.Environment)
		}
	})
}

func TestProviderConstants(t *testing.T) {
	tests := []struct {
		provider Provider
		expected string
	}{
		{ProviderOpenAI, "openai"},
		{ProviderAnthropic, "anthropic"},
		{ProviderGoogle, "google"},
		{ProviderAzure, "azure"},
		{ProviderAWS, "aws"},
		{ProviderCustom, "custom"},
	}

	for _, tt := range tests {
		t.Run(tt.expected, func(t *testing.T) {
			if string(tt.provider) != tt.expected {
				t.Errorf("expected '%s', got '%s'", tt.expected, string(tt.provider))
			}
		})
	}
}

func TestCallStatusConstants(t *testing.T) {
	tests := []struct {
		status   CallStatus
		expected string
	}{
		{StatusSuccess, "success"},
		{StatusError, "error"},
		{StatusTimeout, "timeout"},
		{StatusRateLimited, "rate_limited"},
	}

	for _, tt := range tests {
		t.Run(tt.expected, func(t *testing.T) {
			if string(tt.status) != tt.expected {
				t.Errorf("expected '%s', got '%s'", tt.expected, string(tt.status))
			}
		})
	}
}

func TestBatchRequestJSON(t *testing.T) {
	t.Run("marshals batch request correctly", func(t *testing.T) {
		req := BatchRequest{
			Calls: []LLMCall{
				{Provider: ProviderOpenAI, Model: "gpt-4", Status: StatusSuccess, InputTokens: 100, OutputTokens: 50},
				{Provider: ProviderAnthropic, Model: "claude-3", Status: StatusSuccess, InputTokens: 200, OutputTokens: 100},
			},
		}

		data, err := json.Marshal(req)
		if err != nil {
			t.Fatalf("failed to marshal: %v", err)
		}

		var result map[string]interface{}
		if err := json.Unmarshal(data, &result); err != nil {
			t.Fatalf("failed to unmarshal: %v", err)
		}

		calls, ok := result["calls"].([]interface{})
		if !ok {
			t.Fatal("expected calls array")
		}
		if len(calls) != 2 {
			t.Errorf("expected 2 calls, got %d", len(calls))
		}
	})
}

func TestBatchResponseJSON(t *testing.T) {
	t.Run("unmarshals batch response correctly", func(t *testing.T) {
		jsonData := `{
			"tracked": 5,
			"total_cost": 0.0025,
			"total_tokens": 500,
			"ids": ["id-1", "id-2", "id-3", "id-4", "id-5"]
		}`

		var resp BatchResponse
		if err := json.Unmarshal([]byte(jsonData), &resp); err != nil {
			t.Fatalf("failed to unmarshal: %v", err)
		}

		if resp.Tracked != 5 {
			t.Errorf("expected tracked 5, got %d", resp.Tracked)
		}
		if resp.TotalCost != 0.0025 {
			t.Errorf("expected total cost 0.0025, got %f", resp.TotalCost)
		}
		if resp.TotalTokens != 500 {
			t.Errorf("expected total tokens 500, got %d", resp.TotalTokens)
		}
		if len(resp.IDs) != 5 {
			t.Errorf("expected 5 IDs, got %d", len(resp.IDs))
		}
	})
}

func TestTrackOptions(t *testing.T) {
	opts := TrackOptions{
		ProjectID:      "proj-123",
		Environment:    "production",
		UserIdentifier: "user-456",
		TraceID:        "trace-789",
		SpanID:         "span-abc",
		Metadata:       map[string]interface{}{"custom": "data"},
		FullPrompt:     "test prompt",
		FullResponse:   "test response",
	}

	if opts.ProjectID != "proj-123" {
		t.Errorf("expected project ID 'proj-123', got '%s'", opts.ProjectID)
	}
	if opts.Environment != "production" {
		t.Errorf("expected environment 'production', got '%s'", opts.Environment)
	}
	if opts.Metadata["custom"] != "data" {
		t.Error("expected metadata to contain custom key")
	}
}
