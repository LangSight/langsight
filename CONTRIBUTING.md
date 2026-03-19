# Contributing to LangSight

Thank you for your interest in contributing to LangSight! This document covers the essentials for getting started.

## Getting Started

```bash
# Clone and install
git clone https://github.com/sumankalyan123/langsight.git
cd langsight
uv sync --dev

# Start infrastructure (required for integration tests)
docker compose up -d

# Run unit tests (no Docker needed)
uv run pytest tests/unit/ --no-cov

# Run all tests
uv run pytest --cov=langsight --cov-report=term-missing

# Lint and format
uv run ruff check src/ && uv run ruff format src/
```

## Development Workflow

1. **Fork and branch** — create a feature branch from `main` (`feature/your-feature` or `fix/your-fix`)
2. **Write code** — follow the conventions in [CLAUDE.md](CLAUDE.md)
3. **Write tests** — every new module needs a corresponding test file
4. **Run checks** — `uv run pytest`, `uv run ruff check src/`, `uv run mypy src/`
5. **Commit** — use [Conventional Commits](https://www.conventionalcommits.org/): `feat(health): add schema drift detection`
6. **Open a PR** — one feature/fix per PR, include test evidence

## Code Standards

- **Python 3.11+** with type hints on all functions
- **Async first** — all I/O operations must be async
- **Pydantic models** for all domain objects
- **Structured logging** via `structlog` (no f-string logs)
- **No hardcoded secrets** — ever, including in tests
- **Parameterized SQL** — no string concatenation in queries

See [CLAUDE.md](CLAUDE.md) for the full engineering standards.

## Test Requirements

- Unit tests: mock all I/O, no external dependencies
- Integration tests: require `docker compose up -d`, marked `@pytest.mark.integration`
- Coverage target: 80% overall, 90% for core modules (health, security, alerts)
- Every public function needs at least one happy-path and one error-path test

## What to Contribute

Good first issues are labeled `good-first-issue` on GitHub. High-impact areas:

- **OWASP MCP checks** — 5 of 10 are implemented; MCP-03, 07, 08, 09, 10 need writing
- **Framework integrations** — adapters for additional agent frameworks
- **Dashboard improvements** — the settings page needs decomposition
- **Documentation** — Mintlify docs at `docs-site/`, API docs, tutorials

## Code of Conduct

Be respectful, constructive, and inclusive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## License

By contributing, you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).
