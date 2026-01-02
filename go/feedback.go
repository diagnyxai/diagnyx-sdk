package diagnyx

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"
)

// FeedbackType represents the type of feedback
type FeedbackType string

const (
	FeedbackTypeThumbsUp   FeedbackType = "thumbs_up"
	FeedbackTypeThumbsDown FeedbackType = "thumbs_down"
	FeedbackTypeRating     FeedbackType = "rating"
	FeedbackTypeText       FeedbackType = "text"
	FeedbackTypeCorrection FeedbackType = "correction"
	FeedbackTypeFlag       FeedbackType = "flag"
)

// FeedbackSentiment represents the sentiment classification
type FeedbackSentiment string

const (
	FeedbackSentimentPositive FeedbackSentiment = "positive"
	FeedbackSentimentNegative FeedbackSentiment = "negative"
	FeedbackSentimentNeutral  FeedbackSentiment = "neutral"
)

// FeedbackOptions contains optional parameters for feedback submission
type FeedbackOptions struct {
	// Optional span ID for specific span feedback
	SpanID string
	// Optional text comment
	Comment string
	// Tags for categorization
	Tags []string
	// Additional metadata
	Metadata map[string]interface{}
	// Anonymized user identifier
	UserID string
	// Session identifier
	SessionID string
}

// Feedback represents a feedback record
type Feedback struct {
	ID           string                 `json:"id"`
	TraceID      string                 `json:"traceId"`
	FeedbackType FeedbackType           `json:"feedbackType"`
	Sentiment    FeedbackSentiment      `json:"sentiment"`
	Rating       *int                   `json:"rating,omitempty"`
	Comment      string                 `json:"comment,omitempty"`
	Correction   string                 `json:"correction,omitempty"`
	Tags         []string               `json:"tags"`
	Metadata     map[string]interface{} `json:"metadata"`
	UserID       string                 `json:"userId,omitempty"`
	SessionID    string                 `json:"sessionId,omitempty"`
	SpanID       string                 `json:"spanId,omitempty"`
	CreatedAt    time.Time              `json:"createdAt"`
}

// FeedbackSummary contains feedback analytics
type FeedbackSummary struct {
	TotalFeedback  int            `json:"totalFeedback"`
	PositiveCount  int            `json:"positiveCount"`
	NegativeCount  int            `json:"negativeCount"`
	NeutralCount   int            `json:"neutralCount"`
	PositiveRate   float64        `json:"positiveRate"`
	AverageRating  float64        `json:"averageRating"`
	FeedbackByType map[string]int `json:"feedbackByType"`
	FeedbackByTag  map[string]int `json:"feedbackByTag"`
}

// ListFeedbackOptions contains parameters for listing feedback
type ListFeedbackOptions struct {
	Limit        int
	Offset       int
	FeedbackType FeedbackType
	Sentiment    FeedbackSentiment
	Tag          string
	StartDate    *time.Time
	EndDate      *time.Time
}

// ListFeedbackResult contains the paginated feedback list
type ListFeedbackResult struct {
	Data   []Feedback `json:"data"`
	Total  int        `json:"total"`
	Limit  int        `json:"limit"`
	Offset int        `json:"offset"`
}

// FeedbackClient handles feedback operations
type FeedbackClient struct {
	apiKey         string
	baseURL        string
	organizationID string
	maxRetries     int
	debug          bool
	httpClient     *http.Client
}

// NewFeedbackClient creates a new feedback client
func NewFeedbackClient(apiKey, organizationID string, opts ...FeedbackClientOption) *FeedbackClient {
	c := &FeedbackClient{
		apiKey:         apiKey,
		baseURL:        "https://api.diagnyx.io",
		organizationID: organizationID,
		maxRetries:     3,
		debug:          false,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}

	for _, opt := range opts {
		opt(c)
	}

	return c
}

// FeedbackClientOption configures a FeedbackClient
type FeedbackClientOption func(*FeedbackClient)

// WithFeedbackBaseURL sets the base URL
func WithFeedbackBaseURL(url string) FeedbackClientOption {
	return func(c *FeedbackClient) {
		c.baseURL = url
	}
}

// WithFeedbackMaxRetries sets the max retries
func WithFeedbackMaxRetries(retries int) FeedbackClientOption {
	return func(c *FeedbackClient) {
		c.maxRetries = retries
	}
}

// WithFeedbackDebug enables debug mode
func WithFeedbackDebug(debug bool) FeedbackClientOption {
	return func(c *FeedbackClient) {
		c.debug = debug
	}
}

// ThumbsUp submits positive feedback
func (c *FeedbackClient) ThumbsUp(traceID string, opts *FeedbackOptions) (*Feedback, error) {
	return c.submit(traceID, FeedbackTypeThumbsUp, nil, "", "", opts)
}

// ThumbsDown submits negative feedback
func (c *FeedbackClient) ThumbsDown(traceID string, opts *FeedbackOptions) (*Feedback, error) {
	return c.submit(traceID, FeedbackTypeThumbsDown, nil, "", "", opts)
}

// Rating submits a numeric rating (1-5)
func (c *FeedbackClient) Rating(traceID string, value int, opts *FeedbackOptions) (*Feedback, error) {
	if value < 1 || value > 5 {
		return nil, fmt.Errorf("rating value must be between 1 and 5")
	}
	return c.submit(traceID, FeedbackTypeRating, &value, "", "", opts)
}

// Text submits text feedback
func (c *FeedbackClient) Text(traceID, comment string, opts *FeedbackOptions) (*Feedback, error) {
	return c.submit(traceID, FeedbackTypeText, nil, comment, "", opts)
}

// Correction submits a correction for fine-tuning
func (c *FeedbackClient) Correction(traceID, correction string, opts *FeedbackOptions) (*Feedback, error) {
	return c.submit(traceID, FeedbackTypeCorrection, nil, "", correction, opts)
}

// Flag flags a response for review
func (c *FeedbackClient) Flag(traceID string, reason string, opts *FeedbackOptions) (*Feedback, error) {
	return c.submit(traceID, FeedbackTypeFlag, nil, reason, "", opts)
}

func (c *FeedbackClient) submit(traceID string, feedbackType FeedbackType, rating *int, comment, correction string, opts *FeedbackOptions) (*Feedback, error) {
	if opts == nil {
		opts = &FeedbackOptions{}
	}

	payload := map[string]interface{}{
		"traceId":      traceID,
		"feedbackType": feedbackType,
	}

	if opts.SpanID != "" {
		payload["spanId"] = opts.SpanID
	}
	if rating != nil {
		payload["rating"] = *rating
	}
	if comment != "" {
		payload["comment"] = comment
	} else if opts.Comment != "" {
		payload["comment"] = opts.Comment
	}
	if correction != "" {
		payload["correction"] = correction
	}
	if len(opts.Tags) > 0 {
		payload["tags"] = opts.Tags
	}
	if opts.Metadata != nil {
		payload["metadata"] = opts.Metadata
	}
	if opts.UserID != "" {
		payload["userId"] = opts.UserID
	}
	if opts.SessionID != "" {
		payload["sessionId"] = opts.SessionID
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal payload: %w", err)
	}

	var result Feedback
	err = c.request("POST", "/api/v1/feedback", body, &result)
	if err != nil {
		return nil, err
	}

	return &result, nil
}

// List retrieves feedback with filters
func (c *FeedbackClient) List(opts *ListFeedbackOptions) (*ListFeedbackResult, error) {
	if opts == nil {
		opts = &ListFeedbackOptions{}
	}

	params := url.Values{}
	if opts.Limit > 0 {
		params.Set("limit", fmt.Sprintf("%d", opts.Limit))
	}
	if opts.Offset > 0 {
		params.Set("offset", fmt.Sprintf("%d", opts.Offset))
	}
	if opts.FeedbackType != "" {
		params.Set("feedbackType", string(opts.FeedbackType))
	}
	if opts.Sentiment != "" {
		params.Set("sentiment", string(opts.Sentiment))
	}
	if opts.Tag != "" {
		params.Set("tag", opts.Tag)
	}
	if opts.StartDate != nil {
		params.Set("startDate", opts.StartDate.Format(time.RFC3339))
	}
	if opts.EndDate != nil {
		params.Set("endDate", opts.EndDate.Format(time.RFC3339))
	}

	path := fmt.Sprintf("/api/v1/organizations/%s/feedback", c.organizationID)
	if len(params) > 0 {
		path += "?" + params.Encode()
	}

	var result ListFeedbackResult
	err := c.request("GET", path, nil, &result)
	if err != nil {
		return nil, err
	}

	return &result, nil
}

// GetSummary retrieves feedback analytics
func (c *FeedbackClient) GetSummary(startDate, endDate *time.Time) (*FeedbackSummary, error) {
	params := url.Values{}
	if startDate != nil {
		params.Set("startDate", startDate.Format(time.RFC3339))
	}
	if endDate != nil {
		params.Set("endDate", endDate.Format(time.RFC3339))
	}

	path := fmt.Sprintf("/api/v1/organizations/%s/feedback/analytics", c.organizationID)
	if len(params) > 0 {
		path += "?" + params.Encode()
	}

	var result FeedbackSummary
	err := c.request("GET", path, nil, &result)
	if err != nil {
		return nil, err
	}

	return &result, nil
}

// GetForTrace retrieves feedback for a specific trace
func (c *FeedbackClient) GetForTrace(traceID string) ([]Feedback, error) {
	path := fmt.Sprintf("/api/v1/organizations/%s/feedback/trace/%s", c.organizationID, traceID)

	var result []Feedback
	err := c.request("GET", path, nil, &result)
	if err != nil {
		return nil, err
	}

	return result, nil
}

func (c *FeedbackClient) request(method, path string, body []byte, result interface{}) error {
	var lastErr error

	for attempt := 0; attempt < c.maxRetries; attempt++ {
		req, err := http.NewRequest(method, c.baseURL+path, bytes.NewReader(body))
		if err != nil {
			return fmt.Errorf("failed to create request: %w", err)
		}

		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+c.apiKey)

		resp, err := c.httpClient.Do(req)
		if err != nil {
			lastErr = err
			c.log("Attempt %d failed: %v", attempt+1, err)
			time.Sleep(time.Duration(1<<attempt) * time.Second)
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			if result != nil {
				if err := json.NewDecoder(resp.Body).Decode(result); err != nil {
					return fmt.Errorf("failed to decode response: %w", err)
				}
			}
			return nil
		}

		lastErr = fmt.Errorf("HTTP %d", resp.StatusCode)
		c.log("Attempt %d failed: %v", attempt+1, lastErr)

		if resp.StatusCode >= 400 && resp.StatusCode < 500 {
			// Don't retry client errors
			return lastErr
		}

		time.Sleep(time.Duration(1<<attempt) * time.Second)
	}

	return lastErr
}

func (c *FeedbackClient) log(format string, args ...interface{}) {
	if c.debug {
		fmt.Printf("[Diagnyx Feedback] "+format+"\n", args...)
	}
}
