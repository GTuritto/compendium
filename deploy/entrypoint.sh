#!/usr/bin/env sh
# Apply migrations, then run the access surface in the foreground (PID 1).
set -e

VENV=/app/.venv/bin
SERVE_HOST="${SERVE_HOST:-0.0.0.0}"
SERVE_PORT="${SERVE_PORT:-8787}"

mkdir -p "${VAULT_PATH:-/app/vault}"

echo "[entrypoint] alembic upgrade head"
"$VENV/alembic" upgrade head

echo "[entrypoint] serve on ${SERVE_HOST}:${SERVE_PORT} (no auth, no TLS -- ADR-011)"
exec "$VENV/python" -m compendium serve --host "$SERVE_HOST" --port "$SERVE_PORT"
