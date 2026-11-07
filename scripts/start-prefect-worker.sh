#!/bin/sh
# The existing terminal/nohup launcher delegates here after checkout deployment.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
set -a
[ ! -f "$repo/.env" ] || . "$repo/.env"
set +a
export PREFECT_API_URL="${PREFECT_API_URL:-http://127.0.0.1:4200/api}"
export DITTO_CONFIG_ROOT="${DITTO_CONFIG_ROOT:-$repo}"
export DITTO_STATE_ROOT="${DITTO_STATE_ROOT:-$repo/data}"
export DITTO_CACHE_ROOT="${DITTO_CACHE_ROOT:-$repo/.cache}"
exec "$repo/.venv/bin/python" -m ditto_apps.scripts.bounded_output \
  --log "$DITTO_CACHE_ROOT/prefect-worker/worker.log" \
  -- "$repo/.venv/bin/prefect" worker start \
  --pool ditto-data-pool --name ditto-data-1 --type process "$@"
