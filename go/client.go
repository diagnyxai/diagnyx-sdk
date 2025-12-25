package diagnyx

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"
)

// Client is the Diagnyx client for tracking LLM calls
type Client struct {
	config      Config
	httpClient  *http.Client
	buffer      []LLMCall
	bufferMu    sync.Mutex
	flushTicker *time.Ticker
	done        chan struct{}
	wg          sync.WaitGroup
}

// NewClient creates a new Diagnyx client
func NewClient(apiKey string) *Client {
	return NewClientWithConfig(DefaultConfig(apiKey))
}

// NewClientWithConfig creates a new Diagnyx client with custom configuration
func NewClientWithConfig(config Config) *Client {
	if config.APIKey == "" {
		panic("diagnyx: api_key is required")
	}
	if config.BaseURL == "" {
		config.BaseURL = "https://api.diagnyx.io"
	}
	if config.BatchSize == 0 {
		config.BatchSize = 100
	}
	if config.FlushIntervalMs == 0 {
		config.FlushIntervalMs = 5000
	}
	if config.MaxRetries == 0 {
		config.MaxRetries = 3
	}

	c := &Client{
		config: config,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		buffer: make([]LLMCall, 0, config.BatchSize),
		done:   make(chan struct{}),
	}

	c.startFlushTimer()
	return c
}

// Track records a single LLM call
func (c *Client) Track(call LLMCall) {
	if call.Timestamp.IsZero() {
		call.Timestamp = time.Now().UTC()
	}

	c.bufferMu.Lock()
	c.buffer = append(c.buffer, call)
	shouldFlush := len(c.buffer) >= c.config.BatchSize
	c.bufferMu.Unlock()

	if shouldFlush {
		go c.Flush()
	}
}

// TrackCalls records multiple LLM calls
func (c *Client) TrackCalls(calls []LLMCall) {
	now := time.Now().UTC()
	for i := range calls {
		if calls[i].Timestamp.IsZero() {
			calls[i].Timestamp = now
		}
	}

	c.bufferMu.Lock()
	c.buffer = append(c.buffer, calls...)
	shouldFlush := len(c.buffer) >= c.config.BatchSize
	c.bufferMu.Unlock()

	if shouldFlush {
		go c.Flush()
	}
}

// Flush sends all buffered calls to the API
func (c *Client) Flush() error {
	c.bufferMu.Lock()
	if len(c.buffer) == 0 {
		c.bufferMu.Unlock()
		return nil
	}
	calls := make([]LLMCall, len(c.buffer))
	copy(calls, c.buffer)
	c.buffer = c.buffer[:0]
	c.bufferMu.Unlock()

	err := c.sendBatch(calls)
	if err != nil {
		// On error, put calls back in buffer
		c.bufferMu.Lock()
		c.buffer = append(calls, c.buffer...)
		c.bufferMu.Unlock()
		c.log("Flush failed: %v", err)
		return err
	}

	c.log("Flushed %d calls", len(calls))
	return nil
}

// BufferSize returns the current number of buffered calls
func (c *Client) BufferSize() int {
	c.bufferMu.Lock()
	defer c.bufferMu.Unlock()
	return len(c.buffer)
}

// Close shuts down the client and flushes remaining calls
func (c *Client) Close() error {
	close(c.done)
	if c.flushTicker != nil {
		c.flushTicker.Stop()
	}
	c.wg.Wait()
	return c.Flush()
}

func (c *Client) startFlushTimer() {
	c.flushTicker = time.NewTicker(time.Duration(c.config.FlushIntervalMs) * time.Millisecond)
	c.wg.Add(1)

	go func() {
		defer c.wg.Done()
		for {
			select {
			case <-c.flushTicker.C:
				if c.BufferSize() > 0 {
					if err := c.Flush(); err != nil {
						c.log("Background flush error: %v", err)
					}
				}
			case <-c.done:
				return
			}
		}
	}()
}

func (c *Client) sendBatch(calls []LLMCall) error {
	payload := BatchRequest{Calls: calls}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal payload: %w", err)
	}

	var lastErr error
	for attempt := 0; attempt < c.config.MaxRetries; attempt++ {
		req, err := http.NewRequest("POST", c.config.BaseURL+"/api/v1/ingest/llm/batch", bytes.NewReader(body))
		if err != nil {
			return fmt.Errorf("failed to create request: %w", err)
		}

		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+c.config.APIKey)

		resp, err := c.httpClient.Do(req)
		if err != nil {
			lastErr = err
			c.log("Attempt %d failed: %v", attempt+1, err)
			time.Sleep(time.Duration(1<<attempt) * time.Second)
			continue
		}

		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			resp.Body.Close()
			return nil
		}

		resp.Body.Close()
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

func (c *Client) log(format string, args ...interface{}) {
	if c.config.Debug {
		fmt.Printf("[Diagnyx] "+format+"\n", args...)
	}
}
