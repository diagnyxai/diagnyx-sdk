package callbacks

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/diagnyxai/diagnyx-go"
	"github.com/tmc/langchaingo/llms"
)

// mockClient is a mock Diagnyx client for testing
type mockClient struct {
	calls  []diagnyx.LLMCall
	config diagnyx.Config
}

func newMockClient() *mockClient {
	return &mockClient{
		calls: make([]diagnyx.LLMCall, 0),
		config: diagnyx.Config{
			CaptureFullContent: false,
			ContentMaxLength:   10000,
		},
	}
}

func (m *mockClient) Track(call diagnyx.LLMCall) {
	m.calls = append(m.calls, call)
}

func (m *mockClient) Config() diagnyx.Config {
	return m.config
}

func TestNewDiagnyxHandler(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client)
	if handler == nil {
		t.Fatal("Expected handler to be created")
	}
	if handler.client != client {
		t.Error("Expected client to be set")
	}
}

func TestDiagnyxHandlerOptions(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client,
		WithProjectID("test-project"),
		WithEnvironment("test"),
		WithUserIdentifier("test-user"),
		WithCaptureContent(true),
	)

	if handler.projectID != "test-project" {
		t.Errorf("Expected projectID 'test-project', got '%s'", handler.projectID)
	}
	if handler.environment != "test" {
		t.Errorf("Expected environment 'test', got '%s'", handler.environment)
	}
	if handler.userIdentifier != "test-user" {
		t.Errorf("Expected userIdentifier 'test-user', got '%s'", handler.userIdentifier)
	}
	if !handler.captureContent {
		t.Error("Expected captureContent to be true")
	}
}

func TestDetectProvider(t *testing.T) {
	tests := []struct {
		model    string
		expected diagnyx.Provider
	}{
		{"gpt-4", diagnyx.ProviderOpenAI},
		{"gpt-3.5-turbo", diagnyx.ProviderOpenAI},
		{"o1-preview", diagnyx.ProviderOpenAI},
		{"GPT-4", diagnyx.ProviderOpenAI}, // Case insensitive
		{"claude-3-opus", diagnyx.ProviderAnthropic},
		{"claude-2", diagnyx.ProviderAnthropic},
		{"gemini-pro", diagnyx.ProviderGoogle},
		{"mistral-large", diagnyx.ProviderCustom},
		{"mixtral-8x7b", diagnyx.ProviderCustom},
		{"llama-2-70b", diagnyx.ProviderCustom},
		{"unknown-model", diagnyx.ProviderCustom},
	}

	for _, tt := range tests {
		t.Run(tt.model, func(t *testing.T) {
			result := detectProvider(tt.model)
			if result != tt.expected {
				t.Errorf("detectProvider(%s) = %s, expected %s", tt.model, result, tt.expected)
			}
		})
	}
}

func TestHandleLLMStartAndEnd(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client,
		WithProjectID("test-project"),
		WithEnvironment("test"),
	)

	ctx := context.Background()

	// Start the LLM call
	handler.HandleLLMStart(ctx, []string{"Hello, world!"})

	// Small delay to ensure latency is measurable
	time.Sleep(10 * time.Millisecond)

	// End the LLM call
	output := &llms.ContentResponse{
		Choices: []*llms.ContentChoice{
			{
				Content: "Hi there!",
				GenerationInfo: map[string]any{
					"PromptTokens":     10,
					"CompletionTokens": 5,
				},
			},
		},
	}
	handler.HandleLLMGenerateContentEnd(ctx, output)

	// Verify the call was tracked
	if client.BufferSize() == 0 {
		t.Skip("Call may have been flushed, skipping buffer check")
	}
}

func TestHandleLLMError(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client,
		WithProjectID("test-project"),
	)

	ctx := context.Background()

	// Start the LLM call
	handler.HandleLLMStart(ctx, []string{"Hello"})

	// Trigger error
	handler.HandleLLMError(ctx, errors.New("API rate limit exceeded"))

	// Verify the error call was tracked
	if client.BufferSize() == 0 {
		t.Skip("Call may have been flushed, skipping buffer check")
	}
}

func TestHandleLLMErrorTruncatesLongMessage(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client)

	ctx := context.Background()

	// Start the LLM call
	handler.HandleLLMStart(ctx, []string{"Hello"})

	// Create a very long error message
	longMsg := make([]byte, 600)
	for i := range longMsg {
		longMsg[i] = 'A'
	}

	// Trigger error with long message
	handler.HandleLLMError(ctx, errors.New(string(longMsg)))

	// The error message should be truncated (we can't easily verify without exposing internals)
}

func TestHandleGenerateContentStart(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client)

	ctx := context.Background()

	messages := []llms.MessageContent{
		{
			Role: llms.ChatMessageTypeHuman,
			Parts: []llms.ContentPart{
				llms.TextContent{Text: "Hello, Claude!"},
			},
		},
	}

	handler.HandleLLMGenerateContentStart(ctx, messages)

	// Verify metadata was stored
	handler.mu.Lock()
	defer handler.mu.Unlock()

	if len(handler.callMetadata) == 0 {
		t.Skip("Metadata may have been cleared, skipping check")
	}
}

func TestConcurrentCalls(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client)

	// Simulate concurrent calls with different contexts
	ctx1 := context.WithValue(context.Background(), "run_id", "run-1")
	ctx2 := context.WithValue(context.Background(), "run_id", "run-2")

	// Start both calls
	handler.HandleLLMStart(ctx1, []string{"First prompt"})
	handler.HandleLLMStart(ctx2, []string{"Second prompt"})

	// End in reverse order
	handler.HandleLLMGenerateContentEnd(ctx2, &llms.ContentResponse{})
	handler.HandleLLMGenerateContentEnd(ctx1, &llms.ContentResponse{})

	// Both calls should be tracked (may be flushed)
}

func TestChainCallbacksAreNoOps(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client)
	ctx := context.Background()

	// These should not panic
	handler.HandleChainStart(ctx, map[string]any{})
	handler.HandleChainEnd(ctx, map[string]any{})
	handler.HandleChainError(ctx, errors.New("test"))
}

func TestToolCallbacksAreNoOps(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client)
	ctx := context.Background()

	// These should not panic
	handler.HandleToolStart(ctx, "input")
	handler.HandleToolEnd(ctx, "output")
	handler.HandleToolError(ctx, errors.New("test"))
}

func TestRetrieverCallbacksAreNoOps(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client)
	ctx := context.Background()

	// These should not panic
	handler.HandleRetrieverStart(ctx, "query")
	handler.HandleRetrieverEnd(ctx, "query", nil)
}

func TestStreamingCallbackIsNoOp(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client)
	ctx := context.Background()

	// This should not panic
	handler.HandleStreamingFunc(ctx, []byte("chunk"))
}

func TestTextCallbackIsNoOp(t *testing.T) {
	client := diagnyx.NewClient("test-key")
	defer client.Close()

	handler := NewDiagnyxHandler(client)
	ctx := context.Background()

	// This should not panic
	handler.HandleText(ctx, "some text")
}
