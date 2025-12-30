// Package callbacks provides callback handlers for LLM framework integrations.
package callbacks

import (
	"context"
	"strings"
	"sync"
	"time"

	"github.com/diagnyxai/diagnyx-go"
	"github.com/google/uuid"
	"github.com/tmc/langchaingo/llms"
	"github.com/tmc/langchaingo/schema"
)

// DiagnyxHandler is a LangChain callback handler for Diagnyx cost tracking.
// Implements the langchaingo callbacks.Handler interface.
type DiagnyxHandler struct {
	client         *diagnyx.Client
	projectID      string
	environment    string
	userIdentifier string
	captureContent bool

	mu             sync.Mutex
	callStarts     map[string]time.Time
	callMetadata   map[string]*callMeta
}

type callMeta struct {
	model   string
	prompts []string
}

// HandlerOption is a function that configures a DiagnyxHandler.
type HandlerOption func(*DiagnyxHandler)

// WithProjectID sets the project ID for tracking.
func WithProjectID(id string) HandlerOption {
	return func(h *DiagnyxHandler) {
		h.projectID = id
	}
}

// WithEnvironment sets the environment for tracking.
func WithEnvironment(env string) HandlerOption {
	return func(h *DiagnyxHandler) {
		h.environment = env
	}
}

// WithUserIdentifier sets the user identifier for tracking.
func WithUserIdentifier(id string) HandlerOption {
	return func(h *DiagnyxHandler) {
		h.userIdentifier = id
	}
}

// WithCaptureContent enables capturing full prompt/response content.
func WithCaptureContent(capture bool) HandlerOption {
	return func(h *DiagnyxHandler) {
		h.captureContent = capture
	}
}

// NewDiagnyxHandler creates a new LangChain callback handler for Diagnyx.
func NewDiagnyxHandler(client *diagnyx.Client, opts ...HandlerOption) *DiagnyxHandler {
	h := &DiagnyxHandler{
		client:       client,
		callStarts:   make(map[string]time.Time),
		callMetadata: make(map[string]*callMeta),
	}

	for _, opt := range opts {
		opt(h)
	}

	return h
}

// HandleLLMStart is called when an LLM starts running.
func (h *DiagnyxHandler) HandleLLMStart(ctx context.Context, prompts []string) {
	runID := h.getRunID(ctx)

	h.mu.Lock()
	defer h.mu.Unlock()

	h.callStarts[runID] = time.Now()
	h.callMetadata[runID] = &callMeta{
		prompts: prompts,
	}
}

// HandleLLMGenerateContentStart is called when content generation starts.
func (h *DiagnyxHandler) HandleLLMGenerateContentStart(ctx context.Context, ms []llms.MessageContent) {
	runID := h.getRunID(ctx)

	// Convert messages to prompts
	var prompts []string
	for _, m := range ms {
		var parts []string
		for _, p := range m.Parts {
			if tc, ok := p.(llms.TextContent); ok {
				parts = append(parts, tc.Text)
			}
		}
		if len(parts) > 0 {
			prompts = append(prompts, strings.Join(parts, " "))
		}
	}

	h.mu.Lock()
	defer h.mu.Unlock()

	h.callStarts[runID] = time.Now()
	h.callMetadata[runID] = &callMeta{
		prompts: prompts,
	}
}

// HandleLLMGenerateContentEnd is called when an LLM finishes generating content.
func (h *DiagnyxHandler) HandleLLMGenerateContentEnd(ctx context.Context, res *llms.ContentResponse) {
	runID := h.getRunID(ctx)

	h.mu.Lock()
	startTime, hasStart := h.callStarts[runID]
	meta := h.callMetadata[runID]
	delete(h.callStarts, runID)
	delete(h.callMetadata, runID)
	h.mu.Unlock()

	var latencyMs int64
	if hasStart {
		latencyMs = time.Since(startTime).Milliseconds()
	}

	// Extract model name
	model := "unknown"
	if meta != nil && meta.model != "" {
		model = meta.model
	}

	// Detect provider from model name
	provider := detectProvider(model)

	// Extract token usage from response
	inputTokens := 0
	outputTokens := 0

	// Try to get token counts from response choices
	if res != nil && len(res.Choices) > 0 {
		for _, choice := range res.Choices {
			if choice.GenerationInfo != nil {
				if pt, ok := choice.GenerationInfo["PromptTokens"].(int); ok {
					inputTokens = pt
				}
				if ct, ok := choice.GenerationInfo["CompletionTokens"].(int); ok {
					outputTokens = ct
				}
			}
		}
	}

	// Build the call data
	call := diagnyx.LLMCall{
		Provider:       provider,
		Model:          model,
		InputTokens:    inputTokens,
		OutputTokens:   outputTokens,
		Status:         diagnyx.StatusSuccess,
		LatencyMs:      latencyMs,
		ProjectID:      h.projectID,
		Environment:    h.environment,
		UserIdentifier: h.userIdentifier,
		Timestamp:      time.Now().UTC(),
	}

	// Capture content if enabled
	if h.captureContent && meta != nil {
		maxLen := h.client.Config().ContentMaxLength
		if maxLen == 0 {
			maxLen = 10000
		}

		if len(meta.prompts) > 0 {
			prompt := strings.Join(meta.prompts, "\n---\n")
			if len(prompt) > maxLen {
				prompt = prompt[:maxLen] + "... [truncated]"
			}
			call.FullPrompt = prompt
		}

		if res != nil && len(res.Choices) > 0 {
			var responseParts []string
			for _, choice := range res.Choices {
				if choice.Content != "" {
					responseParts = append(responseParts, choice.Content)
				}
			}
			if len(responseParts) > 0 {
				response := strings.Join(responseParts, "\n")
				if len(response) > maxLen {
					response = response[:maxLen] + "... [truncated]"
				}
				call.FullResponse = response
			}
		}
	}

	h.client.Track(call)
}

// HandleLLMError is called when an LLM errors.
func (h *DiagnyxHandler) HandleLLMError(ctx context.Context, err error) {
	runID := h.getRunID(ctx)

	h.mu.Lock()
	startTime, hasStart := h.callStarts[runID]
	meta := h.callMetadata[runID]
	delete(h.callStarts, runID)
	delete(h.callMetadata, runID)
	h.mu.Unlock()

	var latencyMs int64
	if hasStart {
		latencyMs = time.Since(startTime).Milliseconds()
	}

	// Extract model name
	model := "unknown"
	if meta != nil && meta.model != "" {
		model = meta.model
	}

	// Detect provider
	provider := detectProvider(model)

	// Extract error details
	errorMsg := err.Error()
	if len(errorMsg) > 500 {
		errorMsg = errorMsg[:500]
	}

	call := diagnyx.LLMCall{
		Provider:       provider,
		Model:          model,
		InputTokens:    0,
		OutputTokens:   0,
		Status:         diagnyx.StatusError,
		LatencyMs:      latencyMs,
		ErrorMessage:   errorMsg,
		ProjectID:      h.projectID,
		Environment:    h.environment,
		UserIdentifier: h.userIdentifier,
		Timestamp:      time.Now().UTC(),
	}

	h.client.Track(call)
}

// HandleChainStart is called when a chain starts. No-op for cost tracking.
func (h *DiagnyxHandler) HandleChainStart(ctx context.Context, inputs map[string]any) {
	// No-op for cost tracking
}

// HandleChainEnd is called when a chain ends. No-op for cost tracking.
func (h *DiagnyxHandler) HandleChainEnd(ctx context.Context, outputs map[string]any) {
	// No-op for cost tracking
}

// HandleChainError is called when a chain errors. No-op for cost tracking.
func (h *DiagnyxHandler) HandleChainError(ctx context.Context, err error) {
	// No-op for cost tracking
}

// HandleToolStart is called when a tool starts. No-op for cost tracking.
func (h *DiagnyxHandler) HandleToolStart(ctx context.Context, input string) {
	// No-op for cost tracking
}

// HandleToolEnd is called when a tool ends. No-op for cost tracking.
func (h *DiagnyxHandler) HandleToolEnd(ctx context.Context, output string) {
	// No-op for cost tracking
}

// HandleToolError is called when a tool errors. No-op for cost tracking.
func (h *DiagnyxHandler) HandleToolError(ctx context.Context, err error) {
	// No-op for cost tracking
}

// HandleAgentAction is called when an agent takes an action. No-op for cost tracking.
func (h *DiagnyxHandler) HandleAgentAction(ctx context.Context, action schema.AgentAction) {
	// No-op for cost tracking
}

// HandleAgentFinish is called when an agent finishes. No-op for cost tracking.
func (h *DiagnyxHandler) HandleAgentFinish(ctx context.Context, finish schema.AgentFinish) {
	// No-op for cost tracking
}

// HandleRetrieverStart is called when a retriever starts. No-op for cost tracking.
func (h *DiagnyxHandler) HandleRetrieverStart(ctx context.Context, query string) {
	// No-op for cost tracking
}

// HandleRetrieverEnd is called when a retriever ends. No-op for cost tracking.
func (h *DiagnyxHandler) HandleRetrieverEnd(ctx context.Context, query string, documents []schema.Document) {
	// No-op for cost tracking
}

// HandleStreamingFunc is called for streaming. No-op for cost tracking.
func (h *DiagnyxHandler) HandleStreamingFunc(ctx context.Context, chunk []byte) {
	// No-op for cost tracking
}

// HandleText is called for text output. No-op for cost tracking.
func (h *DiagnyxHandler) HandleText(ctx context.Context, text string) {
	// No-op for cost tracking
}

// getRunID extracts or generates a run ID from context.
func (h *DiagnyxHandler) getRunID(ctx context.Context) string {
	// Try to get run ID from context if available
	if runID, ok := ctx.Value("run_id").(string); ok && runID != "" {
		return runID
	}
	// Generate a new UUID if not found
	return uuid.New().String()
}

// detectProvider detects the LLM provider from the model name.
func detectProvider(model string) diagnyx.Provider {
	modelLower := strings.ToLower(model)

	providerPrefixes := map[string]diagnyx.Provider{
		"gpt-":     diagnyx.ProviderOpenAI,
		"o1-":      diagnyx.ProviderOpenAI,
		"claude-":  diagnyx.ProviderAnthropic,
		"gemini-":  diagnyx.ProviderGoogle,
		"command":  diagnyx.ProviderCustom, // Cohere
		"mistral":  diagnyx.ProviderCustom,
		"mixtral":  diagnyx.ProviderCustom,
		"llama":    diagnyx.ProviderCustom,
	}

	for prefix, provider := range providerPrefixes {
		if strings.HasPrefix(modelLower, prefix) {
			return provider
		}
	}

	return diagnyx.ProviderCustom
}
