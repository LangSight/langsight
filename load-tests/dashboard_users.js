/**
 * LangSight — Dashboard Users Load Test
 *
 * Simulates N concurrent users with browser-open dashboards polling the API.
 * Models the real dashboard polling pattern:
 *   - Sessions list      every 30s
 *   - Session trace      every 30s (when a session is open)
 *   - Health servers     every 60s
 *   - Lineage graph      every 300s
 *   - Costs overview     every 300s
 *
 * Run:
 *   k6 run --env BASE_URL=http://localhost:8000 \
 *           --env API_KEY=ls_yourkey \
 *           --env PROJECT_ID=yourprojectid \
 *           load-tests/dashboard_users.js
 *
 * Stages: ramp 0→100 VUs over 2 min, hold 5 min, ramp down 1 min.
 * Pass criteria: p95 < 500ms, error rate < 1%.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL   = __ENV.BASE_URL   || "http://localhost:8000";
const API_KEY    = __ENV.API_KEY    || "";
const PROJECT_ID = __ENV.PROJECT_ID || "";

const HEADERS = {
  "X-API-Key":    API_KEY,
  "Content-Type": "application/json",
};

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------
const errorRate    = new Rate("errors");
const sessionsList = new Trend("req_sessions_list_ms",  true);
const sessionTrace = new Trend("req_session_trace_ms",  true);
const healthList   = new Trend("req_health_list_ms",    true);
const lineage      = new Trend("req_lineage_ms",        true);
const costs        = new Trend("req_costs_ms",          true);

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------
export const options = {
  scenarios: {
    // Ramp to 100 dashboard users, hold, ramp down
    dashboard_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m",  target: 50  },  // warm up
        { duration: "1m",  target: 100 },  // hit 100
        { duration: "5m",  target: 100 },  // hold
        { duration: "1m",  target: 0   },  // ramp down
      ],
    },
  },
  thresholds: {
    errors:                  ["rate<0.01"],        // < 1% errors
    http_req_duration:       ["p(95)<500"],        // p95 < 500ms
    req_sessions_list_ms:    ["p(95)<300"],
    req_session_trace_ms:    ["p(95)<500"],
    req_health_list_ms:      ["p(95)<400"],
    req_lineage_ms:          ["p(95)<600"],
    req_costs_ms:            ["p(95)<400"],
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function projectParam() {
  return PROJECT_ID ? `?project_id=${PROJECT_ID}` : "";
}

function get(path, trendMetric) {
  const res = http.get(`${BASE_URL}/api${path}`, { headers: HEADERS });
  const ok  = check(res, {
    "status 200": (r) => r.status === 200,
    "has body":   (r) => r.body && r.body.length > 0,
  });
  errorRate.add(!ok);
  if (trendMetric) trendMetric.add(res.timings.duration);
  return res;
}

// ---------------------------------------------------------------------------
// Virtual user behaviour
// ---------------------------------------------------------------------------
export default function () {
  // 1. Sessions list (every 30s in real dashboard)
  const sessionsRes = get(`/agents/sessions?hours=24&limit=50${PROJECT_ID ? "&project_id=" + PROJECT_ID : ""}`, sessionsList);

  // 2. If sessions exist, fetch the trace for the most recent one
  try {
    const sessions = JSON.parse(sessionsRes.body || "[]");
    if (Array.isArray(sessions) && sessions.length > 0) {
      const sid = sessions[0].session_id;
      get(`/agents/sessions/${sid}${projectParam()}`, sessionTrace);
    }
  } catch (_) {}

  sleep(1);

  // 3. Health servers (less frequent)
  if (Math.random() < 0.5) {
    get(`/health/servers${projectParam()}`, healthList);
    sleep(0.5);
  }

  // 4. Lineage (infrequent)
  if (Math.random() < 0.2) {
    get(`/agents/lineage?hours=24${PROJECT_ID ? "&project_id=" + PROJECT_ID : ""}`, lineage);
    sleep(0.5);
  }

  // 5. Costs (infrequent)
  if (Math.random() < 0.2) {
    get(`/agents/costs?hours=24${PROJECT_ID ? "&project_id=" + PROJECT_ID : ""}`, costs);
    sleep(0.5);
  }

  // Simulate user reading the page before next poll cycle
  sleep(Math.random() * 3 + 2);  // 2–5s think time
}
