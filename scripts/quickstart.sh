#!/usr/bin/env bash
# LangSight quickstart — idempotent, safe to re-run at any time.
#
# Usage:
#   ./scripts/quickstart.sh           # normal start / resume
#   ./scripts/quickstart.sh --redis   # start with Redis (multi-worker mode)
#   ./scripts/quickstart.sh --reset   # wipe volumes + .env and start fresh
#   ./scripts/quickstart.sh --build   # force rebuild of Docker images
#
# Flags can be combined:
#   ./scripts/quickstart.sh --reset --redis
#   ./scripts/quickstart.sh --reset --build
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"
CONFIG_FILE="$ROOT_DIR/.langsight.yaml"

# ── Parse flags ──────────────────────────────────────────────────────────────
RESET=false
FORCE_BUILD=false
WITH_REDIS=false
for arg in "$@"; do
  case "$arg" in
    --reset) RESET=true ;;
    --build) FORCE_BUILD=true ;;
    --redis) WITH_REDIS=true ;;
    --help)
      echo "Usage: ./scripts/quickstart.sh [--reset] [--build] [--redis]"
      echo ""
      echo "  --reset   Wipe all data (volumes + .env) and start fresh"
      echo "  --build   Force rebuild of Docker images"
      echo "  --redis   Start Redis alongside the core stack (enables multi-worker mode)"
      exit 0
      ;;
  esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
ok()    { echo -e "${GREEN}[ok]${NC} $*"; }
info()  { echo -e "     $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

echo "──────────────────────────────────────────────────────"
echo "  LangSight Quickstart"
if [ "$WITH_REDIS" = true ]; then
  echo "  (Redis mode)"
fi
echo "──────────────────────────────────────────────────────"
echo ""

# ── Pre-flight checks ─────────────────────────────────────────────────────────
echo "[..] Running pre-flight checks..."

# Docker
if ! docker info > /dev/null 2>&1; then
  error "Docker is not running."
  info  "Start Docker Desktop and try again."
  exit 1
fi
ok "Docker is running"

# docker compose (v2 plugin)
if ! docker compose version > /dev/null 2>&1; then
  error "docker compose not found."
  info  "Install Docker Desktop (includes Compose v2): https://docs.docker.com/get-docker/"
  exit 1
fi
ok "docker compose available"

# openssl (for secret generation)
if ! command -v openssl > /dev/null 2>&1; then
  error "openssl not found — required to generate secrets."
  info  "Install with: brew install openssl"
  exit 1
fi
ok "openssl available"

# Disk space — warn if less than 4 GB free (skip on systems without df/awk)
if command -v df > /dev/null 2>&1 && command -v awk > /dev/null 2>&1; then
  FREE_KB=$(df -k "$ROOT_DIR" 2>/dev/null | awk 'NR==2 {print $4}' || echo "0")
  FREE_GB=$(( FREE_KB / 1024 / 1024 ))
  if [ "$FREE_GB" -lt 4 ]; then
    warn "Less than 4 GB free disk space (${FREE_GB} GB). Docker images need ~3 GB."
    warn "Continuing anyway — free up space if the build fails."
  else
    ok "Disk space OK (${FREE_GB} GB free)"
  fi
else
  warn "Cannot check disk space — skipping check"
fi

# Ports — warn if already in use (lsof is not available on Git Bash/Windows)
if command -v lsof > /dev/null 2>&1; then
  CHECK_PORTS="3003 8000 5432 8123 9000"
  if [ "$WITH_REDIS" = true ]; then
    CHECK_PORTS="$CHECK_PORTS 6379"
  fi
  PORT_CONFLICTS=""
  for port in $CHECK_PORTS; do
    if lsof -i ":$port" -sTCP:LISTEN -t > /dev/null 2>&1; then
      PORT_CONFLICTS="$PORT_CONFLICTS $port"
    fi
  done
  if [ -n "$PORT_CONFLICTS" ]; then
    warn "Port(s) already in use:$PORT_CONFLICTS"
    warn "This may cause startup failures. Stop conflicting services first."
  else
    ok "Required ports are free"
  fi
else
  warn "lsof not found — skipping port conflict check (on Windows: use Git Bash or WSL)"
fi

echo ""

# ── Reset mode ───────────────────────────────────────────────────────────────
if [ "$RESET" = true ]; then
  warn "--reset: stopping containers and wiping all data..."
  cd "$ROOT_DIR"
  docker compose --profile redis down -v 2>/dev/null || true
  rm -f "$ENV_FILE"
  ok "Reset complete — starting fresh"
  echo ""
fi

# ── Clean up stale Docker directory mounts ───────────────────────────────────
# When .langsight.yaml is absent, Docker Compose creates a *directory* at the
# mount point. This causes the API to crash on startup. Remove it if present.
if [ -d "$CONFIG_FILE" ]; then
  rm -rf "$CONFIG_FILE"
fi

# ── Generate .env if missing ──────────────────────────────────────────────────
# DB passwords are fixed for local dev (ports are loopback-only: 127.0.0.1).
# Using random DB passwords causes mismatch when volumes already exist and .env
# is regenerated — the DB was initialised with the old password and rejects the
# new one. Static DB passwords eliminate this failure mode completely.
# User-facing credentials (API key, admin password, auth secret) stay random.
POSTGRES_PASSWORD_DEFAULT="langsight-local-db"
CLICKHOUSE_PASSWORD_DEFAULT="langsight-local-db"
REDIS_PASSWORD_DEFAULT="langsight-local-redis"

if [ -f "$ENV_FILE" ]; then
  ok ".env already exists — using existing credentials"
  echo ""
else
  echo "[..] Generating .env..."

  API_KEY="ls_$(openssl rand -hex 32)"
  AUTH_SECRET="$(openssl rand -base64 32)"
  ADMIN_PASSWORD="ls-$(openssl rand -hex 10)"

  cat > "$ENV_FILE" <<EOF
# Generated by scripts/quickstart.sh — $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Do not commit this file to git.

# API authentication
LANGSIGHT_API_KEYS=${API_KEY}

# Dashboard session secret
AUTH_SECRET=${AUTH_SECRET}

# Dashboard admin login
LANGSIGHT_ADMIN_EMAIL=admin@langsight.dev
LANGSIGHT_ADMIN_PASSWORD=${ADMIN_PASSWORD}

# Database passwords — fixed for local dev (ports are loopback-only)
POSTGRES_PASSWORD=${POSTGRES_PASSWORD_DEFAULT}
CLICKHOUSE_USER=langsight
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD_DEFAULT}
EOF

  ok ".env created"
  echo ""
  echo "  Admin email:    admin@langsight.dev"
  echo "  Admin password: ${ADMIN_PASSWORD}"
  echo "  API key:        ${API_KEY}"
  echo ""
fi

# ── Inject Redis env vars if --redis and not already in .env ──────────────────
if [ "$WITH_REDIS" = true ]; then
  if ! grep -q "REDIS_PASSWORD" "$ENV_FILE" 2>/dev/null; then
    cat >> "$ENV_FILE" <<EOF

# Redis — enabled with --redis flag (port is loopback-only)
REDIS_PASSWORD=${REDIS_PASSWORD_DEFAULT}
LANGSIGHT_REDIS_URL=redis://:${REDIS_PASSWORD_DEFAULT}@redis:6379
EOF
    ok "Redis credentials added to .env"
  else
    ok "Redis credentials already in .env"
  fi
fi

# ── Create config file ────────────────────────────────────────────────────────
if [ ! -f "$CONFIG_FILE" ]; then
  echo "servers: []" > "$CONFIG_FILE"
  ok ".langsight.yaml created"
fi

# ── Build images ──────────────────────────────────────────────────────────────
cd "$ROOT_DIR"

# Check if images already exist
API_IMAGE_EXISTS=false
DASH_IMAGE_EXISTS=false
if docker image inspect langsight/api:latest > /dev/null 2>&1; then
  API_IMAGE_EXISTS=true
fi
if docker image inspect langsight/dashboard:latest > /dev/null 2>&1; then
  DASH_IMAGE_EXISTS=true
fi

if [ "$FORCE_BUILD" = true ] || [ "$API_IMAGE_EXISTS" = false ] || [ "$DASH_IMAGE_EXISTS" = false ]; then
  echo "[..] Building images (3-5 min on first run — downloading dependencies)..."
  if ! docker compose build; then
    error "Docker build failed."
    info  "Check the output above for details."
    info  "Common causes: no internet connection, insufficient disk space."
    exit 1
  fi
  ok "Images built"
else
  ok "Images already exist — skipping build (use --build to force rebuild)"
fi

echo ""

# ── Start services ────────────────────────────────────────────────────────────
echo "[..] Starting services..."
# Allow non-zero exit — Docker Compose returns non-zero when a dependency
# health check condition is used (e.g. dashboard depends_on api: healthy) and
# a service is still starting. The health loop below catches real failures.
if [ "$WITH_REDIS" = true ]; then
  docker compose --profile redis up -d 2>&1 || true
else
  docker compose up -d 2>&1 || true
fi
echo ""

# ── Map service names to container names (bash 3.2 compatible) ───────────────
# Matches the container_name values in docker-compose.yml
svc_to_container() {
  case "$1" in
    postgres)   echo "langsight-app-postgres" ;;
    clickhouse) echo "langsight-clickhouse" ;;
    api)        echo "langsight-api" ;;
    dashboard)  echo "langsight-dashboard" ;;
    redis)      echo "langsight-redis" ;;
    *)          echo "$1" ;;
  esac
}

# ── Helper: inspect a container's state and health ────────────────────────────
container_state() {
  # running | exited | dead | created | paused | missing
  docker inspect --format '{{.State.Status}}' "$1" 2>/dev/null || echo "missing"
}

container_health() {
  # healthy | unhealthy | starting | none | missing
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$1" 2>/dev/null || echo "missing"
}

# ── Set services list and healthy target based on flags ───────────────────────
if [ "$WITH_REDIS" = true ]; then
  CORE_SERVICES="postgres clickhouse api dashboard redis"
  HEALTHY_TARGET=5
else
  CORE_SERVICES="postgres clickhouse api dashboard"
  HEALTHY_TARGET=4
fi

# ── Wait for healthy ──────────────────────────────────────────────────────────
echo "[..] Waiting for services to be healthy..."
echo "     (cold start: ~3-4 min on first run)"
echo ""

# Worst-case startup chain when starting from scratch:
#   postgres:   10s start_period + 5 × 5s retries  =  35s max
#   clickhouse: 20s start_period + 5 × 10s retries =  70s max
#   api:        waits for postgres+clickhouse, then 20s + 5×10s = ~140s total
#   dashboard:  waits for api,                then 20s + 3×15s  = ~205s total
#   redis:      5s start_period + 5 × 5s retries   =  30s max (parallel)
# Adding buffer: timeout = 240s
TIMEOUT=240
ELAPSED=0
INTERVAL=5

while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  HEALTHY=0
  CRASHED=""

  for svc in $CORE_SERVICES; do
    cname=$(svc_to_container "$svc")
    state=$(container_state "$cname")
    health=$(container_health "$cname")

    if [ "$state" = "running" ] && [ "$health" = "healthy" ]; then
      HEALTHY=$(( HEALTHY + 1 ))
    fi

    # Crashed = container exited/died, or running but health probe failed
    if [ "$state" = "exited" ] || [ "$state" = "dead" ] || [ "$health" = "unhealthy" ]; then
      CRASHED="$CRASHED $svc"
    fi
  done

  # All services healthy — success
  if [ "$HEALTHY" -ge "$HEALTHY_TARGET" ]; then
    break
  fi

  # Crashed containers — show diagnostics and exit with clear instructions
  if [ -n "$CRASHED" ]; then
    echo ""
    echo ""
    error "Service(s) failed to start:$CRASHED"
    echo ""

    # Collect logs and scan for known error patterns
    ALL_LOGS=""
    for svc in $CRASHED; do
      cname=$(svc_to_container "$svc")
      SVC_LOGS=$(docker compose logs --tail=40 "$svc" 2>/dev/null || true)
      echo "── $svc logs (last 40 lines) ──────────────────────────"
      echo "$SVC_LOGS"
      echo ""
      ALL_LOGS="$ALL_LOGS $SVC_LOGS"
    done

    echo "── Container states ────────────────────────────────────"
    for svc in $CORE_SERVICES; do
      cname=$(svc_to_container "$svc")
      state=$(container_state "$cname")
      health=$(container_health "$cname")
      printf "  %-12s state=%-8s health=%s\n" "$svc" "$state" "$health"
    done
    echo ""

    # Targeted fix based on detected error pattern
    echo "── Diagnosis ───────────────────────────────────────────"
    if echo "$ALL_LOGS" | grep -q "password authentication failed\|Invalid password\|InvalidPasswordError"; then
      error "DB password mismatch — .env credentials don't match existing volumes"
      echo ""
      echo "  This happens when .env was regenerated but the database"
      echo "  volumes still hold data from the previous password."
      echo ""
      echo -e "  ${GREEN}Fix:${NC} ./scripts/quickstart.sh --reset"
      echo ""
      echo "  (--reset wipes volumes + .env and starts fresh)"
    elif echo "$ALL_LOGS" | grep -q "No space left on device\|no space left"; then
      error "Out of disk space"
      echo ""
      echo "  Free up disk space and re-run."
    elif echo "$ALL_LOGS" | grep -q "address already in use\|port is already allocated\|bind.*failed"; then
      error "Port conflict — another process is using a required port"
      echo ""
      echo "  Check which ports are in use:"
      echo "    lsof -i :5432 -i :8123 -i :8000 -i :3003 -i :6379"
    else
      echo "  Common causes:"
      echo "    Stale .env + existing volumes → ./scripts/quickstart.sh --reset"
      echo "    Stale image                  → ./scripts/quickstart.sh --reset --build"
      echo "    Port conflict                → stop conflicting service, re-run"
    fi
    echo ""
    echo "  Full logs:  docker compose logs"
    echo ""
    exit 1
  fi

  # Progress indicator
  printf "  [%3ds] healthy: %d/%d —" "$ELAPSED" "$HEALTHY" "$HEALTHY_TARGET"
  for svc in $CORE_SERVICES; do
    cname=$(svc_to_container "$svc")
    state=$(container_state "$cname")
    health=$(container_health "$cname")
    if [ "$state" = "running" ] && [ "$health" = "healthy" ]; then
      printf " %s✓" "$svc"
    elif [ "$state" = "running" ]; then
      printf " %s…" "$svc"
    else
      printf " %s?" "$svc"
    fi
  done
  echo ""

  sleep "$INTERVAL"
  ELAPSED=$(( ELAPSED + INTERVAL ))
done

if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
  echo ""
  error "Timed out after ${TIMEOUT}s waiting for services."
  echo ""
  echo "── Container states ────────────────────────────────────"
  for svc in $CORE_SERVICES; do
    cname=$(svc_to_container "$svc")
    state=$(container_state "$cname")
    health=$(container_health "$cname")
    printf "  %-12s state=%-8s health=%s\n" "$svc" "$state" "$health"
  done
  echo ""
  echo "── Logs from unhealthy services ────────────────────────"
  for svc in $CORE_SERVICES; do
    cname=$(svc_to_container "$svc")
    health=$(container_health "$cname")
    if [ "$health" != "healthy" ]; then
      echo "  -- $svc --"
      docker compose logs --tail=20 "$svc" 2>/dev/null || true
    fi
  done
  echo ""
  echo "  View all logs:  docker compose logs"
  echo "  Fresh start:    ./scripts/quickstart.sh --reset"
  exit 1
fi

# ── Verify API is responding ──────────────────────────────────────────────────
echo ""
LIVENESS=$(curl -sf http://localhost:8000/api/liveness 2>/dev/null || true)
if [ -z "$LIVENESS" ]; then
  warn "API liveness check did not respond — may take a few more seconds."
fi

# ── Print success ─────────────────────────────────────────────────────────────
echo ""
echo "──────────────────────────────────────────────────────"
echo -e "  ${GREEN}LangSight is running!${NC}"
echo "──────────────────────────────────────────────────────"
echo ""
echo "  Dashboard:  http://localhost:3003"
echo "  API:        http://localhost:8000"
echo ""
echo "  Login credentials:"
echo "    Email:    $(grep LANGSIGHT_ADMIN_EMAIL "$ENV_FILE" | cut -d= -f2)"
echo "    Password: $(grep LANGSIGHT_ADMIN_PASSWORD "$ENV_FILE" | cut -d= -f2)"
echo ""
echo "  API Key:    $(grep LANGSIGHT_API_KEYS "$ENV_FILE" | cut -d= -f2)"
echo ""
echo "  Services:"
for svc in $CORE_SERVICES; do
  cname=$(svc_to_container "$svc")
  health=$(container_health "$cname")
  printf "    %-12s %s\n" "$svc" "$health"
done
echo ""
echo "  Next steps:"
echo "    1. Open http://localhost:3003 and log in"
echo "    2. Create a project in the dashboard"
echo "    3. Instrument your agent:"
echo ""
echo "       pip install langsight"
echo "       export LANGSIGHT_URL=http://localhost:8000"
echo "       export LANGSIGHT_API_KEY=<your-api-key>"
echo "       export LANGSIGHT_PROJECT_ID=<from dashboard Settings>"
echo ""
echo "       import langsight"
echo "       langsight.auto_patch()"
echo ""
echo "  Docs:       https://docs.langsight.dev"
echo "  Stop:       docker compose down"
echo "  Reset:      ./scripts/quickstart.sh --reset"
echo ""
echo "──────────────────────────────────────────────────────"
