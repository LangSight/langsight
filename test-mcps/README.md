# LangSight Test MCP Servers

Two real MCP servers for testing and dogfooding LangSight.

## Servers

| Server | Tools | Transport |
|---|---|---|
| `postgres-mcp` | query, list_tables, describe_table, get_row_count, get_schema_summary | stdio |
| `s3-mcp` | list_buckets, list_objects, get_object_metadata, read_object, put_object, delete_object, search_objects | stdio |

---

## Quick Start

### 1. Start PostgreSQL

```bash
docker compose up -d
```

This spins up Postgres on port 5432 with sample data (customers, orders, products, agent_conversations).

### 2. Set up PostgreSQL MCP

```bash
cd postgres-mcp
cp .env.example .env
pip install -e .
```

### 3. Set up S3 MCP

```bash
cd s3-mcp
cp .env.example .env
# Edit .env with your AWS credentials
pip install -e .
```

### 4. Add to Claude Desktop

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "langsight-postgres": {
      "command": "python",
      "args": ["/path/to/test-mcps/postgres-mcp/server.py"],
      "env": {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "langsight_test",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres"
      }
    },
    "langsight-s3": {
      "command": "python",
      "args": ["/path/to/test-mcps/s3-mcp/server.py"],
      "env": {
        "AWS_ACCESS_KEY_ID": "your_key",
        "AWS_SECRET_ACCESS_KEY": "your_secret",
        "AWS_REGION": "eu-west-1"
      }
    }
  }
}
```

### 5. Test PostgreSQL MCP manually

```bash
cd postgres-mcp
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python server.py
```

---

## Sample Data

The Postgres database has 5 tables:

| Table | Description |
|---|---|
| `customers` | 10 customers with tiers (standard/premium/enterprise) |
| `products` | 10 products (software licenses, support plans, credits) |
| `orders` | 10 orders across various statuses |
| `order_items` | Line items per order |
| `agent_conversations` | Sample agent conversation logs for dogfooding |

### Useful test queries

```sql
-- Revenue by customer tier
SELECT tier, COUNT(*) as customers, SUM(o.total_usd) as total_revenue
FROM customers c JOIN orders o ON c.customer_id = o.customer_id
WHERE o.status = 'delivered'
GROUP BY tier ORDER BY total_revenue DESC;

-- Recent failed agent conversations
SELECT * FROM agent_conversations WHERE status = 'failed';

-- Top products by revenue
SELECT p.name, SUM(oi.quantity * oi.unit_price_usd) as revenue
FROM products p JOIN order_items oi ON p.product_id = oi.product_id
GROUP BY p.name ORDER BY revenue DESC;
```
