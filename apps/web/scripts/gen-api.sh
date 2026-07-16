#!/usr/bin/env bash
set -euo pipefail

OPENAPI_URL="${OPENAPI_URL:-http://localhost:8000/openapi.json}"
OUTPUT_PATH="${OUTPUT_PATH:-src/types/generated/api.d.ts}"

mkdir -p "$(dirname "$OUTPUT_PATH")"
curl --fail --silent --show-error --max-time 15 "$OPENAPI_URL" \
	| bunx openapi-typescript -o "$OUTPUT_PATH"
