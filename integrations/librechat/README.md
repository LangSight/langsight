# LangSight — LibreChat Plugin

Traces every MCP tool call made through LibreChat and sends spans to the LangSight API.
Follows the same env-var pattern as LibreChat's native Langfuse integration.

## Setup

### 1. Copy the plugin

```bash
cp integrations/librechat/langsight-plugin.js /path/to/librechat/plugins/
```

### 2. Register in librechat.yaml

```yaml
plugins:
  - name: langsight
    path: ./plugins/langsight-plugin.js
```

### 3. Set environment variables

```bash
# Required
LANGSIGHT_URL=http://localhost:8000

# Optional
LANGSIGHT_API_KEY=your-api-key
LANGSIGHT_AGENT_NAME=librechat-agent    # shown in traces
```

### 4. Start LangSight and LibreChat

```bash
# Terminal 1 — start LangSight API
langsight serve --config .langsight.yaml

# Terminal 2 — start LibreChat (existing process)
npm run start
```

All MCP tool calls from LibreChat now appear in `langsight serve` logs:

```
trace.span_received  server=postgres-mcp  tool=query  status=success  latency_ms=42.0
trace.span_received  server=confluence-mcp  tool=search  status=error  latency_ms=1240.0
```

## How it works

LibreChat wraps the MCP client through its plugin system before passing it to agents.
The plugin intercepts `callTool()`, records timing and outcome, and POSTs a
`ToolCallSpan` to LangSight's `/api/traces/spans` endpoint as a fire-and-forget task.

**Fail-open**: if LangSight is unreachable or slow, the plugin logs a debug message
and the tool call proceeds normally. Your agents are never blocked by monitoring.

## What you see in LangSight

Once spans are flowing, `langsight mcp-health` cross-references live tool call
data with health check results:

| Tool | Health | Success rate | p99 latency | Last error |
|------|--------|-------------|-------------|------------|
| postgres-mcp/query | ✓ up | 99.1% | 180ms | — |
| confluence-mcp/search | ⚠ degraded | 87.4% | 2.4s | timeout |
| slack-mcp/post | ✗ down | 12.0% | — | auth_error |

## Requirements

- Node.js 18+ (uses native `fetch`)
- LibreChat with plugin support
- LangSight `langsight serve` running
