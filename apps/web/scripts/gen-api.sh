#!/usr/bin/env bash
set -euo pipefail

OPENAPI_URL="${OPENAPI_URL:-http://localhost:8000/openapi.json}"
OPENAPI_FILE="${OPENAPI_FILE:-}"
OUTPUT_PATH="${OUTPUT_PATH:-src/types/generated/api.d.ts}"

mkdir -p "$(dirname "$OUTPUT_PATH")"

if [[ -n "$OPENAPI_FILE" ]]; then
	if [[ ! -r "$OPENAPI_FILE" ]]; then
		echo "OPENAPI_FILE is not readable: $OPENAPI_FILE" >&2
		exit 1
	fi
	bunx openapi-typescript "$OPENAPI_FILE" -o "$OUTPUT_PATH"
	exit 0
fi

curl --fail --silent --show-error --max-time 15 "$OPENAPI_URL" \
	| bunx openapi-typescript -o "$OUTPUT_PATH"
