package diagnyx

import "time"

// Provider represents an LLM provider
type Provider string

const (
	ProviderOpenAI    Provider = "openai"
	ProviderAnthropic Provider = "anthropic"
	ProviderGoogle    Provider = "google"
	ProviderAzure     Provider = "azure"
	ProviderAWS       Provider = "aws"
	ProviderCustom    Provider = "custom"
)

// CallStatus represents the status of an LLM call
type CallStatus string

const (
	StatusSuccess     CallStatus = "success"
	StatusError       CallStatus = "error"
	StatusTimeout     CallStatus = "timeout"
	StatusRateLimited CallStatus = "rate_limited"
)

// Config holds the configuration for the Diagnyx client
type Config struct {
	APIKey          string
	BaseURL         string
	BatchSize       int
	FlushIntervalMs int
	MaxRetries      int
	Debug           bool
}

// DefaultConfig returns a Config with default values
func DefaultConfig(apiKey string) Config {
	return Config{
		APIKey:          apiKey,
		BaseURL:         "https://api.diagnyx.io",
		BatchSize:       100,
		FlushIntervalMs: 5000,
		MaxRetries:      3,
		Debug:           false,
	}
}

// LLMCall represents a single LLM API call
type LLMCall struct {
	Provider       Provider   `json:"provider"`
	Model          string     `json:"model"`
	Endpoint       string     `json:"endpoint,omitempty"`
	InputTokens    int        `json:"input_tokens"`
	OutputTokens   int        `json:"output_tokens"`
	LatencyMs      int64      `json:"latency_ms"`
	TTFTMs         *int64     `json:"ttft_ms,omitempty"`
	Status         CallStatus `json:"status"`
	ErrorCode      string     `json:"error_code,omitempty"`
	ErrorMessage   string     `json:"error_message,omitempty"`
	ProjectID      string     `json:"project_id,omitempty"`
	Environment    string     `json:"environment,omitempty"`
	UserIdentifier string     `json:"user_identifier,omitempty"`
	TraceID        string     `json:"trace_id,omitempty"`
	SpanID         string     `json:"span_id,omitempty"`
	Metadata       map[string]interface{} `json:"metadata,omitempty"`
	Timestamp      time.Time  `json:"timestamp"`
}

// BatchRequest is the request body for batch ingestion
type BatchRequest struct {
	Calls []LLMCall `json:"calls"`
}

// BatchResponse is the response from batch ingestion
type BatchResponse struct {
	Tracked     int      `json:"tracked"`
	TotalCost   float64  `json:"total_cost"`
	TotalTokens int      `json:"total_tokens"`
	IDs         []string `json:"ids"`
}

// TrackOptions provides optional parameters for tracking
type TrackOptions struct {
	ProjectID      string
	Environment    string
	UserIdentifier string
	TraceID        string
	SpanID         string
	Metadata       map[string]interface{}
}
