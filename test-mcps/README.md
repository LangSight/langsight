# LangSight Test MCP Servers

Two real MCP servers for testing and dogfooding LangSight.

## Servers

| Server | Tools | Transport |
|--------|-------|-----------|
| `postgres-mcp` | `query`, `list_tables`, `describe_table`, `get_row_count`, `get_schema_summary` | stdio |
| `s3-mcp` | `list_buckets`, `list_objects`, `get_object_metadata`, `read_object`, `put_object`, `delete_object`, `search_objects` | stdio |

---

## Quick Start

### 1. Start PostgreSQL

```bash
cd test-mcps
docker compose up -d
```

Spins up Postgres 16 on port `5432` with the e-commerce sample data auto-seeded.

### 2. Set up postgres-mcp

```bash
cd postgres-mcp
cp .env.example .env
uv sync
```

### 3. Set up s3-mcp

```bash
cd s3-mcp
cp .env.example .env
# Fill in your AWS credentials in .env
uv sync
```

### 4. Test manually (stdio)

```bash
# postgres
cd postgres-mcp && echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | uv run python server.py

# s3
cd s3-mcp && echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | uv run python server.py
```

### 5. Inspect with MCP dev tools

```bash
uv run mcp dev postgres-mcp/server.py
uv run mcp dev s3-mcp/server.py
```

---

## Add to Claude Desktop

`~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "langsight-postgres": {
      "command": "uv",
      "args": ["run", "python", "/path/to/test-mcps/postgres-mcp/server.py"],
      "env": {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "langsight_test",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres"
      }
    },
    "langsight-s3": {
      "command": "uv",
      "args": ["run", "python", "/path/to/test-mcps/s3-mcp/server.py"],
      "env": {
        "AWS_ACCESS_KEY_ID": "your_key",
        "AWS_SECRET_ACCESS_KEY": "your_secret",
        "AWS_REGION": "eu-central-1"
      }
    }
  }
}
```

---

## Sample Data (postgres-mcp)

| Table | Rows | Description |
|-------|------|-------------|
| `customers` | 10 | 3 tiers: standard / premium / enterprise |
| `products` | 10 | Subscriptions, credits, support plans, add-ons |
| `orders` | 10 | Various statuses: pending, processing, delivered, cancelled |
| `order_items` | 13 | Line items linking orders to products |
| `agent_conversations` | 5 | Sample agent sessions including failures and timeouts |

### Useful test queries

```sql
-- Revenue by customer tier
SELECT c.tier, COUNT(DISTINCT c.customer_id) AS customers, SUM(o.total_usd) AS revenue
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE o.status = 'delivered'
GROUP BY c.tier
ORDER BY revenue DESC;

-- Failed agent conversations
SELECT session_id, agent_name, tool_calls_count, error_message
FROM agent_conversations
WHERE status IN ('failed', 'timeout')
ORDER BY created_at DESC;

-- Top products by revenue
SELECT p.name, p.category, SUM(oi.quantity * oi.unit_price_usd) AS revenue
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
GROUP BY p.product_id, p.name, p.category
ORDER BY revenue DESC;
```

---

## Security Notes

- `postgres-mcp` only allows `SELECT`, `WITH`, and `EXPLAIN` statements — all mutating SQL is rejected.
- `s3-mcp` uses credentials from `.env` only — never hardcoded.
- `.env` files are gitignored.
