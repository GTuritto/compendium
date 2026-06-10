#!/usr/bin/env bash
# Compendium — interactive installer (manual CD).
#
# Distributed as TWO files that sit side by side:
#   install.sh                 <- this script (download + run it)
#   compendium-deploy.zip      <- the payload bundle
#
# It unzips the bundle into an install directory, asks the operator how to run
# Compendium (host-native via uv, or as a Docker app image), provisions the four
# backing stores with Docker, interactively collects configuration (endpoints,
# API keys, paths, bind address) into a .env file, loads dependencies, applies
# migrations, builds the derived indexes, and starts the services.
#
# macOS and Linux. Bash 3.2 compatible (no associative arrays / no ${v,,}).
# Localhost / single-user / no-auth posture (ADR-011, ADR-012).
#
# Usage:  ./install.sh [--zip <path>] [--dir <install-dir>]
set -euo pipefail

# ---------------------------------------------------------------------------
# Pretty output (all human-facing text goes to the TTY so piped stdin is fine).
# ---------------------------------------------------------------------------
if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B=; G=; Y=; R=; N=; fi

# Resolve an interactive terminal. Prompts go to the real TTY so the script also
# works under `curl ... | bash` (where stdin is the script). If there is no
# controlling terminal (CI, --help in a sandbox), fall back to std streams
# instead of crashing.
if { : > /dev/tty; } 2>/dev/null; then TTYOUT=/dev/tty; TTYIN=/dev/tty; else TTYOUT=/dev/stderr; TTYIN=/dev/stdin; fi

say()  { printf '\n%s==> %s%s\n' "$B" "$*" "$N" > "$TTYOUT"; }
info() { printf '    %s\n' "$*" > "$TTYOUT"; }
warn() { printf '%s[warn]%s %s\n' "$Y" "$N" "$*" > "$TTYOUT"; }
die()  { printf '%s[error]%s %s\n' "$R" "$N" "$*" > "$TTYOUT"; exit 1; }

# Prompt helpers. Read from /dev/tty so they work even under `curl ... | bash`.
ask() { # ask VARNAME "prompt" "default"
  local __var="$1" __prompt="$2" __default="${3:-}" __reply=""
  if [ -n "$__default" ]; then printf '%s [%s]: ' "$__prompt" "$__default" > "$TTYOUT"
  else printf '%s: ' "$__prompt" > "$TTYOUT"; fi
  IFS= read -r __reply < "$TTYIN" || __reply=""
  [ -z "$__reply" ] && __reply="$__default"
  eval "$__var=\$__reply"
}
ask_secret() { # ask_secret VARNAME "prompt"
  local __var="$1" __prompt="$2" __reply=""
  printf '%s: ' "$__prompt" > "$TTYOUT"
  IFS= read -rs __reply < "$TTYIN" || __reply=""
  printf '\n' > "$TTYOUT"
  eval "$__var=\$__reply"
}
ask_yn() { # ask_yn "prompt" "Y|N"  -> returns 0 for yes
  local __prompt="$1" __default="${2:-Y}" __reply=""
  local __hint="[Y/n]"; [ "$__default" = "N" ] && __hint="[y/N]"
  printf '%s %s ' "$__prompt" "$__hint" > "$TTYOUT"
  IFS= read -r __reply < "$TTYIN" || __reply=""
  [ -z "$__reply" ] && __reply="$__default"
  case "$(printf '%s' "$__reply" | tr '[:upper:]' '[:lower:]')" in y|yes) return 0 ;; *) return 1 ;; esac
}

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZIP=""
INSTALL_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --zip) ZIP="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    -h|--help) { grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -n 20 || true; } > "$TTYOUT"; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

say "Compendium installer"
OS="$(uname)"
case "$OS" in Darwin) info "Detected macOS." ;; Linux) info "Detected Linux." ;; *) die "Unsupported OS: $OS (macOS or Linux only)." ;; esac

# ---------------------------------------------------------------------------
# 1. Locate and extract the bundle
# ---------------------------------------------------------------------------
command -v unzip >/dev/null 2>&1 || die "'unzip' is required. Install it (macOS: preinstalled; Debian/Ubuntu: sudo apt install unzip)."
if [ -z "$ZIP" ]; then
  if [ -f "$SCRIPT_DIR/compendium-deploy.zip" ]; then ZIP="$SCRIPT_DIR/compendium-deploy.zip"
  else die "compendium-deploy.zip not found next to install.sh. Pass it with --zip <path>."; fi
fi
[ -f "$ZIP" ] || die "zip not found: $ZIP"

[ -z "$INSTALL_DIR" ] && ask INSTALL_DIR "Install directory" "$HOME/compendium"
# Expand a leading ~ portably.
case "$INSTALL_DIR" in "~"/*) INSTALL_DIR="$HOME/${INSTALL_DIR#~/}" ;; "~") INSTALL_DIR="$HOME" ;; esac
mkdir -p "$INSTALL_DIR"

say "Extracting bundle into $INSTALL_DIR"
unzip -q -o "$ZIP" -d "$INSTALL_DIR"
# The bundle is a single top-level folder (compendium-deploy/).
APP_DIR="$INSTALL_DIR/compendium-deploy"
[ -d "$APP_DIR" ] || APP_DIR="$INSTALL_DIR"
[ -f "$APP_DIR/pyproject.toml" ] || die "extracted bundle looks wrong (no pyproject.toml in $APP_DIR)."
cd "$APP_DIR"
info "App directory: $APP_DIR"
info "Version: $(cat VERSION 2>/dev/null || echo unknown)"

# ---------------------------------------------------------------------------
# 2. Docker (required for the backing stores in both modes)
# ---------------------------------------------------------------------------
say "Checking Docker (needed for the backing stores)"
command -v docker >/dev/null 2>&1 || die "Docker is not installed. Install Docker Desktop (macOS) or Docker Engine (Linux) first."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required (the 'docker compose' subcommand)."
docker info >/dev/null 2>&1 || die "The Docker daemon is not running (or this user lacks access). Start Docker and re-run."
info "Docker OK."

# ---------------------------------------------------------------------------
# 3. Deployment mode
# ---------------------------------------------------------------------------
say "Choose how to run the Compendium application"
info "1) Host-native (uv)   — run on this host with uv; install launchd/systemd services. Best on macOS."
info "2) Docker app image   — build a container and run it with docker compose. Best for a headless LAN server."
MODE=""
while [ "$MODE" != "host" ] && [ "$MODE" != "docker" ]; do
  ask _m "Select [1=host-native, 2=docker-image]" "1"
  case "$_m" in 1|host|host-native) MODE="host" ;; 2|docker|docker-image) MODE="docker" ;; *) warn "enter 1 or 2" ;; esac
done
info "Mode: $MODE"

# Store URLs differ by mode: host reaches published localhost ports; the
# container reaches stores by service name on the internal compose network.
if [ "$MODE" = "host" ]; then
  DEF_PG="postgresql://compendium:compendium@localhost:5432/compendium"
  DEF_OS="http://localhost:9200"; DEF_QD="http://localhost:6533"; DEF_MG="bolt://localhost:7688"
else
  DEF_PG="postgresql://compendium:compendium@postgres:5432/compendium"
  DEF_OS="http://opensearch:9200"; DEF_QD="http://qdrant:6333"; DEF_MG="bolt://memgraph:7687"
fi

# ---------------------------------------------------------------------------
# 4. uv (host-native only)
# ---------------------------------------------------------------------------
if [ "$MODE" = "host" ]; then
  if ! command -v uv >/dev/null 2>&1; then
    warn "'uv' is not installed (https://docs.astral.sh/uv/)."
    if ask_yn "Install uv now via the official script?" "Y"; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
      # uv installs to ~/.local/bin or ~/.cargo/bin
      export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
      command -v uv >/dev/null 2>&1 || die "uv still not on PATH; open a new shell and re-run, or install uv manually."
    else
      die "uv is required for host-native mode. Install it and re-run."
    fi
  fi
  info "uv: $(uv --version 2>/dev/null || echo present)"
fi

# ---------------------------------------------------------------------------
# 5. Interactive configuration -> .env
# ---------------------------------------------------------------------------
say "Configuration"
if [ -f .env ] && ! ask_yn "A .env already exists. Overwrite it?" "N"; then
  info "Keeping existing .env."
else
  info "OpenRouter is the cloud default for synthesis + embeddings. For a local Docker Model Runner, point the endpoints at DMR and leave keys blank."
  ask SYNTHESIS_ENDPOINT "Synthesis endpoint" "https://openrouter.ai/api/v1"
  ask SYNTHESIS_MODEL    "Synthesis model"    "anthropic/claude-sonnet-4.5"
  OPENROUTER_API_KEY=""
  case "$SYNTHESIS_ENDPOINT" in *openrouter*) ask_secret OPENROUTER_API_KEY "OpenRouter API key (synthesis)" ;; esac

  ask EMBEDDINGS_ENDPOINT "Embeddings endpoint" "https://openrouter.ai/api/v1"
  ask EMBED_MODEL         "Embeddings model"    "BAAI/bge-m3"
  EMBEDDINGS_API_KEY=""
  case "$EMBEDDINGS_ENDPOINT" in
    *openrouter*)
      if [ -n "$OPENROUTER_API_KEY" ] && ask_yn "Use the same key for embeddings?" "Y"; then
        EMBEDDINGS_API_KEY="$OPENROUTER_API_KEY"
      else
        ask_secret EMBEDDINGS_API_KEY "Embeddings API key"
      fi ;;
  esac

  if [ "$MODE" = "host" ]; then
    VAULT_PATH="$APP_DIR/vault"
    ask SERVE_HOST "Access-surface bind host" "127.0.0.1"
    ask SERVE_PORT "Access-surface port" "8787"
    BIND_HOST="$SERVE_HOST"
  else
    VAULT_PATH="/app/vault"
    info "Docker mode publishes the access surface on BIND_HOST. Use this server's LAN IP (or 127.0.0.1 for local-only)."
    ask BIND_HOST "BIND_HOST (published interface)" "127.0.0.1"
    SERVE_HOST="0.0.0.0"; SERVE_PORT="8787"
  fi

  ask BACKUP_LOCAL_DIR "Local backup directory" "$APP_DIR/backups"
  ask BACKUP_RSYNC_DEST "Off-host rsync destination (optional, blank to skip)" ""
  ask INBOX_PATH "Inbox directory (auto-ingest)" "$HOME/Compendium/inbox"

  say "Writing .env"
  umask 077
  cat > .env <<EOF
# Generated by install.sh on $(date -u '+%Y-%m-%dT%H:%M:%SZ') (mode: $MODE)
# Secrets live here; never commit this file.

# --- Storage backends ---
POSTGRES_URL=$DEF_PG
OPENSEARCH_URL=$DEF_OS
QDRANT_URL=$DEF_QD
MEMGRAPH_URL=$DEF_MG

# --- Vault ---
VAULT_PATH=$VAULT_PATH

# --- Synthesis LLM ---
SYNTHESIS_ENDPOINT=$SYNTHESIS_ENDPOINT
SYNTHESIS_MODEL=$SYNTHESIS_MODEL
OPENROUTER_API_KEY=$OPENROUTER_API_KEY

# --- Embeddings ---
EMBEDDINGS_ENDPOINT=$EMBEDDINGS_ENDPOINT
EMBED_MODEL=$EMBED_MODEL
EMBEDDINGS_API_KEY=$EMBEDDINGS_API_KEY

# --- Access surface ---
BIND_HOST=$BIND_HOST
SERVE_HOST=$SERVE_HOST
SERVE_PORT=$SERVE_PORT

# --- Backup ---
BACKUP_LOCAL_DIR=$BACKUP_LOCAL_DIR
BACKUP_RSYNC_DEST=$BACKUP_RSYNC_DEST

# --- Inbox ---
INBOX_PATH=$INBOX_PATH
EOF
  umask 022
  info ".env written (permissions 600)."
fi

# Re-read the bind values from .env so the rest of the script works whether or
# not .env was just regenerated.
SERVE_HOST="$(grep -E '^SERVE_HOST=' .env | head -1 | cut -d= -f2-)"; [ -z "$SERVE_HOST" ] && SERVE_HOST="127.0.0.1"
SERVE_PORT="$(grep -E '^SERVE_PORT=' .env | head -1 | cut -d= -f2-)"; [ -z "$SERVE_PORT" ] && SERVE_PORT="8787"
BIND_HOST="$(grep -E '^BIND_HOST=' .env | head -1 | cut -d= -f2-)";  [ -z "$BIND_HOST" ] && BIND_HOST="127.0.0.1"

# ---------------------------------------------------------------------------
# 6. Provision + finish, per mode
# ---------------------------------------------------------------------------
wait_http() { # wait_http URL LABEL
  local url="$1" label="$2" i
  for i in $(seq 1 60); do curl -fsS -o /dev/null --max-time 2 "$url" && return 0; sleep 2; done
  warn "$label not reachable at $url after 120s"; return 1
}

if [ "$MODE" = "host" ]; then
  mkdir -p "$APP_DIR/vault/concepts" "$APP_DIR/vault/topics" "$APP_DIR/vault/sources" "$BACKUP_LOCAL_DIR"

  say "Loading dependencies (uv sync)"
  uv sync

  say "Starting backing stores (docker compose -f docker-compose.stores.yml up -d)"
  docker compose -f docker-compose.stores.yml up -d
  say "Waiting for stores"
  for i in $(seq 1 60); do docker compose -f docker-compose.stores.yml exec -T postgres pg_isready -U compendium >/dev/null 2>&1 && break; sleep 2; done
  wait_http "http://localhost:9200" "OpenSearch" || true
  wait_http "http://localhost:6533/collections" "Qdrant" || true

  say "Applying migrations (alembic upgrade head)"
  uv run alembic upgrade head
  say "Building derived indexes (reindex all + graph rebuild)"
  uv run python -m compendium reindex all
  uv run python -m compendium graph rebuild || warn "graph rebuild failed (Memgraph down?) — non-fatal"

  if [ "$OS" = "Linux" ]; then
    loginctl enable-linger "$USER" 2>/dev/null && info "systemd lingering enabled ($USER)" \
      || warn "could not enable lingering; run 'sudo loginctl enable-linger $USER' for 24/7 without a login session."
  fi

  say "Installing always-on services (backup, schedule, inbox, serve)"
  uv run python -m compendium backup install   || warn "backup install failed"
  uv run python -m compendium schedule install  || warn "schedule install failed"
  uv run python -m compendium inbox install      || warn "inbox install failed"
  uv run python -m compendium serve install --host "$SERVE_HOST" --port "$SERVE_PORT" || warn "serve install failed"

  say "Done — host-native install complete."
  info "Access surface: http://$SERVE_HOST:$SERVE_PORT   (localhost, no auth — ADR-011)"
  info "Load data:  cd $APP_DIR && uv run python -m compendium ingest <path-or-url> --kind <kind>"
  info "Health:     curl http://$SERVE_HOST:$SERVE_PORT/index_status"
  info "Stores:     docker compose -f docker-compose.stores.yml {ps|stop|start}"
else
  say "Building image and starting the full stack (docker compose up -d --build)"
  docker compose up -d --build
  say "Done — Docker install complete."
  info "Access surface: http://$BIND_HOST:8787"
  if [ "$BIND_HOST" != "127.0.0.1" ]; then
    warn "BIND_HOST is $BIND_HOST and there is NO auth. Firewall port 8787 to your consumer machine only (see DEPLOY.md)."
  fi
  info "Manage with: cd $APP_DIR && ./compendiumctl {start|stop|status|restart|logs|update}"
  info "Load data:   ./compendiumctl ingest <path-or-url> --kind <kind>"
fi
