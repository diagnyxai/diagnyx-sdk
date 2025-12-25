# Contributing to Diagnyx SDKs

Thank you for your interest in contributing to Diagnyx SDKs!

## Repository Structure

```
diagnyx-sdk/
├── node/       # Node.js/TypeScript SDK
├── python/     # Python SDK
├── go/         # Go SDK
├── java/       # Java SDK
└── rust/       # Rust SDK
```

## Development Setup

### Node.js

```bash
cd node
npm install
npm test
```

### Python

```bash
cd python
pip install -e ".[dev]"
pytest
```

### Go

```bash
cd go
go test ./...
```

### Java

```bash
cd java
mvn test
```

### Rust

```bash
cd rust
cargo test
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Update documentation if needed
7. Submit a pull request

## Code Style

- **Node.js**: Follow existing ESLint configuration
- **Python**: Follow PEP 8, use Black for formatting
- **Go**: Use `gofmt`
- **Java**: Follow Google Java Style Guide
- **Rust**: Use `rustfmt`

## Reporting Issues

Please include:
- SDK language and version
- Steps to reproduce
- Expected vs actual behavior
- Error messages/stack traces

## Feature Requests

Open an issue describing:
- The problem you're trying to solve
- Proposed solution
- Any alternatives considered

## Questions?

- Open a GitHub issue
- Email: support@diagnyx.io
