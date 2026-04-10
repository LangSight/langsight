# Security Policy

LangSight monitors MCP security — it must itself be secure. We take security vulnerabilities seriously.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please report vulnerabilities through one of these channels:

1. **GitHub Security Advisories** (preferred): [Create a security advisory](https://github.com/LangSight/langsight/security/advisories/new)
2. **Email**: security@langsight.dev (if the above is not available)

### What to include

- Description of the vulnerability
- Steps to reproduce
- Affected version(s)
- Impact assessment (what can an attacker do?)
- Suggested fix, if you have one

### Response timeline

- **Acknowledgment**: within 48 hours
- **Initial assessment**: within 7 days
- **Fix timeline**: depends on severity
  - Critical: patch within 72 hours
  - High: patch within 14 days
  - Medium/Low: next release cycle

## Supported Versions

Only the **latest release** receives security fixes. We do not backport patches to older versions.

| Version | Supported |
|---------|-----------|
| 0.14.x (latest) | ✅ Yes |
| < 0.14  | ❌ No — upgrade to latest |

## Security Model

### Authentication

- **Dashboard**: NextAuth.js with bcrypt-hashed passwords and JWT sessions
- **API/SDK**: SHA-256 hashed API keys with HMAC-safe comparison
- **Proxy trust boundary**: X-User-* headers trusted only from configurable CIDR ranges AND validated via HMAC signature (when `LANGSIGHT_PROXY_SECRET` is set)
- **Project access control**: All data endpoints enforce project-level access via `get_active_project_id` — callers can only read/write data for projects they belong to

### Data Protection

- Passwords are bcrypt-hashed (never stored in plaintext)
- API keys are SHA-256 hashed (raw key shown once at creation, never stored)
- **Provider API keys** (Anthropic/OpenAI/Gemini) are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256) when `LANGSIGHT_SECRET_KEY` is set
- Audit log records all admin mutations with actor identity and IP
- PII is never logged via structlog
- **Payload redaction is fail-closed**: if the settings database is unreachable during span ingestion, payloads are redacted by default to prevent accidental PII storage

### Network Security

- **Dashboard proxy**: In production (`NODE_ENV=production`), the direct `/api/*` rewrite is disabled when `LANGSIGHT_API_KEY` is not set — all traffic must go through the authenticated `/api/proxy/*` route
- **OTEL Collector**: Bearer token auth is required; `OTEL_COLLECTOR_TOKEN` must be set in shared/production deployments
- **SSE connections**: Configurable per-worker cap (`LANGSIGHT_SSE_MAX_CLIENTS`, default: 1000) with rejection logging and backpressure
- **Session trace reads**: Concurrent ClickHouse queries capped at 5 (configurable) with 200MB per-query memory limit to prevent OOM

### Supply Chain Security

- CI pipeline includes pip-audit (Python dependency CVEs), gitleaks (secret detection), and trivy (filesystem vulnerability scanning)
- Dependencies are pinned in `pyproject.toml`

### Known Limitations

- No SSO/OIDC support yet (password-only authentication)
- No encryption at rest for ClickHouse data (spans, health checks)
- Rate limiting is IP-based (with X-Forwarded-For support for proxy deployments)
- 5 of 10 OWASP MCP checks are implemented

### Recommended Production Configuration

Set these environment variables for any deployment beyond local dev:

| Variable | Purpose |
|---|---|
| `LANGSIGHT_SECRET_KEY` | Encrypt provider API keys in Postgres |
| `LANGSIGHT_PROXY_SECRET` | HMAC-sign dashboard→API proxy headers |
| `LANGSIGHT_API_KEYS` | Enable API authentication |
| `OTEL_COLLECTOR_TOKEN` | Authenticate OTEL span ingestion |
| `AUTH_SECRET` | Sign NextAuth JWT sessions |

Generate all secrets with: `python3 -c "import secrets; print(secrets.token_hex(32))"`

## Dependency Security

- Dependencies are pinned in `pyproject.toml`
- CVE scanning via pip-audit and trivy in CI
- Run `uv audit` locally to check for known vulnerabilities
