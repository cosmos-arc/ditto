#!/usr/bin/env bash
# Claude Code post-write hook.
#
# 在写入 .ts/.tsx/.css/.json 文件后自动执行 Biome 格式化和修复。
# 仅处理 src/ 目录下的文件，排除 docs/、.claude/ 等。

set -euo pipefail

# 从 stdin 读取 JSON
input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name // empty')
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

# 只处理 Write 和 Edit
if [[ "$tool_name" != "Write" && "$tool_name" != "Edit" ]]; then
    exit 0
fi

# 无文件路径则跳过
if [[ -z "$file_path" ]]; then
    exit 0
fi

# 仅处理 src/ 下的代码文件
case "$file_path" in
    src/**/*.ts|src/**/*.tsx|src/**/*.css|src/**/*.json)
        ;;
    *)
        exit 0
        ;;
esac

# 执行 biome check --write（lint + format 一步到位）
bunx biome check --write "$file_path"
