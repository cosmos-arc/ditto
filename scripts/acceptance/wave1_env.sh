#!/usr/bin/env bash
# Wave 1 RC1 acceptance 环境注入脚本。
#
# source 后导出独立数据根与 testing 运行时环境，供 Phase 1 backfill /
# acceptance 任务复用。data root 默认 .tmp/ditto-rc1（仓库已 gitignore）。
#
# 用法:
#   source scripts/acceptance/wave1_env.sh [data_root]
#
# 导出:
#   DITTO_DATA_ROOT  数据根目录（绝对路径）
#   SQLITE_PATH      metadata.sqlite 路径（catalog/promotion store 共用）
#   DUCKDB_PATH      DuckDB 路径
#   ENVIRONMENT      固定 testing
#   PYTHONUNBUFFERED 1（CLI 输出不缓冲，便于 acceptance 捕获）
set -euo pipefail

WAVE1_DATA_ROOT="${1:-${WAVE1_DATA_ROOT:-.tmp/ditto-rc1}}"

# 解析为绝对路径：目录已存在则 cd+pwd 取规范路径；否则相对 $PWD 绝对化
# （实际目录创建由 `ditto init config` 负责，本脚本不建目录）。
if [[ -d "${WAVE1_DATA_ROOT}" ]]; then
  WAVE1_DATA_ROOT="$(cd "${WAVE1_DATA_ROOT}" && pwd)"
elif [[ "${WAVE1_DATA_ROOT}" != /* ]]; then
  WAVE1_DATA_ROOT="${PWD}/${WAVE1_DATA_ROOT}"
fi

export DITTO_DATA_ROOT="${WAVE1_DATA_ROOT}"
export SQLITE_PATH="${WAVE1_DATA_ROOT}/metadata/metadata.sqlite"
export DUCKDB_PATH="${WAVE1_DATA_ROOT}/db/ditto.duckdb"
export ENVIRONMENT="testing"
export PYTHONUNBUFFERED="1"
