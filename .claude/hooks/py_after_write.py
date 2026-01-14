#!/usr/bin/env python3
"""
Claude Code post-write hook.

在写入 Python 文件后自动执行代码格式化和修复。

从 stdin 读取 JSON 格式的工具调用信息，判断是否为 Write/Edit 操作且目标
文件为 .py 文件。如果是，则依次执行：
1. pixi run format - Ruff 格式化
2. pixi run lint-fix - Ruff 自动修复

输入格式（JSON）:
{
    "tool_name": "Write" | "Edit",
    "tool_input": {"file_path": "..."}
}
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: str) -> int:
    """运行命令并输出 stdout/stderr，返回退出码。"""
    p = subprocess.run(cmd, check=False, cwd=cwd, capture_output=True, text=True)  # noqa: S603
    if p.stdout:
        print(p.stdout)  # noqa: T201
    if p.stderr:
        print(p.stderr, file=sys.stderr)  # noqa: T201
    return p.returncode


def main() -> int:
    """处理 hook 调用，对 Python 文件执行格式化和修复。"""
    data = json.load(sys.stdin)
    tool = data.get("tool_name")
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path")

    if tool not in {"Write", "Edit"} or not file_path:
        return 0

    p = Path(file_path)
    if p.suffix != ".py":
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()  # noqa: PTH109

    # 用 pixi task 替代 ruff
    # 参数会自动追加到任务命令末尾：pixi run format <file>  => ruff format <file>
    rc = run(["pixi", "run", "format", str(p)], cwd=project_dir)
    if rc != 0:
        return rc

    rc = run(["pixi", "run", "lint-fix", str(p)], cwd=project_dir)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
