# LangSight — MCP Strategy & Research

All MCP-specific product strategy, market research, and implementation docs live here.

## Documents

| File | What It Contains |
|---|---|
| [01-market-landscape.md](01-market-landscape.md) | Full market scan — 62 tools/companies across 8 categories in MCP observability, monitoring, security, and gateways |
| [02-product-identity-positioning.md](02-product-identity-positioning.md) | LangSight's confirmed identity: "Production Reliability for AI Agents". Brain vs hands positioning vs Langfuse. |
| [03-feature-strategy-icp.md](03-feature-strategy-icp.md) | ICP definition (Mark, Sarah, MCP authors), feature tiers, what NOT to build |
| [04-top5-features-research.md](04-top5-features-research.md) | Deep research on top 5 MCP features: competitor implementations, gaps, and how LangSight should build each |
| [05-impact-analysis.md](05-impact-analysis.md) | Impact assessment: do the 5 MCP features break any existing agent features? (Answer: No) |
| [06-onboarding.md](06-onboarding.md) | Two onboarding paths: local/dev (IDE scan) vs production (explicit HTTP URLs). How others do it. |

## Decision Log

| Date | Decision |
|---|---|
| 2026-03-26 | LangSight = "Production Reliability for AI Agents". Langfuse owns observability. We own reliability. |
| 2026-03-26 | MCP monitoring is greenfield. Agent monitoring is already built and working. |
| 2026-03-26 | One product, two entry points: MCP-first (zero infra) → agents (full stack). Combined, not split. |
| 2026-03-26 | Top 5 MCP features prioritised: Discovery fix → Scorecard → Schema Drift + Consumer Impact → Continuous Daemon → Root Cause Correlation |
| 2026-03-26 | None of the 5 MCP features break existing agent features. All additive. |

## The One-Sentence Identity

> **LangSight is where engineers go when their AI agent breaks in production.**

## Biggest Competitor

**Runlayer** — $11M seed (Khosla + Felicis), MCP co-creator as advisor, 8 unicorn customers. Commercial-only. LangSight owns the OSS lane.
