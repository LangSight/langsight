# MCP Server Onboarding

**Date**: 2026-03-26
**Status**: Confirmed — two distinct paths

---

## The Core Distinction

`langsight init` scanning `~/.cursor/mcp.json` is a **developer convenience**.
It is not the production onboarding story.

| | Local / Dev | Production |
|---|---|---|
| **Who** | Individual developer | Platform team / DevOps |
| **MCP servers** | stdio processes launched by IDE | HTTP endpoints in K8s / Docker / cloud |
| **Configured via** | IDE JSON files | Explicit URLs in config or env vars |
| **LangSight runs** | Developer's laptop | As a service / sidecar in your infra |
| **Onboarding** | `langsight init` (IDE scan) | Explicit URL registration |
| **Value** | Catch issues before prod | Catch prod outages, drift, security |

---

## Production Onboarding (the real target)

Production MCP servers are HTTP endpoints — not stdio processes on a laptop. Nobody has a `~/.cursor/mcp.json` in production.

### Option A — Config file (most common)

Deploy `.langsight.yaml` alongside your agents:

```yaml
servers:
  - name: postgres-mcp
    transport: streamable_http
    url: https://postgres-mcp.internal.company.com/mcp

  - name: search-mcp
    transport: streamable_http
    url: https://search-mcp.k8s.company.com/mcp

  - name: github-mcp
    transport: streamable_http
    url: https://github-mcp.prod.company.com/mcp
    headers:
      Authorization: "Bearer ${GITHUB_MCP_TOKEN}"

alerts:
  slack_webhook: "${SLACK_WEBHOOK_URL}"

monitoring:
  interval_seconds: 60
  degraded_interval_seconds: 15
  down_interval_seconds: 5
```

### Option B — Environment variables (12-factor / CI-CD friendly)

```bash
LANGSIGHT_MCP_SERVERS="postgres-mcp=https://postgres-mcp.internal/mcp,search-mcp=https://search-mcp.internal/mcp"
LANGSIGHT_SLACK_WEBHOOK="https://hooks.slack.com/..."
LANGSIGHT_API_KEYS="your-api-key"
```

### Option C — CLI (one-off registration)

```bash
# Register a production HTTP server
langsight add postgres-mcp \
  --url https://postgres-mcp.internal.company.com/mcp

# With auth header
langsight add github-mcp \
  --url https://github-mcp.prod.company.com/mcp \
  --header "Authorization=Bearer $TOKEN"

# Stdio server (local / dev only)
langsight add local-db \
  --command "uv run python server.py" \
  --args "--db-url postgresql://localhost/mydb"
```

Output after `langsight add`:
```
Adding postgres-mcp...
  ✓ Connection test: UP (38ms)
  ✓ Protocol: MCP 2025-03-26
  ✓ Tools discovered: query, insert, update, list_tables (4)
  ✓ Added to .langsight.yaml

Run `langsight mcp-health postgres-mcp` for details.
```

### Option D — Dashboard (team / platform view)

`/settings` → MCP Servers → "Add Server" button → form:

```
Name:       [ postgres-mcp          ]
Transport:  ( ) stdio  (•) StreamableHTTP  ( ) SSE
URL:        [ https://postgres-mcp.internal.company.com/mcp ]
Auth:       [ Authorization: Bearer ••••••••••••••••••••••• ]
Interval:   [ 60 ] seconds
Tags:       [ production, database  ]

[ Test Connection ]  [ Save ]
```

On save: immediate health check → redirect to server detail page with scorecard.

---

## Local / Dev Onboarding (the onramp)

For developers building and testing agents locally. MCP servers are stdio processes launched by their IDE.

```bash
pip install langsight

langsight init
# Scans: Claude Desktop, Cursor, VS Code, Windsurf,
#        Claude Code, Gemini CLI, Kiro, Zed, Cline
# Shows discovered servers, writes .langsight.yaml
# Runs first health check immediately

langsight mcp-health
# Instant health table — no Docker required

langsight scorecard
# A-F grade per server — shareable
```

**Purpose**: Get developers familiar with LangSight on their laptop. The onramp, not the destination.

**Limitation**: stdio servers die when the IDE closes. The `langsight init` scan is a point-in-time snapshot of what's configured, not a live production inventory.

---

## How LangSight Runs in Production

LangSight deploys as a **service** alongside your agents — not as a developer CLI tool.

### Docker Compose

```yaml
services:
  langsight:
    image: langsight/langsight:latest
    environment:
      - LANGSIGHT_POSTGRES_URL=postgresql://postgres:password@postgres:5432/langsight
      - LANGSIGHT_CLICKHOUSE_URL=http://clickhouse:8123
      - LANGSIGHT_API_KEYS=your-api-key
    volumes:
      - ./langsight.yaml:/app/.langsight.yaml:ro
    command: ["langsight", "serve"]
    ports:
      - "8000:8000"

  langsight-monitor:
    image: langsight/langsight:latest
    environment:
      - LANGSIGHT_POSTGRES_URL=postgresql://postgres:password@postgres:5432/langsight
      - LANGSIGHT_CLICKHOUSE_URL=http://clickhouse:8123
    volumes:
      - ./langsight.yaml:/app/.langsight.yaml:ro
    command: ["langsight", "monitor", "--daemon"]
    restart: unless-stopped
```

### Kubernetes (sidecar pattern)

```yaml
# LangSight monitor as a sidecar or standalone deployment
# monitors the MCP servers your agents connect to
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langsight-monitor
spec:
  template:
    spec:
      containers:
        - name: langsight
          image: langsight/langsight:latest
          command: ["langsight", "monitor", "--daemon"]
          env:
            - name: LANGSIGHT_MCP_SERVERS
              value: "postgres-mcp=https://postgres-mcp.internal/mcp,search-mcp=https://search-mcp.internal/mcp"
            - name: LANGSIGHT_POSTGRES_URL
              valueFrom:
                secretKeyRef:
                  name: langsight-secrets
                  key: postgres-url
```

---

## Competitor Onboarding Comparison

| Tool | First action | Discovery | Time to value | Production-ready? |
|---|---|---|---|---|
| **Snyk Agent Scan** | `uvx snyk-agent-scan@latest` | Auto — 10+ IDE config paths | ~2 min | No — one-shot scan, not a service |
| **MCP Inspector** | `npx @mcp/inspector` | CLI arg or web form | ~30 sec | No — dev debugging tool |
| **OpenStatus** | Sign up, enter URL | Manual URL entry | ~3 min | Yes — HTTP uptime only |
| **MCP Hub** | Install Neovim plugin | Manual `servers.json` edit | ~5 min | No — editor plugin |
| **Portkey** | Admin registers in web UI | Admin catalog | Minutes (after admin) | Yes — gateway proxy |
| **Runlayer** | Enterprise sign-up | Catalog + auto-discover | Enterprise setup | Yes — $11M, enterprise |
| **Lasso** | Wrap existing `mcp.json` | Reads existing config | ~5 min | No — local gateway only |
| **LangSight** | `langsight init` (local) / config file (prod) | Auto (local) / explicit URL (prod) | <60 sec (local) / <5 min (prod) | **Yes — explicit URL config + service mode** |

**Key gap we fill**: every tool except OpenStatus and Runlayer is fundamentally a local/dev tool. OpenStatus does HTTP uptime only. Runlayer is commercial. **LangSight is the only OSS tool with both a developer local experience and a production monitoring service mode.**

---

## What NOT to Do

- **Don't scan IDE configs in production** — those files don't exist in a K8s pod
- **Don't require Docker for local dev** — `langsight init` + `langsight mcp-health` must work with zero infrastructure
- **Don't conflate stdio and HTTP** — stdio servers are local dev only; production servers are HTTP
- **Don't make URL registration harder than necessary** — one line in `.langsight.yaml` is the production onboarding

---

## The North Star Onboarding Experience

```
Local (developer, 60 seconds):
  pip install langsight && langsight init
  → sees all their MCP servers, health status, scorecard

Production (platform team, 5 minutes):
  Add .langsight.yaml with server URLs to your deployment
  docker compose up langsight
  → continuous monitoring, Slack alerts, dashboard at :8000
```

No account required. No gateway proxy. No traffic rerouting. Just point at your MCP server URLs and watch.
