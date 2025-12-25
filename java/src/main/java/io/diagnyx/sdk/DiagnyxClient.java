package io.diagnyx.sdk;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.io.Closeable;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Diagnyx client for tracking LLM API calls.
 */
public class DiagnyxClient implements Closeable {
    private final DiagnyxConfig config;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final List<LLMCall> buffer;
    private final ScheduledExecutorService scheduler;
    private final AtomicBoolean isFlushing;
    private volatile boolean closed = false;

    /**
     * Creates a new DiagnyxClient with the given API key.
     */
    public static DiagnyxClient create(String apiKey) {
        return new DiagnyxClient(new DiagnyxConfig(apiKey));
    }

    /**
     * Creates a new DiagnyxClient with custom configuration.
     */
    public static DiagnyxClient create(DiagnyxConfig config) {
        return new DiagnyxClient(config);
    }

    private DiagnyxClient(DiagnyxConfig config) {
        this.config = config;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(30))
                .build();
        this.objectMapper = new ObjectMapper();
        this.objectMapper.registerModule(new JavaTimeModule());
        this.buffer = new ArrayList<>();
        this.scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "diagnyx-flush");
            t.setDaemon(true);
            return t;
        });
        this.isFlushing = new AtomicBoolean(false);

        startFlushTimer();
    }

    /**
     * Track a single LLM call.
     */
    public void track(LLMCall call) {
        if (closed) {
            throw new IllegalStateException("Client is closed");
        }

        if (call.getTimestamp() == null) {
            call.setTimestamp(Instant.now());
        }

        boolean shouldFlush;
        synchronized (buffer) {
            buffer.add(call);
            shouldFlush = buffer.size() >= config.getBatchSize();
        }

        if (shouldFlush) {
            flushAsync();
        }
    }

    /**
     * Track multiple LLM calls.
     */
    public void trackAll(List<LLMCall> calls) {
        if (closed) {
            throw new IllegalStateException("Client is closed");
        }

        Instant now = Instant.now();
        for (LLMCall call : calls) {
            if (call.getTimestamp() == null) {
                call.setTimestamp(now);
            }
        }

        boolean shouldFlush;
        synchronized (buffer) {
            buffer.addAll(calls);
            shouldFlush = buffer.size() >= config.getBatchSize();
        }

        if (shouldFlush) {
            flushAsync();
        }
    }

    /**
     * Flush the buffer asynchronously.
     */
    public CompletableFuture<Void> flushAsync() {
        return CompletableFuture.runAsync(this::flush);
    }

    /**
     * Flush the buffer synchronously.
     */
    public void flush() {
        if (!isFlushing.compareAndSet(false, true)) {
            return;
        }

        try {
            List<LLMCall> calls;
            synchronized (buffer) {
                if (buffer.isEmpty()) {
                    return;
                }
                calls = new ArrayList<>(buffer);
                buffer.clear();
            }

            try {
                sendBatch(calls);
                log("Flushed %d calls", calls.size());
            } catch (Exception e) {
                // On error, put calls back in buffer
                synchronized (buffer) {
                    calls.addAll(buffer);
                    buffer.clear();
                    buffer.addAll(calls);
                }
                log("Flush failed: %s", e.getMessage());
            }
        } finally {
            isFlushing.set(false);
        }
    }

    /**
     * Get the current buffer size.
     */
    public int getBufferSize() {
        synchronized (buffer) {
            return buffer.size();
        }
    }

    /**
     * Close the client and flush remaining calls.
     */
    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;

        scheduler.shutdown();
        try {
            scheduler.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        flush();
    }

    private void startFlushTimer() {
        scheduler.scheduleAtFixedRate(() -> {
            if (getBufferSize() > 0) {
                try {
                    flush();
                } catch (Exception e) {
                    log("Background flush error: %s", e.getMessage());
                }
            }
        }, config.getFlushIntervalMs(), config.getFlushIntervalMs(), TimeUnit.MILLISECONDS);
    }

    private void sendBatch(List<LLMCall> calls) throws Exception {
        Map<String, Object> payload = Map.of("calls", calls);
        String body = objectMapper.writeValueAsString(payload);

        Exception lastError = null;
        for (int attempt = 0; attempt < config.getMaxRetries(); attempt++) {
            try {
                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(config.getBaseUrl() + "/api/v1/ingest/llm/batch"))
                        .header("Content-Type", "application/json")
                        .header("Authorization", "Bearer " + config.getApiKey())
                        .POST(HttpRequest.BodyPublishers.ofString(body))
                        .build();

                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

                if (response.statusCode() >= 200 && response.statusCode() < 300) {
                    return;
                }

                lastError = new RuntimeException("HTTP " + response.statusCode());
                log("Attempt %d failed: %s", attempt + 1, lastError.getMessage());

                if (response.statusCode() >= 400 && response.statusCode() < 500) {
                    throw lastError;
                }

                Thread.sleep((long) Math.pow(2, attempt) * 1000);

            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw e;
            } catch (Exception e) {
                lastError = e;
                log("Attempt %d failed: %s", attempt + 1, e.getMessage());
                if (attempt < config.getMaxRetries() - 1) {
                    Thread.sleep((long) Math.pow(2, attempt) * 1000);
                }
            }
        }

        throw lastError != null ? lastError : new RuntimeException("Failed to send batch");
    }

    private void log(String format, Object... args) {
        if (config.isDebug()) {
            System.out.printf("[Diagnyx] " + format + "%n", args);
        }
    }
}
