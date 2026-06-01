#!/usr/bin/env bash
# Compendium one-shot deployer for a personal "production" host (ADR-012).
#
# Brings the whole stack up from a clean checkout: prereqs -> deps -> backing
# stores -> migrations -> derived indexes -> the four always-on services
# (backup, curate schedule, inbox watcher, access surface). Idempotent: safe to
# re-run. Localhost / single-user / no-auth posture (ADR-011).
#
# Usage:  deploy/install.sh [--host 127.0.0.1] [--port 8787]
set -euo pipefail

HOST="127.0.0.1"
PORT="8787"
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mWARN:\033[0m %s\n' "$*" >&2; }

say "Compendium deployer  (repo: $REPO_ROOT  bind: $HOST:$PORT)"

# 1. Prerequisites ----------------------------------------------------------
command -v uv >/dev/null     || { echo "ERROR: 'uv' not found (https://docs.astral.sh/uv/)"; exit 1; }
command -v docker >/dev/null || { echo "ERROR: 'docker' not found"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERROR: 'docker compose' not available"; exit 1; }
if ! command -v pg_dump >/dev/null; then
  case "$(uname)" in
    Darwin) warn "pg_dump not on PATH -> 'compendium backup' will fail (macOS: brew install libpq && brew link --force libpq)" ;;
    *)      warn "pg_dump not on PATH -> 'compendium backup' will fail (Ubuntu: sudo apt install postgresql-client)" ;;
  esac
fi

# 2. .env -------------------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  warn ".env created from .env.example -- fill in secrets (OPENROUTER/EMBEDDINGS keys, store URLs) then re-run."
  exit 1
fi

# 3. Python deps ------------------------------------------------------------
say "Syncing dependencies (uv sync)"
uv sync

# 4. Backing stores ---------------------------------------------------------
say "Starting backing stores (docker compose up -d)"
docker compose up -d
say "Waiting for stores to accept connections"
for i in $(seq 1 60); do
  pg=$(docker compose exec -T postgres pg_isready -U compendium >/dev/null 2>&1 && echo ok || echo no)
  os=$(curl -fsS -o /dev/null --max-time 2 http://localhost:9200 && echo ok || echo no)
  qd=$(curl -fsS -o /dev/null --max-time 2 http://localhost:6533/collections && echo ok || echo no)
  [ "$pg" = ok ] && [ "$os" = ok ] && [ "$qd" = ok ] && break
  sleep 2
done
[ "${pg:-no}" = ok ] || { echo "ERROR: PostgreSQL not ready"; exit 1; }
[ "${os:-no}" = ok ] || { echo "ERROR: OpenSearch not ready"; exit 1; }
[ "${qd:-no}" = ok ] || { echo "ERROR: Qdrant not ready"; exit 1; }
say "Stores up: postgres + opensearch + qdrant (memgraph optional)"

# 5. Schema + derived indexes ----------------------------------------------
say "Applying migrations (alembic upgrade head)"
uv run alembic upgrade head
say "Rebuilding derived indexes (reindex all + graph rebuild)"
uv run python -m compendium reindex all
uv run python -m compendium graph rebuild || warn "graph rebuild failed (Memgraph down?) -- non-fatal"

# 6. Always-on services -----------------------------------------------------
# On Linux, user systemd units only run without an active login session when
# "lingering" is enabled -- essential for a headless 24/7 server.
if [ "$(uname)" = "Linux" ]; then
  if loginctl enable-linger "$USER" 2>/dev/null; then
    say "systemd user lingering enabled ($USER) -- services run without a login session"
  else
    warn "could not enable systemd lingering; run:  sudo loginctl enable-linger $USER  (needed for 24/7 without an active login)"
  fi
fi

say "Installing services (backup, schedule, inbox, serve)"
uv run python -m compendium backup install   || warn "backup install failed"
uv run python -m compendium schedule install  || warn "schedule install failed"
uv run python -m compendium inbox install      || warn "inbox install failed"
uv run python -m compendium serve install --host "$HOST" --port "$PORT" || warn "serve install failed"

say "Done. Status:"
"$REPO_ROOT/deploy/compendiumctl" status || true
echo
say "Access surface: http://$HOST:$PORT   (localhost, no auth -- ADR-011)"
say "Manage with: deploy/compendiumctl {start|stop|status|restart|logs}"
