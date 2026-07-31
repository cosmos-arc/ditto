#!/usr/bin/env bash
set -euo pipefail

OPENAPI_URL="${OPENAPI_URL:-http://localhost:8000/openapi.json}"
OPENAPI_FILE="${OPENAPI_FILE:-}"
OUTPUT_PATH="${OUTPUT_PATH:-src/types/generated/api.d.ts}"
OUTPUT_DIR="$(dirname "$OUTPUT_PATH")"
OUTPUT_BASENAME="$(basename "$OUTPUT_PATH")"

mkdir -p "$OUTPUT_DIR"
TEMP_OUTPUT_PATH="$(mktemp "$OUTPUT_DIR/.${OUTPUT_BASENAME}.tmp.XXXXXX.d.ts")"

cleanup() {
	if [[ -n "${TEMP_OUTPUT_PATH:-}" && -e "$TEMP_OUTPUT_PATH" ]]; then
		rm -f -- "$TEMP_OUTPUT_PATH"
	fi
}

trap cleanup EXIT
trap 'exit 1' HUP INT TERM

if [[ -n "$OPENAPI_FILE" ]]; then
	if [[ ! -r "$OPENAPI_FILE" ]]; then
		echo "OPENAPI_FILE is not readable: $OPENAPI_FILE" >&2
		exit 1
	fi
	bunx openapi-typescript "$OPENAPI_FILE" -o "$TEMP_OUTPUT_PATH"
else
	curl --fail --silent --show-error --max-time 15 "$OPENAPI_URL" \
		| bunx openapi-typescript -o "$TEMP_OUTPUT_PATH"
fi

mv -f -- "$TEMP_OUTPUT_PATH" "$OUTPUT_PATH"
TEMP_OUTPUT_PATH=""
