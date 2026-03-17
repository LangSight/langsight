# LangSight — AI Provider Setup for `langsight investigate`

`langsight investigate` analyses MCP server failures and produces a root-cause report.
It supports four AI providers: **Claude**, **OpenAI GPT**, **Google Gemini**, and **Ollama** (local, free).

If no provider is configured or the API key is missing, the command falls back to
rule-based heuristics — useful offline or in CI pipelines.

---

## Quick Start

Add an `investigate` block to your `.langsight.yaml`:

```yaml
investigate:
  provider: gemini           # anthropic | openai | gemini | ollama
  model: gemini-2.0-flash    # optional — each provider has a sensible default
```

Then run:

```bash
langsight investigate
langsight investigate --server postgres-mcp --window 2h
```

---

## Provider 1 — Claude (Anthropic)  *(default)*

**Best for:** highest-quality RCA, adaptive reasoning, best at correlating MCP-specific patterns.

**Default model:** `claude-sonnet-4-6` (with adaptive thinking enabled)

**Other models:** `claude-opus-4-6` (deepest analysis), `claude-haiku-4-5` (fastest/cheapest)

### Setup

1. Create an account at [console.anthropic.com](https://console.anthropic.com)
2. Generate an API key under **API Keys**
3. Set the environment variable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Or add it to your shell profile (`~/.zshrc`, `~/.bashrc`):

```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc
```

### Configuration

```yaml
# .langsight.yaml
investigate:
  provider: anthropic
  model: claude-sonnet-4-6    # default — omit to use this

  # Alternative: override per-run without editing the file
  # export ANTHROPIC_API_KEY=sk-ant-...
```

### Pricing

| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| claude-sonnet-4-6 | $3/1M | $15/1M | Default, best balance |
| claude-opus-4-6 | $5/1M | $25/1M | Deepest analysis |
| claude-haiku-4-5 | $1/1M | $5/1M | Fast, budget |

A typical `investigate` call uses ~2,000 input tokens + ~1,000 output tokens ≈ **$0.02–0.06**.

---

## Provider 2 — OpenAI (GPT-4o, o1-mini)

**Best for:** teams already using OpenAI for their agents, consistent provider stack.

**Default model:** `gpt-4o`

**Other models:** `gpt-4o-mini` (cheaper), `o1-mini` (slower but stronger reasoning), `gpt-4-turbo`

### Setup

1. Create an account at [platform.openai.com](https://platform.openai.com)
2. Generate an API key under **API Keys**
3. Set the environment variable:

```bash
export OPENAI_API_KEY=sk-...
```

### Configuration

```yaml
# .langsight.yaml
investigate:
  provider: openai
  model: gpt-4o              # default

  # Budget option:
  # model: gpt-4o-mini

  # Stronger reasoning:
  # model: o1-mini
```

### Pricing

| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| gpt-4o | $2.50/1M | $10/1M | Default |
| gpt-4o-mini | $0.15/1M | $0.60/1M | Budget option |
| o1-mini | $3/1M | $12/1M | Stronger multi-step reasoning |

---

## Provider 3 — Google Gemini  *(recommended for free tier)*

**Best for:** getting started for free, large context windows (1M tokens = entire history at once).

**Default model:** `gemini-2.0-flash`

**Other models:** `gemini-2.5-pro` (best quality), `gemini-1.5-flash` (budget)

### Key advantage

Gemini models have a **1M token context window** — you can feed the full health history
of all your MCP servers in a single request without truncation.

### Setup

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **Create API key** — it's free, no credit card required
3. Set the environment variable:

```bash
export GEMINI_API_KEY=AIza...
```

### Configuration

```yaml
# .langsight.yaml
investigate:
  provider: gemini
  model: gemini-2.0-flash    # default — fast and free

  # Higher quality:
  # model: gemini-2.5-pro

  # Budget:
  # model: gemini-1.5-flash
```

### Free tier

| Limit | gemini-2.0-flash | gemini-2.5-pro |
|-------|-----------------|----------------|
| Requests/day | 1,500 | 50 |
| Requests/minute | 15 | 2 |
| Tokens/minute | 1,000,000 | 32,000 |

For most teams running `langsight investigate` on-demand, the free tier is sufficient.

### Pricing (pay-as-you-go, after free tier)

| Model | Input | Output |
|-------|-------|--------|
| gemini-2.0-flash | $0.10/1M | $0.40/1M |
| gemini-2.5-pro | $1.25/1M | $10/1M |
| gemini-1.5-flash | $0.075/1M | $0.30/1M |

---

## Provider 4 — Ollama (local, completely free)

**Best for:** air-gapped environments, no data leaving your network, zero cost, offline use.

**Default model:** `llama3.2`

**No API key required.**

### Setup

1. Install Ollama from [ollama.com/download](https://ollama.com/download)
2. Pull a model:

```bash
# Recommended — fast, good reasoning, 3B parameters (~2GB)
ollama pull llama3.2

# Better quality — needs ~8GB RAM
ollama pull llama3.1:8b

# Strong structured analysis — needs ~8GB RAM
ollama pull mistral

# Best quality — needs GPU + ~16GB RAM
ollama pull qwen2.5:14b
```

3. Ollama starts automatically. Verify it's running:

```bash
ollama list      # shows installed models
curl http://localhost:11434/api/tags   # API health check
```

### Configuration

```yaml
# .langsight.yaml
investigate:
  provider: ollama
  model: llama3.2            # default

  # For a remote Ollama server:
  # base_url: http://my-server:11434/v1
```

### Model recommendations

| Model | RAM needed | Quality | Speed | Notes |
|-------|-----------|---------|-------|-------|
| llama3.2 | 2 GB | Good | Fast | Default, best for most setups |
| llama3.1:8b | 8 GB | Better | Medium | Recommended if you have RAM |
| mistral | 8 GB | Good | Medium | Strong at structured text |
| qwen2.5:14b | 16 GB | Excellent | Slow | Best local quality |

---

## Comparison

| | Claude | OpenAI | Gemini | Ollama |
|--|--------|--------|--------|--------|
| **Free tier** | No | No | Yes (1,500/day) | Yes (unlimited) |
| **Data privacy** | Sent to Anthropic | Sent to OpenAI | Sent to Google | Stays on your machine |
| **Setup time** | 2 min | 2 min | 2 min | 5 min |
| **RCA quality** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Context window** | 200K | 128K | 1M | Varies |
| **Default model** | claude-sonnet-4-6 | gpt-4o | gemini-2.0-flash | llama3.2 |

---

## Environment Variables

| Provider | Variable | Example |
|----------|----------|---------|
| Claude | `ANTHROPIC_API_KEY` | `sk-ant-api03-...` |
| OpenAI | `OPENAI_API_KEY` | `sk-proj-...` |
| Gemini | `GEMINI_API_KEY` | `AIzaSy...` |
| Ollama | *(none required)* | — |

> [!IMPORTANT]
> Never put API keys directly in `.langsight.yaml` — use environment variables.
> The `api_key` field in `investigate:` config is for CI/CD secrets injection only.

---

## CI/CD Usage

```yaml
# GitHub Actions example
- name: Investigate MCP failures
  env:
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
  run: |
    langsight investigate --window 1h --json > rca-report.json
```

---

## Rule-Based Fallback

If no provider is configured or the API call fails, `langsight investigate` automatically
falls back to deterministic heuristics:

- Server DOWN → connection/process failure analysis
- Schema drift → unexpected deployment or supply chain warning
- High latency → performance degradation analysis
- Intermittent DEGRADED → error pattern summary

The fallback requires no API key and works offline.

---

## Troubleshooting

**`GEMINI_API_KEY not set`**
```bash
export GEMINI_API_KEY=AIza...
# or add to .langsight.yaml: investigate.api_key: AIza...
```

**`Ollama request failed: Connection refused`**
```bash
ollama serve   # start the Ollama daemon
ollama pull llama3.2   # pull the model if not installed
```

**`Unknown investigate provider 'X'`**
Valid values: `anthropic`, `openai`, `gemini`, `ollama`

**`Rate limit exceeded` (Gemini free tier)**
Switch to `gemini-2.0-flash` (highest free quota) or add billing to your Google AI account.
