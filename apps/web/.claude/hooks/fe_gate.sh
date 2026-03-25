#!/usr/bin/env bash
# Claude Code stop hook — 快速质量门禁。
#
# 在 Claude 停止时执行轻量检查（约 2s），不跑测试。
# 完整验证请运行 bun run check 或调用 verification-before-completion。

set -euo pipefail

echo "=== fe_gate.sh: 快速质量门禁 ==="

# 1. Biome lint + format
echo "--- [1/2] Biome check ---"
bunx biome check .

# 2. TypeScript 类型检查
echo "--- [2/2] TypeScript type check ---"
bunx tsc --noEmit

echo "=== fe_gate.sh: 通过 ==="
