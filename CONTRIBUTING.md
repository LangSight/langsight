# Contributing to LangSight

Thanks for your interest in contributing! This guide covers everything you need.

## Quick Start

```bash
git clone https://github.com/sumankalyan123/langsight
cd langsight
uv sync --dev          # install all dependencies
uv run pytest          # run tests (957 should pass)
uv run ruff check src/ # lint
```

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Docker (for integration tests)
- Node.js 20+ (for dashboard development)

### Backend (Python)

```bash
uv sync --dev                    # install dependencies
uv run pytest                    # unit + regression tests
uv run pytest -m integration     # integration tests (requires Docker)
uv run ruff check src/           # lint
uv run ruff format src/          # format
uv run mypy src/                 # type check
```

### Dashboard (Next.js)

```bash
cd dashboard
npm ci                           # install dependencies
npm run dev                      # start dev server on port 3002
npx tsc --noEmit                 # type check
```

### Full Stack (Docker)

```bash
./scripts/quickstart.sh          # generates .env, starts everything
# API: http://localhost:8000
# Dashboard: http://localhost:3003
```

## Project Structure

```
src/langsight/
  api/          # FastAPI routes, middleware, auth
  cli/          # Click CLI commands
  health/       # MCP health checker
  security/     # OWASP, CVE, poisoning scanner
  alerts/       # Alert engine + Slack/webhook delivery
  storage/      # Postgres, ClickHouse, DualStorage
  sdk/          # Python SDK (LangSightClient, MCPClientProxy)
  integrations/ # Framework adapters (LangChain, OpenAI, Anthropic, etc.)

dashboard/      # Next.js 15 dashboard
docs-site/      # Mintlify documentation
tests/
  unit/         # Fast, no external deps
  integration/  # Requires Docker (postgres + clickhouse)
  security/     # Adversarial tests
```

## Making Changes

### 1. Create a branch

```bash
git checkout -b feature/your-feature   # or fix/issue-number
```

### 2. Write code

- Type hints on every function
- Use `structlog` for logging (not `print()`)
- Use `async`/`await` for all I/O
- Follow existing patterns — read a similar file first

### 3. Write tests

Every change needs tests. Match the test file to the source:

| Source | Test |
|--------|------|
| `src/langsight/health/checker.py` | `tests/unit/health/test_checker.py` |
| `src/langsight/api/routers/agents.py` | `tests/unit/api/test_agents.py` |

### 4. Lint and type check

```bash
uv run ruff check src/ tests/
uv run mypy src/ --no-error-summary
```

### 5. Commit

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(health): add schema drift detection
fix(auth): reject expired API keys
test(sdk): add OpenAI Agents integration tests
docs: update quickstart guide
```

### 6. Open a PR

- Keep PRs focused — one feature or fix per PR
- Describe what changed and why
- All CI checks must pass

## Code Style

- **Python**: Ruff for linting + formatting, mypy for types
- **TypeScript**: strict mode, no `any`
- **SQL**: Parameterized queries only — never f-strings
- **Logging**: Structured (`logger.info("event.name", key=value)`)
- **Errors**: Explicit handling, never `except: pass`

## Architecture

Key design principles:

1. **Fail-open SDK** — Tracing never crashes the host application
2. **Dual storage** — Postgres for metadata, ClickHouse for analytics
3. **Async-first** — No blocking I/O in async context
4. **Protocol-based storage** — `StorageBackend` protocol, not inheritance
5. **Project-scoped isolation** — Multi-tenant data separation

Read `docs/02-architecture-design.md` for details.

## Getting Help

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- For security vulnerabilities, see `SECURITY.md`

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
