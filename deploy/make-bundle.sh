#!/usr/bin/env bash
# Assemble a self-contained production deployment bundle (folder + zip) that can
# be copied to a personal LAN server and installed with one script.
#
#   ./deploy/make-bundle.sh [output-dir]
#
# Default output: ./2Deploy/  (contains compendium-deploy/ and the .zip)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/2Deploy}"
NAME="compendium-deploy"
STAGE="$OUT/$NAME"

echo "==> Staging bundle at $STAGE"
rm -rf "$OUT"
mkdir -p "$STAGE"

copy() {  # copy a tree, excluding python caches
  rsync -a --exclude '__pycache__' --exclude '*.py[cod]' "$1" "$2"
}

echo "==> Copying application source"
copy "$ROOT/compendium" "$STAGE/"
copy "$ROOT/migrations" "$STAGE/"
copy "$ROOT/config" "$STAGE/"
cp "$ROOT/alembic.ini" "$ROOT/pyproject.toml" "$ROOT/uv.lock" "$ROOT/README.md" "$STAGE/"
# VERSION is the canonical version source (compendium.__version__ reads it at the
# bundle root); CHANGELOG.md ships alongside it.
cp "$ROOT/VERSION" "$STAGE/"
[ -f "$ROOT/CHANGELOG.md" ] && cp "$ROOT/CHANGELOG.md" "$STAGE/"

echo "==> Copying container + orchestration"
cp "$ROOT/deploy/Dockerfile" "$STAGE/"
# The single Dockerfile does `COPY deploy/entrypoint.sh`, so keep it under
# deploy/ here (the Dockerfile then builds identically in-repo and in-bundle).
mkdir -p "$STAGE/deploy"
cp "$ROOT/deploy/entrypoint.sh" "$STAGE/deploy/"
cp "$ROOT/deploy/bundle/docker-compose.yml" "$STAGE/"
# Stores-only compose (publishes localhost ports) for the host-native install
# mode; the dev compose is exactly that.
cp "$ROOT/docker-compose.yml" "$STAGE/docker-compose.stores.yml"
cp "$ROOT/deploy/.env.lan.example" "$STAGE/.env.example"

echo "==> Copying install + lifecycle scripts"
cp "$ROOT/deploy/bundle/install.sh" "$STAGE/"
cp "$ROOT/deploy/bundle/compendiumctl" "$STAGE/"
cp "$ROOT/deploy/bundle/uninstall.sh" "$STAGE/"
cp "$ROOT/deploy/bundle/DEPLOY.md" "$STAGE/"
chmod +x "$STAGE/install.sh" "$STAGE/compendiumctl" "$STAGE/uninstall.sh" "$STAGE/deploy/entrypoint.sh"

echo "==> Copying documentation"
mkdir -p "$STAGE/docs"
[ -d "$ROOT/docs/operations" ] && copy "$ROOT/docs/operations" "$STAGE/docs/"
[ -d "$ROOT/docs/architecture" ] && copy "$ROOT/docs/architecture" "$STAGE/docs/"

echo "==> Writing bundle manifest"
{
  echo "Compendium deployment bundle"
  echo "Built from compendium v$(cat "$ROOT/VERSION" 2>/dev/null | tr -d '[:space:]')"
  echo "Source commit: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo
  echo "Install: copy this folder to the server and run ./install.sh"
  echo "See DEPLOY.md for full instructions."
} > "$STAGE/MANIFEST.txt"

if command -v zip >/dev/null 2>&1; then
  echo "==> Zipping"
  ( cd "$OUT" && zip -rq "$NAME.zip" "$NAME" )
  echo "Zip:    $OUT/$NAME.zip"
else
  echo "[warn] 'zip' not found; folder produced, no archive."
fi

echo "==> Placing the interactive installer beside the zip"
# The two distribution artifacts: install.sh (this) + compendium-deploy.zip.
# Operators download both, then run ./install.sh.
cp "$ROOT/deploy/installer.sh" "$OUT/install.sh"
chmod +x "$OUT/install.sh"
echo "Installer: $OUT/install.sh"

echo "Folder: $STAGE"
echo "Done."
