package diagnyx

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/sashabaranov/go-openai"
)

// truncateContent truncates a string to maxLength, appending "... [truncated]" if needed
func truncateContent(content string, maxLength int) string {
	if maxLength <= 0 {
		maxLength = 10000
	}
	if len(content) > maxLength {
		return content[:maxLength] + "... [truncated]"
	}
	return content
}

// extractOpenAIPrompt extracts prompt content from OpenAI messages
func extractOpenAIPrompt(messages []openai.ChatCompletionMessage, maxLength int) string {
	if len(messages) == 0 {
		return ""
	}

	var parts []string
	for _, m := range messages {
		var content string
		if m.Content != "" {
			content = m.Content
		} else if len(m.MultiContent) > 0 {
			// Handle multi-content messages (images, etc.)
			var textParts []string
			for _, c := range m.MultiContent {
				if c.Type == openai.ChatMessagePartTypeText {
					textParts = append(textParts, c.Text)
				} else {
					// Serialize non-text content
					if b, err := json.Marshal(c); err == nil {
						textParts = append(textParts, string(b))
					}
				}
			}
			content = strings.Join(textParts, "")
		}
		parts = append(parts, fmt.Sprintf("[%s]: %s", m.Role, content))
	}

	return truncateContent(strings.Join(parts, "\n"), maxLength)
}

// extractOpenAIResponse extracts response content from OpenAI completion
func extractOpenAIResponse(resp openai.ChatCompletionResponse, maxLength int) string {
	if len(resp.Choices) == 0 {
		return ""
	}
	content := resp.Choices[0].Message.Content
	return truncateContent(content, maxLength)
}

// OpenAIWrapper wraps an OpenAI client for automatic tracking
type OpenAIWrapper struct {
	client  *openai.Client
	diagnyx *Client
	opts    TrackOptions
}

// WrapOpenAI wraps an OpenAI client for automatic call tracking
func WrapOpenAI(client *openai.Client, diagnyx *Client, opts ...TrackOptions) *OpenAIWrapper {
	var trackOpts TrackOptions
	if len(opts) > 0 {
		trackOpts = opts[0]
	}
	return &OpenAIWrapper{
		client:  client,
		diagnyx: diagnyx,
		opts:    trackOpts,
	}
}

// CreateChatCompletion creates a chat completion and tracks the call
func (w *OpenAIWrapper) CreateChatCompletion(ctx context.Context, req openai.ChatCompletionRequest) (openai.ChatCompletionResponse, error) {
	start := time.Now()

	resp, err := w.client.CreateChatCompletion(ctx, req)

	latencyMs := time.Since(start).Milliseconds()

	call := LLMCall{
		Provider:       ProviderOpenAI,
		Model:          req.Model,
		Endpoint:       "/v1/chat/completions",
		LatencyMs:      latencyMs,
		ProjectID:      w.opts.ProjectID,
		Environment:    w.opts.Environment,
		UserIdentifier: w.opts.UserIdentifier,
		TraceID:        w.opts.TraceID,
		SpanID:         w.opts.SpanID,
		Metadata:       w.opts.Metadata,
		Timestamp:      time.Now().UTC(),
	}

	if err != nil {
		call.Status = StatusError
		call.ErrorMessage = err.Error()
		call.InputTokens = 0
		call.OutputTokens = 0
	} else {
		call.Status = StatusSuccess
		call.InputTokens = resp.Usage.PromptTokens
		call.OutputTokens = resp.Usage.CompletionTokens

		// Extract content if enabled
		config := w.diagnyx.Config()
		if config.CaptureFullContent {
			call.FullPrompt = extractOpenAIPrompt(req.Messages, config.ContentMaxLength)
			call.FullResponse = extractOpenAIResponse(resp, config.ContentMaxLength)
		}
	}

	w.diagnyx.Track(call)

	return resp, err
}

// CreateEmbeddings creates embeddings and tracks the call
func (w *OpenAIWrapper) CreateEmbeddings(ctx context.Context, req openai.EmbeddingRequest) (openai.EmbeddingResponse, error) {
	start := time.Now()

	resp, err := w.client.CreateEmbeddings(ctx, req)

	latencyMs := time.Since(start).Milliseconds()

	call := LLMCall{
		Provider:       ProviderOpenAI,
		Model:          fmt.Sprintf("%v", req.Model),
		Endpoint:       "/v1/embeddings",
		LatencyMs:      latencyMs,
		ProjectID:      w.opts.ProjectID,
		Environment:    w.opts.Environment,
		UserIdentifier: w.opts.UserIdentifier,
		TraceID:        w.opts.TraceID,
		SpanID:         w.opts.SpanID,
		Metadata:       w.opts.Metadata,
		Timestamp:      time.Now().UTC(),
	}

	if err != nil {
		call.Status = StatusError
		call.ErrorMessage = err.Error()
		call.InputTokens = 0
		call.OutputTokens = 0
	} else {
		call.Status = StatusSuccess
		call.InputTokens = resp.Usage.PromptTokens
		call.OutputTokens = 0
	}

	w.diagnyx.Track(call)

	return resp, err
}

// Underlying returns the underlying OpenAI client for direct access
func (w *OpenAIWrapper) Underlying() *openai.Client {
	return w.client
}

// TrackCall is a helper to manually track any LLM call
func TrackCall(diagnyx *Client, provider Provider, model string, fn func() (inputTokens, outputTokens int, err error), opts ...TrackOptions) error {
	var trackOpts TrackOptions
	if len(opts) > 0 {
		trackOpts = opts[0]
	}

	start := time.Now()
	inputTokens, outputTokens, err := fn()
	latencyMs := time.Since(start).Milliseconds()

	call := LLMCall{
		Provider:       provider,
		Model:          model,
		InputTokens:    inputTokens,
		OutputTokens:   outputTokens,
		LatencyMs:      latencyMs,
		ProjectID:      trackOpts.ProjectID,
		Environment:    trackOpts.Environment,
		UserIdentifier: trackOpts.UserIdentifier,
		TraceID:        trackOpts.TraceID,
		SpanID:         trackOpts.SpanID,
		Metadata:       trackOpts.Metadata,
		Timestamp:      time.Now().UTC(),
		FullPrompt:     trackOpts.FullPrompt,
		FullResponse:   trackOpts.FullResponse,
	}

	if err != nil {
		call.Status = StatusError
		call.ErrorMessage = err.Error()
	} else {
		call.Status = StatusSuccess
	}

	diagnyx.Track(call)

	return err
}

// TrackCallWithContent is a helper to track any LLM call with full content capture
// Use this for providers without dedicated wrappers (like Anthropic in Go)
func TrackCallWithContent(
	diagnyx *Client,
	provider Provider,
	model string,
	prompt string,
	response string,
	inputTokens int,
	outputTokens int,
	latencyMs int64,
	opts ...TrackOptions,
) {
	var trackOpts TrackOptions
	if len(opts) > 0 {
		trackOpts = opts[0]
	}

	config := diagnyx.Config()
	fullPrompt := ""
	fullResponse := ""

	if config.CaptureFullContent {
		fullPrompt = truncateContent(prompt, config.ContentMaxLength)
		fullResponse = truncateContent(response, config.ContentMaxLength)
	}

	call := LLMCall{
		Provider:       provider,
		Model:          model,
		InputTokens:    inputTokens,
		OutputTokens:   outputTokens,
		LatencyMs:      latencyMs,
		Status:         StatusSuccess,
		ProjectID:      trackOpts.ProjectID,
		Environment:    trackOpts.Environment,
		UserIdentifier: trackOpts.UserIdentifier,
		TraceID:        trackOpts.TraceID,
		SpanID:         trackOpts.SpanID,
		Metadata:       trackOpts.Metadata,
		Timestamp:      time.Now().UTC(),
		FullPrompt:     fullPrompt,
		FullResponse:   fullResponse,
	}

	diagnyx.Track(call)
}
