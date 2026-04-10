# SEO Baseline — 2026-04-10

Snapshot taken immediately after the first SEO optimization pass (commit `92e080c`).
Use this as the comparison point when re-running `/seo google gsc` and `/seo google ga4`.

## Overall Health Score
**70 / 100** (audit run 2026-04-10)

| Category | Score |
|---|---|
| Technical SEO | 78 |
| Content Quality | 68 |
| On-Page SEO | 75 |
| Schema / Structured Data | 82 |
| Performance (CWV) | 65 |
| AI Search Readiness | 55 |
| Images | 40 |

---

## Google Search Console — 90-day window (2026-01-10 → 2026-04-07)

### Totals
| Metric | Value |
|---|---|
| Total clicks | 2 |
| Total impressions | 253 |
| Avg CTR | 0.79% |
| Active queries | 19 |

### Page-level performance

| Page | Impressions | Avg Position | Clicks | CTR |
|---|---|---|---|---|
| `/blog/ai-agent-loop-detection/` | 146 | 5.9 | 1 | 0.68% |
| `/alternatives/` | 27 | 16.2 | 0 | 0% |
| `/` | 21 | 8.8 | 1 | 4.76% |
| `/glossary/` | 16 | 9.4 | 0 | 0% |
| `docs.../openai-sdk` | 8 | 59.0 | 0 | 0% |
| `/blog/circuit-breakers-ai-agents/` | 6 | 7.7 | 0 | 0% |
| `/blog/owasp-mcp-top-10-guide/` | 4 | 8.0 | 0 | 0% |
| `/blog/mcp-monitoring-production/` | 4 | 11.0 | 0 | 0% |
| `/blog/langsight-vs-langfuse/` | 4 | 79.0 | 0 | 0% |
| `docs.../quickstart` | 4 | 4.5 | 0 | 0% |
| `http://langsight.dev/` (HTTP) | 4 | 3.2 | 0 | 0% |
| `/pricing/` | 3 | 6.0 | 0 | 0% |
| `/blog/mcp-schema-drift/` | 2 | 9.0 | 0 | 0% |
| `/blog/slos-for-ai-agents/` | 1 | 7.0 | 0 | 0% |
| `docs.../cli/sessions` | 1 | 4.0 | 0 | 0% |
| `docs.../database-connections` | 1 | 6.0 | 0 | 0% |
| `docs.../introduction` | 1 | 10.0 | 0 | 0% |

### Query-level performance (key queries)

| Query | Page | Position | Impressions |
|---|---|---|---|
| `how to detect ai agent looping or stalling` | loop blog | **1.0** | 1 |
| `mcp model context protocol definition` | glossary | **3.0** | 1 |
| `langfuse vs langwatch` | alternatives | **7.0** | 1 |
| `langwatch vs langfuse` | alternatives | **9.6** | 8 |
| `owasp mcp top 10 2025` | owasp blog | **9.0** | 1 |
| `tools to monitor agent behavior (loops, wrong tool selection, context loss)` | loop blog | **9.0** | 1 |
| `your production agent is consuming 3x more tokens...` | loop blog | **10.0** | 1 |
| `how to detect infinite loops in ai agents tool calling` | loop blog | 13.5 | 2 |
| `langfuse vs langtrace ai` | alternatives | 75.0 | 1 |
| `langfuse vs langtrace ai` | vs-langfuse blog | 64.0 | 1 |
| `مراقبة وكيل langfuse` (Arabic) | alternatives | 66.7 | 3 |
| `openai sdk` | docs/openai-sdk | 53.8 | 6 |

---

## GA4 Organic Traffic — 90-day window (2026-01-10 → 2026-04-09)

### Totals
| Metric | Value |
|---|---|
| Sessions | 19 |
| Users | 11 |
| Pageviews | 25 |
| Avg daily sessions | 1.9 |

### Top landing pages
| Page | Sessions | Users | Bounce rate | Engagement rate |
|---|---|---|---|---|
| `/` | 17 | 4 | 64.7% | 35.3% |
| `/blog/ai-agent-loop-detection` | 1 | 1 | 100% | 0% |

### Notable engagement sessions
- 2026-03-22: 4 sessions, 8 pageviews, **11 min avg session** (deep evaluation)
- 2026-03-28: 1 session, 2 pageviews, **23 min avg session** (thorough read)
- 2026-04-09: 1 session, 2 pageviews, **18 min avg session**

---

## PageSpeed Insights (Lighthouse, 2026-04-10)

### Mobile
| Metric | Score | Value |
|---|---|---|
| Performance | 90 | — |
| FCP | 100 | 0.9s |
| LCP | 64 ⚠️ | 3.5s |
| TBT | 100 | 10ms |
| CLS | 100 | 0.035 |
| Speed Index | 93 | 3.1s |
| TTI | 80 | 4.7s |

### Desktop
| Metric | Score | Value |
|---|---|---|
| Performance | 85 | — |
| FCP | 100 | 0.3s |
| LCP | 99 | 0.7s |
| TBT | 79 ⚠️ | 200ms |
| CLS | 86 ⚠️ | 0.115 |
| Speed Index | 49 🔴 | 2.3s |
| TTI | 96 | 1.9s |

### Top Lighthouse issues
- `agent_Details.png` — 433KB unoptimized (convert to WebP)
- Unused JS: `bd904a5c.js` 82KB + GTM 64KB
- Images missing `width`/`height` → CLS 0.115 on desktop
- Render-blocking CSS: `49f476761014fa49.css`
- Legacy JS polyfills: `1255-320f0521cc2d8e5a.js`

---

## Fixes Applied (commit 92e080c, 2026-04-10)

| Fix | File |
|---|---|
| Created `llms.txt` for AI crawlers | `public/llms.txt` |
| Added GPTBot/ClaudeBot/PerplexityBot/CCBot to robots.txt | `public/robots.txt` |
| Removed self-preconnect, added GTM preconnect | `app/layout.tsx` |
| Created `.well-known/security.txt` | `public/.well-known/security.txt` |
| Loop blog: new title + 2 FAQ entries targeting GSC queries | `blog/ai-agent-loop-detection/layout.tsx` |
| Circuit breakers blog: new title + FAQPage schema | `blog/circuit-breakers-ai-agents/layout.tsx` |
| OWASP blog: "2026" in title, updated dateModified | `blog/owasp-mcp-top-10-guide/layout.tsx` |
| Alternatives: 5 competitors, 6-col table, FAQPage schema | `alternatives/layout.tsx` + `alternatives/page.tsx` |

---

## Remaining Issues (not yet fixed)

| Priority | Issue |
|---|---|
| High | OG image is 6.8KB (broken/placeholder) — needs real 1200×630 branded image |
| High | Blog posts all show `datePublished: 2026-04-02` — should be spread over weeks |
| High | No named author — all "LangSight Engineering" — E-E-A-T gap |
| High | No external authority links in blog posts |
| Medium | `agent_Details.png` 433KB — convert to WebP |
| Medium | Images missing `width`/`height` attributes (CLS 0.115 desktop) |
| Medium | Glossary only 10 terms — expand to 30+ |
| Medium | Cache-control: max-age=0 — no edge caching |
| Low | `blog/langsight-vs-langfuse/` competing with `/alternatives/` for same queries (cannibalization) |

---

## How to Compare (re-run after 2–4 weeks)

```bash
cd ~/.claude/skills/seo

# GSC query data
python3 scripts/gsc_query.py query --property sc-domain:langsight.dev --days 30 --json

# GSC page data
python3 scripts/gsc_query.py query --property sc-domain:langsight.dev --days 30 --dimensions page --json

# GA4 organic
source .venv/bin/activate && python3 scripts/ga4_report.py --property properties/529393006 --days 30 --json

# PageSpeed
python3 -c "
import os, urllib.request, json
key = os.environ['PAGESPEED_API_KEY']  # set in .env — never hardcode
for strategy in ['mobile','desktop']:
    url = f'https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://langsight.dev&strategy={strategy}&key={key}'
    with urllib.request.urlopen(url) as r:
        d = json.loads(r.read())
    cats = d.get('lighthouseResult',{}).get('categories',{})
    print(strategy, {k: int((v.get('score') or 0)*100) for k,v in cats.items()})
"
```

**Targets to beat:**
- Loop blog CTR: > 3% (from 0.68%)
- Alternatives position: < 10 (from 16.2)
- Circuit breakers CTR: > 2% (from 0%)
- Total impressions: > 400 (from 253)
- Total clicks: > 10 (from 2)
