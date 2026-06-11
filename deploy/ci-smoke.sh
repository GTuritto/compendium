#!/usr/bin/env bash
# CI smoke gate: every CI-runnable layer of tests/manual/smoke_test.md, scripted.
#
#   deploy/ci-smoke.sh            # assumes stores reachable + env configured
#
# Layers (mirrors the playbook's method):
#   1. the full pytest suite including the golden tier (the definitive gate),
#   2. a deterministic end-to-end CLI walk with the profilers ON
#      (ingest -> wiki -> indexes -> retrieval -> graph -> traces -> curation
#       -> ask -> profile stats -> CPU/span profiling -> inbox processing),
#   3. the access surface over HTTP (all six verbs + streaming + the
#      SIGUSR1/SIGUSR2 memory profiler against the live daemon),
#   4. a backup pair (when pg_dump is available).
#
# Deliberately NOT here (documented in the playbook as manual/host-bound):
# launchd/systemd unit installs, the interactive TUI walk (its headless Pilot
# suite runs inside layer 1), the live real-model tier (never in CI), and the
# destructive restore round-trip.
#
# The walk ingests the test fixtures into whatever POSTGRES_URL points at —
# fine for CI service containers and for a dev stack, like the manual playbook.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export COMPENDIUM_PROFILE=1
export COMPENDIUM_EMBED_STUB=1
export COMPENDIUM_SYNTH_STUB=1
export COMPENDIUM_PROFILE_DIR="${COMPENDIUM_PROFILE_DIR:-$(mktemp -d)}"

PORT="${SMOKE_SERVE_PORT:-8799}"
C="uv run python -m compendium"
FAIL=0
STEP=""

say()  { printf '\033[1m==> %s\033[0m\n' "$*"; }
pass() { printf '  \033[32mpass\033[0m %s\n' "$STEP"; }
fail() { printf '  \033[31mFAIL\033[0m %s: %s\n' "$STEP" "$*"; FAIL=1; }
need() { STEP="$1"; shift; if "$@"; then pass; else fail "assertion failed"; fi; }

# --- layer 0: migrate the ambient database (the suite's integration tests
# that target the dev DB assume it is migrated, like a dev checkout) ----------
say "layer 0: migrate the ambient database"
uv run alembic upgrade head >/dev/null

# --- layer 1: the full test suite (incl. golden) ---------------------------
say "layer 1: full pytest suite (incl. golden tier), profilers on"
uv run pytest -q -p no:cacheprovider

# --- layer 2: deterministic CLI walk ----------------------------------------
say "layer 2: end-to-end CLI walk"

STEP="config validates (cold start)"
$C >/dev/null 2>&1 && pass || fail "non-zero exit"

STEP="migrations to head"
uv run alembic upgrade head >/dev/null 2>&1 && pass || fail "alembic failed"

STEP="ingest a PDF (stored)"
OUT=$($C ingest tests/fixtures/sample.pdf --kind paper 2>/dev/null)
grep -q "1 stored\|1 unchanged" <<<"$OUT" && pass || fail "$OUT"

STEP="re-ingest is idempotent (unchanged)"
OUT=$($C ingest tests/fixtures/sample.pdf --kind paper 2>/dev/null)
grep -q "1 unchanged" <<<"$OUT" && pass || fail "$OUT"

STEP="broken source fails without crashing"
OUT=$($C ingest tests/fixtures/broken.pdf --kind paper 2>/dev/null)
grep -q "1 failed\|1 unchanged" <<<"$OUT" && pass || fail "$OUT"

STEP="authored provenance (--mine)"
OUT=$($C ingest tests/fixtures/sample.md --kind note --mine 2>/dev/null)
grep -q "stored\|unchanged" <<<"$OUT" && pass || fail "$OUT"

STEP="directory ingest handles every file"
OUT=$($C ingest tests/fixtures/ 2>/dev/null)
grep -q "5 source(s)" <<<"$OUT" && pass || fail "$OUT"

need "pages build exits clean" sh -c "$C pages build >/dev/null 2>&1"
need "lint is clean" sh -c "$C lint >/dev/null 2>&1"

STEP="stub concept synthesis"
$C synth concept "psychological safety" >/dev/null 2>&1 \
  && grep -q "## Grounding" vault/concepts/psychological-safety.md && pass || fail "no grounded page"

need "reindex all" sh -c "$C reindex all >/dev/null 2>&1"

STEP="index status reports counts"
OUT=$($C index status 2>/dev/null)
grep -q "opensearch/pages" <<<"$OUT" && pass || fail "$OUT"

STEP="covered query, no fallback"
OUT=$($C query "psychological safety" 2>/dev/null)
grep -q "coverage 0\.[1-9]\|coverage 1\." <<<"$OUT" && ! grep -q "chunk fallback" <<<"$OUT" && pass || fail "$OUT"

STEP="timed spans fire (--timings)"
SPANS=$($C --timings query "psychological safety" 2>&1 >/dev/null | grep -c '"event": "profile"' || true)
[ "$SPANS" -ge 1 ] && pass || fail "no profile events on stderr"

STEP="query JSON contract"
$C query "psychological safety" --format json 2>/dev/null | uv run python -c "
import sys, json
d = json.load(sys.stdin)
assert all(k in d for k in ('query','coverage_score','fallback_to_chunks','pages','citations','gaps')), d.keys()
assert d['pages']
" && pass || fail "missing keys or empty pages"

need "graph rebuild" sh -c "$C graph rebuild >/dev/null 2>&1"

STEP="graph status shows structural edges"
OUT=$($C graph status 2>/dev/null)
grep -qE "GROUNDS: [1-9]" <<<"$OUT" && pass || fail "$OUT"

STEP="trace list + replay"
TRACE=$($C trace list 2>/dev/null | head -1 | awk '{print $1}')
[ -n "$TRACE" ] && $C trace replay "$TRACE" >/dev/null 2>&1 && pass || fail "no trace or replay failed"

STEP="promote to canonical (idempotence rejected)"
$C page promote psychological-safety --to canonical >/dev/null 2>&1 || true
if $C page promote psychological-safety --to canonical >/dev/null 2>&1; then fail "re-promote accepted"; else pass; fi

need "curate run (signals + extraction)" sh -c "$C curate run >/dev/null 2>&1"

STEP="ask composes with citations (stub)"
OUT=$($C ask "What is psychological safety?" 2>/dev/null)
grep -q "citations:" <<<"$OUT" && pass || fail "$OUT"

STEP="ask JSON contract"
$C ask "What is psychological safety?" --format json 2>/dev/null | uv run python -c "
import sys, json
d = json.load(sys.stdin)
assert all(k in d for k in ('answer','refused','citations','coverage_score','trace_id','ask_trace_id','gap','suggested_actions')), d.keys()
" && pass || fail "missing keys"

STEP="profile stats aggregates the walk"
OUT=$($C profile stats --days 1 2>/dev/null)
grep -q "retrieval:" <<<"$OUT" && grep -q "ingest.parse" <<<"$OUT" && pass || fail "$OUT"

STEP="profile stats JSON"
$C profile stats --days 1 --format json 2>/dev/null | uv run python -c "import sys,json; json.load(sys.stdin)" \
  && pass || fail "not one JSON object"

STEP="--profile writes a loadable cProfile artifact"
$C --profile index status >/dev/null 2>&1
PROF=$(ls -t "$COMPENDIUM_PROFILE_DIR"/index-*.prof 2>/dev/null | head -1)
[ -n "$PROF" ] && uv run python -c "import pstats; assert pstats.Stats('$PROF').total_calls > 0" \
  && pass || fail "no artifact"

# --- layer 2b: inbox processing (no watcher unit; the worker itself) --------
STEP="inbox process routes good + bad files"
INBOX=$(mktemp -d)
mkdir -p "$INBOX"/{book,article,paper,note,web,processed,failed}
cp tests/fixtures/sample.epub "$INBOX/book/"
echo "NOT-A-PDF-$(date +%s)" > "$INBOX/paper/garbage.pdf"
OUT=$($C inbox process --path "$INBOX" 2>/dev/null)
TODAY=$(date -u +%Y-%m-%d)
{ ls "$INBOX/processed/$TODAY/" 2>/dev/null | grep -q "sample.epub" || grep -q "processed=0" <<<"$OUT"; } \
  && ls "$INBOX/failed/$TODAY/" | grep -q "garbage.pdf.error" && pass || fail "$OUT"
rm -rf "$INBOX"

# --- layer 3: the access surface + the memory profiler ----------------------
say "layer 3: HTTP access surface + SIGUSR memory profiler (port $PORT)"
$C serve --port "$PORT" >/tmp/ci-smoke-serve.log 2>&1 &
SERVE_WRAPPER=$!
trap 'kill $SERVE_WRAPPER 2>/dev/null || true' EXIT
for i in $(seq 1 30); do curl -sf "127.0.0.1:$PORT/index_status" >/dev/null && break; sleep 1; done

STEP="serve: index_status"
curl -sf "127.0.0.1:$PORT/index_status" | grep -q "opensearch" && pass || fail "no report"

STEP="serve: query"
curl -sf -XPOST "127.0.0.1:$PORT/query" -H 'content-type: application/json' \
  -d '{"text":"psychological safety"}' | grep -q '"pages"' && pass || fail "no pages"

STEP="serve: ingest base64 + auto-sync"
B64=$(printf '# CI Smoke Note\n\nA note ingested over the access surface during the CI smoke.' | base64 | tr -d '\n')
curl -sf -XPOST "127.0.0.1:$PORT/ingest" -H 'content-type: application/json' \
  -d "{\"kind\":\"note\",\"filename\":\"ci-smoke.md\",\"content_base64\":\"$B64\"}" \
  | grep -qE '"status": ?"(ingested|unchanged|updated)"' && pass || fail "ingest over HTTP failed"

STEP="serve: ask + streaming final envelope"
curl -sf -XPOST "127.0.0.1:$PORT/ask" -H 'content-type: application/json' \
  -d '{"question":"What is psychological safety?"}' | grep -q '"citations"' || fail "buffered ask"
curl -sfN -XPOST "127.0.0.1:$PORT/ask/stream" -H 'content-type: application/json' \
  -d '{"question":"What is psychological safety?"}' | tail -1 | grep -q '"ask_trace_id"' && pass || fail "stream envelope"

STEP="serve: page_list / page_get / 404"
SLUG=$(curl -sf "127.0.0.1:$PORT/page_list?kind=source" | uv run python -c "import sys,json; print(json.load(sys.stdin)[0]['slug'])")
curl -sf "127.0.0.1:$PORT/page_get?kind=source&slug=$SLUG" | grep -q '"markdown"' || fail "page_get"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "127.0.0.1:$PORT/page_get?kind=source&slug=no-such-slug")
[ "$CODE" = "404" ] && pass || fail "expected 404, got $CODE"

STEP="memory profiler: SIGUSR1 arm / SIGUSR2 report, daemon undisturbed"
SERVE_PID=$(pgrep -f "[p]ython.*-m compendium serve --port $PORT" | head -1 || echo "$SERVE_WRAPPER")
kill -USR1 "$SERVE_PID"; sleep 1
curl -sf -XPOST "127.0.0.1:$PORT/query" -H 'content-type: application/json' -d '{"text":"safety"}' >/dev/null
kill -USR2 "$SERVE_PID"; sleep 2
MEM=$(ls -t "$COMPENDIUM_PROFILE_DIR"/mem-*.txt 2>/dev/null | head -1)
[ -n "$MEM" ] && grep -q "allocation growth" "$MEM" \
  && curl -sf "127.0.0.1:$PORT/index_status" >/dev/null && pass || fail "no mem report or daemon hurt"

kill "$SERVE_WRAPPER" 2>/dev/null || true
trap - EXIT

# --- layer 4: backup pair (when pg_dump is available) ------------------------
if command -v pg_dump >/dev/null 2>&1; then
  STEP="backup writes the dump + vault pair"
  BK=$(mktemp -d)
  BACKUP_LOCAL_DIR="$BK" BACKUP_RSYNC_DEST= $C backup >/dev/null 2>&1
  TS=$(ls "$BK" | head -1)
  [ -s "$BK/$TS/compendium.dump" ] && [ -s "$BK/$TS/vault.tar.gz" ] && pass || fail "pair missing"
  rm -rf "$BK"
else
  say "layer 4: pg_dump not on PATH — backup smoke skipped"
fi

# --- verdict -----------------------------------------------------------------
if [ "$FAIL" -ne 0 ]; then
  say "CI SMOKE: FAILED"
  exit 1
fi
say "CI SMOKE: ALL GREEN"
