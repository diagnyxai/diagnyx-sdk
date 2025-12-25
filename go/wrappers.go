package diagnyx

import (
	"context"
	"fmt"
	"time"

	"github.com/sashabaranov/go-openai"
)

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
