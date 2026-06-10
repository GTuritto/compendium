#!/usr/bin/env bash
# Cut a new Compendium distribution version in one command.
#
#   ./release.sh <version> [--commit] [--no-build]
#   ./release.sh 0.2.4
#
# Steps:
#   1. Validate the version (semver: X.Y.Z, optional -suffix).
#   2. Write the canonical VERSION file and the pyproject.toml mirror.
#   3. Refresh uv.lock (so the project's own version follows).
#   4. Insert a dated CHANGELOG.md section stub for the new version.
#   5. Rebuild the distribution bundle (deploy/make-bundle.sh) unless --no-build.
#   6. Optionally git-commit the bump (--commit); otherwise leave it for review.
#
# VERSION is the single source of truth; compendium.__version__ reads it and the
# FastAPI access-surface version derives from it. macOS + Linux; no GNU-only deps.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

VERSION=""
DO_COMMIT=0
DO_BUILD=1
while [ $# -gt 0 ]; do
  case "$1" in
    --commit)   DO_COMMIT=1; shift ;;
    --no-build) DO_BUILD=0; shift ;;
    -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -n 16; exit 0 ;;
    -*)         die "unknown flag: $1" ;;
    *)          [ -z "$VERSION" ] && VERSION="$1" || die "unexpected arg: $1"; shift ;;
  esac
done

[ -n "$VERSION" ] || die "usage: ./release.sh <version> [--commit] [--no-build]"
# Strip a leading 'v' if the operator typed v0.2.4.
VERSION="${VERSION#v}"
case "$VERSION" in
  [0-9]*.[0-9]*.[0-9]*) : ;;
  *) die "version must be semver X.Y.Z (optionally with -suffix): got '$VERSION'" ;;
esac

[ -f "$ROOT/VERSION" ] || die "no VERSION file — run from the repo root."
[ -f "$ROOT/pyproject.toml" ] || die "no pyproject.toml — run from the repo root."
CURRENT="$(tr -d '[:space:]' < "$ROOT/VERSION")"
say "Releasing $CURRENT -> $VERSION"
[ "$CURRENT" = "$VERSION" ] && warn "VERSION is already $VERSION (continuing — re-stamping)."

# Refuse to clobber an in-progress release on a dirty tree unless committing is
# explicitly deferred to the operator (the default). Just inform.
if [ -n "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ]; then
  warn "working tree is not clean; the bump will be added on top of existing changes."
fi

# 1. VERSION (canonical) ----------------------------------------------------
printf '%s\n' "$VERSION" > "$ROOT/VERSION"
say "VERSION -> $VERSION"

# 2. pyproject.toml mirror (first `version = \"...\"` line) ------------------
awk -v v="$VERSION" 'BEGIN{d=0} /^version = "/ && !d {print "version = \"" v "\""; d=1; next} {print}' \
  "$ROOT/pyproject.toml" > "$ROOT/pyproject.toml.tmp" && mv "$ROOT/pyproject.toml.tmp" "$ROOT/pyproject.toml"
say "pyproject.toml mirror -> $VERSION"

# 3. uv.lock (project's own version) ---------------------------------------
if command -v uv >/dev/null 2>&1; then
  uv lock >/dev/null 2>&1 && say "uv.lock refreshed" || warn "uv lock failed — refresh uv.lock manually."
else
  warn "uv not found — uv.lock not refreshed (it records the project version)."
fi

# 4. CHANGELOG.md section stub ---------------------------------------------
DATE="$(date -u +%Y-%m-%d)"
if [ -f "$ROOT/CHANGELOG.md" ]; then
  if grep -q "^## \[$VERSION\]" "$ROOT/CHANGELOG.md"; then
    warn "CHANGELOG already has a [$VERSION] section — leaving it."
  else
    # Insert a new dated section before the first existing versioned section
    # (i.e. just below the [Unreleased] block).
    awk -v v="$VERSION" -v d="$DATE" '
      /^## \[/ && $0 !~ /\[Unreleased\]/ && !ins {
        print "## [" v "] - " d
        print ""
        print "- _Describe the changes in this release._"
        print ""
        ins=1
      }
      { print }
      END { if (!ins) {
        print ""
        print "## [" v "] - " d
        print ""
        print "- _Describe the changes in this release._"
      } }
    ' "$ROOT/CHANGELOG.md" > "$ROOT/CHANGELOG.md.tmp" && mv "$ROOT/CHANGELOG.md.tmp" "$ROOT/CHANGELOG.md"
    # Link reference at the bottom (best-effort; harmless if the repo URL differs).
    printf '[%s]: https://github.com/GTuritto/compendium/releases/tag/v%s\n' "$VERSION" "$VERSION" >> "$ROOT/CHANGELOG.md"
    say "CHANGELOG.md — added [$VERSION] - $DATE stub (edit it before committing)"
  fi
else
  warn "no CHANGELOG.md — skipped."
fi

# 5. Build the distribution -------------------------------------------------
if [ "$DO_BUILD" -eq 1 ]; then
  say "Rebuilding the distribution bundle"
  "$ROOT/deploy/make-bundle.sh"
else
  say "Skipping bundle build (--no-build)"
fi

# 6. Commit (optional) ------------------------------------------------------
if [ "$DO_COMMIT" -eq 1 ]; then
  say "Committing the version bump"
  git -C "$ROOT" add VERSION pyproject.toml uv.lock CHANGELOG.md 2Deploy 2>/dev/null || true
  git -C "$ROOT" commit -q -m "chore(release): v$VERSION" \
    -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
    && say "committed: chore(release): v$VERSION"
fi

echo
say "Done — v$VERSION"
echo "  Runtime check:  uv run python -c 'import compendium; print(compendium.__version__)'"
[ "$DO_COMMIT" -eq 0 ] && echo "  Next: edit the CHANGELOG.md [$VERSION] stub, then commit (or re-run with --commit)."
echo "  Distribution:   2Deploy/install.sh + 2Deploy/compendium-deploy.zip"
