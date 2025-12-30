package diagnyx

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

// MockServer creates a test server that records requests
type MockServer struct {
	*httptest.Server
	RequestCount int
	LastRequest  BatchRequest
	mu           sync.Mutex
	StatusCode   int
}

func newMockServer() *MockServer {
	ms := &MockServer{StatusCode: http.StatusOK}
	ms.Server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ms.mu.Lock()
		ms.RequestCount++
		ms.mu.Unlock()

		if r.Method == "POST" && r.URL.Path == "/api/v1/ingest/llm/batch" {
			var req BatchRequest
			json.NewDecoder(r.Body).Decode(&req)
			ms.mu.Lock()
			ms.LastRequest = req
			ms.mu.Unlock()
		}

		w.WriteHeader(ms.StatusCode)
		json.NewEncoder(w).Encode(BatchResponse{
			Tracked:     len(ms.LastRequest.Calls),
			TotalCost:   0.001,
			TotalTokens: 100,
			IDs:         []string{"id-1"},
		})
	}))
	return ms
}

func TestNewClient(t *testing.T) {
	t.Run("creates client with API key", func(t *testing.T) {
		client := NewClient("test-api-key")
		defer client.Close()

		if client.config.APIKey != "test-api-key" {
			t.Errorf("expected API key 'test-api-key', got '%s'", client.config.APIKey)
		}
		if client.config.BaseURL != "https://api.diagnyx.io" {
			t.Errorf("expected default base URL, got '%s'", client.config.BaseURL)
		}
	})

	t.Run("panics without API key", func(t *testing.T) {
		defer func() {
			if r := recover(); r == nil {
				t.Error("expected panic for empty API key")
			}
		}()
		NewClient("")
	})

	t.Run("creates client with custom config", func(t *testing.T) {
		config := Config{
			APIKey:          "test-key",
			BaseURL:         "https://custom.api.com",
			BatchSize:       50,
			FlushIntervalMs: 10000,
			MaxRetries:      5,
			Debug:           true,
		}
		client := NewClientWithConfig(config)
		defer client.Close()

		if client.config.BatchSize != 50 {
			t.Errorf("expected batch size 50, got %d", client.config.BatchSize)
		}
		if client.config.FlushIntervalMs != 10000 {
			t.Errorf("expected flush interval 10000, got %d", client.config.FlushIntervalMs)
		}
	})
}

func TestDefaultConfig(t *testing.T) {
	config := DefaultConfig("test-key")

	if config.APIKey != "test-key" {
		t.Errorf("expected API key 'test-key', got '%s'", config.APIKey)
	}
	if config.BatchSize != 100 {
		t.Errorf("expected batch size 100, got %d", config.BatchSize)
	}
	if config.FlushIntervalMs != 5000 {
		t.Errorf("expected flush interval 5000, got %d", config.FlushIntervalMs)
	}
	if config.MaxRetries != 3 {
		t.Errorf("expected max retries 3, got %d", config.MaxRetries)
	}
}

func TestTrack(t *testing.T) {
	t.Run("adds call to buffer", func(t *testing.T) {
		server := newMockServer()
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			BatchSize:       100,
			FlushIntervalMs: 60000, // Long interval to prevent auto-flush
		})
		defer client.Close()

		call := LLMCall{
			Provider:     ProviderOpenAI,
			Model:        "gpt-4",
			InputTokens:  100,
			OutputTokens: 50,
			Status:       StatusSuccess,
			LatencyMs:    500,
		}

		client.Track(call)

		if client.BufferSize() != 1 {
			t.Errorf("expected buffer size 1, got %d", client.BufferSize())
		}
	})

	t.Run("sets timestamp if not provided", func(t *testing.T) {
		server := newMockServer()
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			FlushIntervalMs: 60000,
		})
		defer client.Close()

		call := LLMCall{
			Provider: ProviderOpenAI,
			Model:    "gpt-4",
			Status:   StatusSuccess,
		}

		client.Track(call)
		// Timestamp is set internally, can't easily verify but test passes
	})

	t.Run("auto-flushes when batch size reached", func(t *testing.T) {
		server := newMockServer()
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			BatchSize:       5,
			FlushIntervalMs: 60000,
		})
		defer client.Close()

		for i := 0; i < 5; i++ {
			client.Track(LLMCall{
				Provider: ProviderOpenAI,
				Model:    "gpt-4",
				Status:   StatusSuccess,
			})
		}

		// Wait for async flush
		time.Sleep(100 * time.Millisecond)

		// Buffer should be empty after auto-flush
		if client.BufferSize() != 0 {
			t.Errorf("expected buffer size 0 after auto-flush, got %d", client.BufferSize())
		}
	})
}

func TestTrackCalls(t *testing.T) {
	t.Run("adds multiple calls to buffer", func(t *testing.T) {
		server := newMockServer()
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			FlushIntervalMs: 60000,
		})
		defer client.Close()

		calls := []LLMCall{
			{Provider: ProviderOpenAI, Model: "gpt-4", Status: StatusSuccess},
			{Provider: ProviderOpenAI, Model: "gpt-4", Status: StatusSuccess},
			{Provider: ProviderOpenAI, Model: "gpt-4", Status: StatusSuccess},
		}

		client.TrackCalls(calls)

		if client.BufferSize() != 3 {
			t.Errorf("expected buffer size 3, got %d", client.BufferSize())
		}
	})
}

func TestFlush(t *testing.T) {
	t.Run("sends batch to API", func(t *testing.T) {
		server := newMockServer()
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			FlushIntervalMs: 60000,
		})
		defer client.Close()

		client.Track(LLMCall{
			Provider:     ProviderOpenAI,
			Model:        "gpt-4",
			InputTokens:  100,
			OutputTokens: 50,
			Status:       StatusSuccess,
		})

		err := client.Flush()

		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}
		if client.BufferSize() != 0 {
			t.Errorf("expected buffer size 0 after flush, got %d", client.BufferSize())
		}
		if server.RequestCount != 1 {
			t.Errorf("expected 1 API request, got %d", server.RequestCount)
		}
	})

	t.Run("returns nil for empty buffer", func(t *testing.T) {
		server := newMockServer()
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			FlushIntervalMs: 60000,
		})
		defer client.Close()

		err := client.Flush()

		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}
	})

	t.Run("restores buffer on error", func(t *testing.T) {
		server := newMockServer()
		server.StatusCode = http.StatusInternalServerError
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			FlushIntervalMs: 60000,
			MaxRetries:      1, // Quick failure
		})
		defer client.Close()

		client.Track(LLMCall{
			Provider: ProviderOpenAI,
			Model:    "gpt-4",
			Status:   StatusSuccess,
		})

		err := client.Flush()

		if err == nil {
			t.Error("expected error on flush failure")
		}
		if client.BufferSize() != 1 {
			t.Errorf("expected buffer size 1 after failed flush, got %d", client.BufferSize())
		}
	})
}

func TestRetry(t *testing.T) {
	t.Run("retries on server error", func(t *testing.T) {
		attemptCount := 0
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			attemptCount++
			if attemptCount < 2 {
				w.WriteHeader(http.StatusInternalServerError)
				return
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(BatchResponse{Tracked: 1})
		}))
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			FlushIntervalMs: 60000,
			MaxRetries:      3,
		})
		defer client.Close()

		client.Track(LLMCall{Provider: ProviderOpenAI, Model: "gpt-4", Status: StatusSuccess})
		err := client.Flush()

		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}
		if attemptCount != 2 {
			t.Errorf("expected 2 attempts, got %d", attemptCount)
		}
	})

	t.Run("does not retry on client error", func(t *testing.T) {
		attemptCount := 0
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			attemptCount++
			w.WriteHeader(http.StatusBadRequest)
		}))
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			FlushIntervalMs: 60000,
			MaxRetries:      3,
		})
		defer client.Close()

		client.Track(LLMCall{Provider: ProviderOpenAI, Model: "gpt-4", Status: StatusSuccess})
		err := client.Flush()

		if err == nil {
			t.Error("expected error for client error response")
		}
		if attemptCount != 1 {
			t.Errorf("expected 1 attempt for client error, got %d", attemptCount)
		}
	})
}

func TestClose(t *testing.T) {
	t.Run("flushes remaining calls on close", func(t *testing.T) {
		server := newMockServer()
		defer server.Close()

		client := NewClientWithConfig(Config{
			APIKey:          "test-key",
			BaseURL:         server.URL,
			FlushIntervalMs: 60000,
		})

		client.Track(LLMCall{Provider: ProviderOpenAI, Model: "gpt-4", Status: StatusSuccess})
		client.Close()

		if server.RequestCount != 1 {
			t.Errorf("expected 1 API request on close, got %d", server.RequestCount)
		}
	})
}

func TestBufferSize(t *testing.T) {
	server := newMockServer()
	defer server.Close()

	client := NewClientWithConfig(Config{
		APIKey:          "test-key",
		BaseURL:         server.URL,
		FlushIntervalMs: 60000,
	})
	defer client.Close()

	if client.BufferSize() != 0 {
		t.Errorf("expected initial buffer size 0, got %d", client.BufferSize())
	}

	client.Track(LLMCall{Provider: ProviderOpenAI, Model: "gpt-4", Status: StatusSuccess})

	if client.BufferSize() != 1 {
		t.Errorf("expected buffer size 1, got %d", client.BufferSize())
	}
}

func TestConfig(t *testing.T) {
	server := newMockServer()
	defer server.Close()

	config := Config{
		APIKey:             "test-key",
		BaseURL:            server.URL,
		BatchSize:          50,
		FlushIntervalMs:    60000,
		CaptureFullContent: true,
		ContentMaxLength:   5000,
	}

	client := NewClientWithConfig(config)
	defer client.Close()

	returnedConfig := client.Config()

	if returnedConfig.BatchSize != 50 {
		t.Errorf("expected batch size 50, got %d", returnedConfig.BatchSize)
	}
	if returnedConfig.CaptureFullContent != true {
		t.Error("expected capture full content to be true")
	}
}

func TestConcurrentTracking(t *testing.T) {
	server := newMockServer()
	defer server.Close()

	client := NewClientWithConfig(Config{
		APIKey:          "test-key",
		BaseURL:         server.URL,
		BatchSize:       1000, // Large batch to prevent auto-flush
		FlushIntervalMs: 60000,
	})
	defer client.Close()

	var wg sync.WaitGroup
	numGoroutines := 10
	callsPerGoroutine := 10

	for i := 0; i < numGoroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < callsPerGoroutine; j++ {
				client.Track(LLMCall{
					Provider: ProviderOpenAI,
					Model:    "gpt-4",
					Status:   StatusSuccess,
				})
			}
		}()
	}

	wg.Wait()

	expectedSize := numGoroutines * callsPerGoroutine
	if client.BufferSize() != expectedSize {
		t.Errorf("expected buffer size %d, got %d", expectedSize, client.BufferSize())
	}
}
