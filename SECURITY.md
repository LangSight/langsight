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
- **Proxy trust boundary**: X-User-* headers only trusted from configurable CIDR ranges

### Data Protection

- Passwords are bcrypt-hashed (never stored in plaintext)
- API keys are SHA-256 hashed (raw key shown once at creation, never stored)
- Audit log records all admin mutations with actor identity and IP
- PII is never logged via structlog

### Known Limitations (Alpha)

- No SSO/OIDC support yet (password-only authentication)
- No encryption at rest for ClickHouse data
- Rate limiting is IP-based (with X-Forwarded-For support for proxy deployments)
- 5 of 10 OWASP MCP checks are implemented

## Dependency Security

- Dependencies are pinned in `pyproject.toml`
- CVE scanning uses the OSV (Open Source Vulnerabilities) database
- Run `uv audit` to check for known vulnerabilities
