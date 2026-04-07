/**
 * LangSight — Agent Span Ingestion Load Test
 *
 * Simulates concurrent agent runs flushing spans to POST /api/traces/spans.
 * This is the write-heavy path — tests ClickHouse insert throughput and
 * Postgres connection pool under simultaneous agent activity.
 *
 * Models a real CrewAI crew flush: 40–60 spans per batch, every ~2 minutes.
 *
 * Run:
 *   k6 run --env BASE_URL=http://localhost:8000 \
 *           --env API_KEY=ls_yourkey \
 *           --env PROJECT_ID=yourprojectid \
 *           load-tests/agent_span_ingestion.js
 *
 * Stages:
 *   - 10 concurrent agent runs (baseline)
 *   - Ramp to 50 simultaneous flushes
 *   - Ramp to 100 simultaneous flushes
 *
 * Pass criteria: p95 < 2s, error rate < 0.5%, no 500s.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";
import { uuidv4 } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

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
const errorRate   = new Rate("span_ingest_errors");
const ingestTime  = new Trend("span_ingest_ms", true);
const spansTotal  = new Counter("spans_sent_total");

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------
export const options = {
  scenarios: {
    // Baseline: 10 constant concurrent flushes
    baseline: {
      executor: "constant-vus",
      vus: 10,
      duration: "2m",
      startTime: "0s",
      tags: { scenario: "baseline" },
    },
    // Ramp: simulate 50 simultaneous agent completions
    ramp_50: {
      executor: "ramping-vus",
      startVUs: 10,
      stages: [
        { duration: "1m", target: 50 },
        { duration: "3m", target: 50 },
        { duration: "30s", target: 0 },
      ],
      startTime: "2m",
      tags: { scenario: "ramp_50" },
    },
    // Spike: 100 simultaneous flushes (stress test)
    spike_100: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 100 },
        { duration: "2m",  target: 100 },
        { duration: "30s", target: 0   },
      ],
      startTime: "7m",
      tags: { scenario: "spike_100" },
    },
  },
  thresholds: {
    span_ingest_errors: ["rate<0.005"],   // < 0.5% errors
    span_ingest_ms:     ["p(95)<2000"],   // p95 < 2s
    http_req_failed:    ["rate<0.005"],
  },
};

// ---------------------------------------------------------------------------
// Span generators — realistic shapes matching actual CrewAI runs
// ---------------------------------------------------------------------------
function makeSpan(sessionId, spanType, toolName, serverName, agentName, parentSpanId) {
  const now = new Date();
  const started = new Date(now - Math.floor(Math.random() * 5000 + 500));
  return {
    span_id:        uuidv4(),
    parent_span_id: parentSpanId || null,
    span_type:      spanType,
    session_id:     sessionId,
    server_name:    serverName,
    tool_name:      toolName,
    started_at:     started.toISOString(),
    ended_at:       now.toISOString(),
    latency_ms:     now - started,
    status:         "success",
    error:          null,
    agent_name:     agentName,
    project_id:     PROJECT_ID || null,
    lineage_provenance: "explicit",
    lineage_status:     "complete",
    schema_version:     "1.0",
  };
}

function buildCrewBatch(sessionId) {
  // Simulate a realistic 3-agent crew flush: crew + 3 tasks + 3 agents + LLM calls + tools
  const spans = [];

  // Crew root
  const crewSpan = makeSpan(sessionId, "agent", "crew:test-crew", "crewai", "crew", null);
  spans.push(crewSpan);

  const agents = ["Lead Analyst", "Strategist", "Writer"];
  const taskNames = ["research_task", "strategy_task", "writing_task"];

  for (let i = 0; i < agents.length; i++) {
    // Task span
    const taskSpan = makeSpan(sessionId, "agent", `task:${taskNames[i]}`, "crewai", agents[i], crewSpan.span_id);
    spans.push(taskSpan);

    // Agent span
    const agentSpan = makeSpan(sessionId, "agent", `agent:${agents[i]}`, "crewai", agents[i], taskSpan.span_id);
    spans.push(agentSpan);

    // 3–5 LLM calls per agent
    const llmCount = Math.floor(Math.random() * 3) + 3;
    for (let j = 0; j < llmCount; j++) {
      const llmSpan = makeSpan(sessionId, "agent", "generate/claude-haiku-4-5-20251001", "anthropic", agents[i], agentSpan.span_id);
      llmSpan.input_tokens  = Math.floor(Math.random() * 2000) + 500;
      llmSpan.output_tokens = Math.floor(Math.random() * 500)  + 100;
      llmSpan.model_id      = "claude-haiku-4-5-20251001";
      spans.push(llmSpan);
    }

    // 1–3 tool calls per agent
    const toolCount = Math.floor(Math.random() * 3) + 1;
    for (let j = 0; j < toolCount; j++) {
      const toolSpan = makeSpan(sessionId, "tool_call", "search_web", "crewai", agents[i], agentSpan.span_id);
      spans.push(toolSpan);
    }
  }

  return spans;
}

// ---------------------------------------------------------------------------
// Virtual user: simulate one agent run completing and flushing spans
// ---------------------------------------------------------------------------
export default function () {
  const sessionId = uuidv4().replace(/-/g, "");  // hex UUID, matches SDK format
  const batch = buildCrewBatch(sessionId);

  const res = http.post(
    `${BASE_URL}/api/traces/spans`,
    JSON.stringify(batch),
    { headers: HEADERS, tags: { name: "ingest_spans" } },
  );

  const ok = check(res, {
    "202 accepted":    (r) => r.status === 202,
    "no server error": (r) => r.status < 500,
  });

  errorRate.add(!ok);
  ingestTime.add(res.timings.duration);
  spansTotal.add(batch.length);

  if (!ok) {
    console.error(`Ingest failed: ${res.status} ${res.body?.substring(0, 200)}`);
  }

  // Simulate gap between agent runs (real agents take minutes, not milliseconds)
  sleep(Math.random() * 4 + 1);  // 1–5s between flushes per VU
}
