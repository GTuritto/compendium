#!/usr/bin/env bash
# One-shot installer for the Compendium production bundle.
# Copy this whole folder to the server, then run: ./install.sh
set -euo pipefail
cd "$(dirname "$0")"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m[warn] %s\033[0m\n' "$*"; }
die()  { printf '\033[31m[error] %s\033[0m\n' "$*" >&2; exit 1; }

say "Checking Docker"
command -v docker >/dev/null 2>&1 || die "Docker is not installed. Install Docker Engine first."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required (the 'docker compose' subcommand)."
docker info >/dev/null 2>&1 || die "Docker daemon is not running or this user lacks access. Start Docker / add the user to the 'docker' group."

if [ ! -f .env ]; then
  cp .env.example .env
  say "Created .env from .env.example"
  warn "Edit .env now:"
  warn "  - BIND_HOST: set to this server's LAN IP (e.g. 192.168.35.70)"
  warn "  - OPENROUTER_API_KEY / EMBEDDINGS_API_KEY: needed for ingest and 'ask'"
  warn "Then re-run ./install.sh"
  exit 0
fi

say "Building image and starting the stack"
docker compose up -d --build

BIND_HOST="$(grep -E '^BIND_HOST=' .env | head -1 | cut -d= -f2- || true)"
[ -z "${BIND_HOST}" ] && BIND_HOST="0.0.0.0"

say "Compendium is up"
echo "Access surface (REST): http://${BIND_HOST}:8787"
echo
echo "Next steps:"
echo "  1. If BIND_HOST is 0.0.0.0 or a LAN IP, add a firewall rule so only your"
echo "     consumer machine can reach port 8787 (no auth exists). See DEPLOY.md."
echo "  2. Load data:  ./compendiumctl ingest <path-or-url> --kind <kind>"
echo "  3. Health:     curl http://${BIND_HOST}:8787/index_status"
echo
echo "Manage with: ./compendiumctl {start|stop|restart|status|logs|update}"
