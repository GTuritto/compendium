#!/usr/bin/env bash
# Stop Compendium. By default keeps data volumes; pass --purge to delete them.
set -euo pipefail
cd "$(dirname "$0")"

if [ "${1:-}" = "--purge" ]; then
  echo "Stopping and DELETING all data volumes..."
  docker compose down -v
  echo "Removed containers and volumes. The bundle folder is untouched."
else
  echo "Stopping services (data volumes kept). Use --purge to also delete data."
  docker compose down
fi
