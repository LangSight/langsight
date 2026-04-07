# LangSight Load Tests

Two k6 scripts that answer the "can it handle 100 users?" question with real numbers.

## Prerequisites

```bash
# macOS
brew install k6

# Linux
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
     --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
     | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

The stack must be running: `docker compose up -d`

---

## Test 1 — Dashboard Users (read load)

Simulates 100 concurrent users with open dashboards polling the API.

```bash
k6 run \
  --env BASE_URL=http://localhost:8000 \
  --env API_KEY=ls_yourkey \
  --env PROJECT_ID=yourprojectid \
  load-tests/dashboard_users.js
```

**What it measures:**
- Sessions list, session trace, health servers, lineage, costs endpoints
- Ramps 0 → 50 → 100 VUs, holds 5 min, ramps down

**Pass criteria:** p95 < 500ms, error rate < 1%

---

## Test 2 — Agent Span Ingestion (write load)

Simulates concurrent CrewAI agent runs all flushing spans simultaneously.

```bash
k6 run \
  --env BASE_URL=http://localhost:8000 \
  --env API_KEY=ls_yourkey \
  --env PROJECT_ID=yourprojectid \
  load-tests/agent_span_ingestion.js
```

**What it measures:**
- `POST /api/traces/spans` with realistic 20–40 span batches
- Three stages: 10 VUs baseline → 50 simultaneous flushes → 100 spike

**Pass criteria:** p95 < 2s, error rate < 0.5%, no 500s

---

## Run both together (realistic mixed load)

```bash
# Terminal 1 — dashboard users
k6 run --env BASE_URL=http://localhost:8000 --env API_KEY=ls_yourkey \
       load-tests/dashboard_users.js &

# Terminal 2 — agent ingestion
k6 run --env BASE_URL=http://localhost:8000 --env API_KEY=ls_yourkey \
       load-tests/agent_span_ingestion.js
```

---

## Reading the output

```
✓ status 200
✗ status 200 ← failure

http_req_duration......: avg=142ms  min=8ms  med=89ms  max=4.1s  p(90)=312ms  p(95)=488ms
http_req_failed........: 0.21%  ✓ 4820  ✗ 10
```

Key numbers to watch:
| Metric | Healthy | Degraded | Broken |
|--------|---------|----------|--------|
| `p(95) http_req_duration` | < 500ms | 500ms–2s | > 2s |
| `http_req_failed` | < 0.5% | 0.5–2% | > 2% |
| `span_ingest_ms p95` | < 1s | 1–3s | > 3s |

---

## What to watch while tests run

```bash
# Postgres connections (in another terminal)
watch -n2 'docker exec langsight-postgres psql -U langsight -c "SELECT count(*) FROM pg_stat_activity WHERE state='"'"'active'"'"';"'

# ClickHouse insert queue
watch -n2 'docker exec langsight-clickhouse clickhouse-client -q "SELECT * FROM system.asynchronous_metrics WHERE metric LIKE '"'"'%Insert%'"'"';"'

# API worker CPU/memory
docker stats langsight-api --no-stream
```
