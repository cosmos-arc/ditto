#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd -P)"

cd -- "$REPO_ROOT"
exec uv run --no-sync python -m tooling.contracts.generate_web_schema "$@"
