# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Repository Info

**GitHub**: `diagnyxai/diagnyx-sdk` (https://github.com/diagnyxai/diagnyx-sdk)

**Git Access**: Uses `github-diagnyx` SSH host alias (see `repos/CLAUDE.md` for full GitHub config)

> **IMPORTANT: ALWAYS switch to `diagnyxadmin` before ANY GitHub operations (push, PR, etc.)!**

```bash
gh auth switch -u diagnyxadmin
```

---

## Repository Structure

This is a monorepo containing Diagnyx SDKs for multiple languages:

```
diagnyx-sdk/
├── node/       # @diagnyx/node (TypeScript/JavaScript)
├── python/     # diagnyx (Python)
├── go/         # github.com/diagnyxai/diagnyx-go
├── java/       # io.diagnyx:diagnyx-sdk (Maven)
└── rust/       # diagnyx (Cargo)
```

## Build & Test Commands

### Node.js
```bash
cd node
npm install
npm run build
npm test
```

### Python
```bash
cd python
pip install -e .
pytest
```

### Go
```bash
cd go
go build ./...
go test ./...
```

### Java
```bash
cd java
mvn compile
mvn test
```

### Rust
```bash
cd rust
cargo build
cargo test
```

## SDK Architecture

All SDKs follow the same core architecture:

1. **Client** - Main class that handles configuration, buffering, and HTTP calls
2. **Types** - LLMCall, Provider, CallStatus, Config types
3. **Wrappers** - Optional wrappers for OpenAI/Anthropic clients
4. **Batching** - Automatic batching with configurable size and interval
5. **Retry** - Exponential backoff retry logic

## Common Patterns

### Client Initialization
```
Client(apiKey, config?) → starts background flush timer
```

### Tracking
```
client.track(call) → adds to buffer → flushes if batch size reached
```

### Flush
```
client.flush() → sends buffer to /api/v1/ingest/llm/batch → clears buffer
```

### Shutdown
```
client.close() → stops timer → final flush
```

## API Endpoint

All SDKs send data to:
```
POST {baseUrl}/api/v1/ingest/llm/batch
Authorization: Bearer {apiKey}
Content-Type: application/json

{
  "calls": [LLMCall, ...]
}
```

## Adding a New SDK

1. Create new directory: `{language}/`
2. Implement core client with batching and retry
3. Add types matching the LLMCall schema
4. Add optional provider wrappers
5. Write README with usage examples
6. Add tests
7. Update root README.md

## Versioning

All SDKs should maintain version parity when possible:
- Current version: `0.1.0`
- Use semantic versioning
