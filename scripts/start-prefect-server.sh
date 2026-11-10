#!/bin/sh
# Ditto 专属 Prefect server（2026-11-10 裁决：独占 4200，与 goalx 4201 分离）。
# DB 隔离：PREFECT_HOME 指向仓库 .cache，不与 goalx 共享 ~/.prefect 默认库。
# 终端血统启动（launchd 对 uv-python 卡死，见 #615）；由 21:45 预检 automation 兜底复活。
set -eu
export PREFECT_HOME="/Users/chevy/Desktop/code/ditto/.cache/prefect-server"
exec /Users/chevy/Desktop/code/ditto/.venv/bin/prefect server start --host 127.0.0.1 --port 4200
