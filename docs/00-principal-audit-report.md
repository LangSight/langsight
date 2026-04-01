# Principal Engineer Audit Report

**Date**: 2026-03-23
**Scope**: Architecture, Security, Scalability, OSS Readiness
**Status**: Review Complete - Action Items Identified

## 1. Executive Summary

LangSight has a strong architectural foundation (FastAPI + ClickHouse + Postgres) and well-defined domains (Prevention, Detection, Monitoring). The codebase exhibits high quality with strict typing and comprehensive testing. However, **critical reliability risks** exist in the current implementation of the SDK and Real-time subsystem that will prevent safe scaling to 100+ concurrent users or exposed public deployments.

## 2. Critical Issues (P0 - Immediate Fix Required)

### 2.1 SDK Memory Leak / DoS Vector
**Component**: `LangSightClient` (SDK)
**Findings**: The prevention layer stores state (`LoopDetector`, `SessionBudget`) in unbound dictionaries keyed by `session_id`.
**Risk**: An attacker or a misconfigured agent generating random session IDs will cause unbounded memory growth in the client application, leading to an OOM crash (Denial of Service).
**Evidence**: `tests/unit/sdk/test_prevention_security.py` explicitly documents this ("1000 sessions = 1000 detectors in memory").
**Fix**: Implement an LRU (Least Recently Used) cache or a hard limit on the size of `_loop_detectors` and `_session_budgets` dictionaries.

### 2.2 SSE Scalability Bottleneck
**Component**: `SSEBroadcaster` (API)
**Findings**: The live event feed uses an in-memory Pub/Sub with a hardcoded limit of 200 clients.
**Risk**: With "100 people accessing at the same time" (likely >200 tabs/connections), the dashboard live features will fail for new connections. Furthermore, this design prevents horizontal scaling of the API; events published on Instance A are not visible to users connected to Instance B.
**Fix**: Externalize the Pub/Sub state to Redis. This removes the per-instance connection limit (delegating it to Redis capabilities) and enables multi-instance deployments.

## 3. Architecture & Feature Evaluation

### Strengths
- **DualStorage**: Excellent separation of concerns (OLTP metadata vs OLAP analytics).
- **Prevention Layer**: The client-side blocking (circuit breakers) is a significant differentiator.
- **Documentation**: The documentation culture (`docs-keeper`) is mature and production-grade.

### Weaknesses / Technical Debt
- **Local-Only Circuit Breakers**: In a distributed agent deployment (e.g., 10 Kubernetes pods), circuit breakers are local to each pod. A failing tool must fail `threshold * N_pods` times to be fully blocked.
- **Configuration Split-Brain**: v0.3.1 introduces dashboard-managed config fetched via background tasks. If the API is down, the agent falls back to hardcoded defaults. This "fail-open" is safe but can lead to confusing debugging scenarios where dashboard settings are ignored silently.

## 4. Concurrency Assessment (100 Concurrent Users)

**Verdict**: **Conditional Pass** (Data Layer) / **Fail** (Real-time Layer).

| Layer | Status | Analysis |
|---|---|---|
| **Ingestion** | **Pass** | ClickHouse + OTEL Collector can easily handle thousands of spans/sec. |
| **API Reads** | **Pass** | FastAPI + AsyncPG handles 100 concurrent requests efficiently. |
| **Dashboard** | **Fail** | The `SSEBroadcaster` limit of 200 clients means 100 users with 2 tabs each will saturate the server, causing dropped connections or instability. |

**Recommendation**: Do not market "100 concurrent users" support until Redis Pub/Sub is implemented.

## 5. Roadmap for OSS Adoption (Smaller Companies)

To be a reliable platform for smaller companies, LangSight needs to lower the operational burden.

1.  **"Lite" Deployment**: The removal of SQLite was architecturally sound for the product but hurts adoption. Re-introducing a "Single Container" mode (Postgres + API + Dashboard in one image, sans ClickHouse if possible, or using embedded ClickHouse/DuckDB) would lower the barrier to entry.
2.  **Distributed State Option**: Provide an optional Redis backend for the SDK so circuit breaker state can be shared across agent replicas.
3.  **Hosted Demo**: A readonly, publicly accessible dashboard populated with the sample data is essential for conversion.

## 6. Implementation Plan Updates

The following items should be added to the roadmap immediately:

- [ ] **Fix**: Implement LRU Cache for SDK Prevention State.
- [ ] **Feat**: Redis-backed SSE Broadcaster.
- [ ] **Feat**: Distributed Circuit Breaker support (Redis).
