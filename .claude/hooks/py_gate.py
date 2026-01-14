#!/usr/bin/env python3
"""
Claude Code pre-commit gate hook.

在写入操作前执行代码质量检查（lint 和 typecheck）。

通过 CLAUDE_PROJECT_DIR 环境变量定位项目根目录，依次执行：
1. pixi run lint - Ruff 代码风格检查
2. pixi run typecheck - 生产代码类型检查（pyright）
3. pixi run typecheck-tests - 测试代码类型检查

任何检查失败会阻止写入操作完成。
"""

import os
import subprocess


def run(cmd: list[str], cwd: str) -> int:
    """运行命令并返回退出码。"""
    return subprocess.run(cmd, check=False, cwd=cwd).returncode  # noqa: S603


def main() -> int:
    """执行代码质量检查流程。"""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()  # noqa: PTH109

    rc = run(["pixi", "run", "-e", "dev", "lint"], cwd=project_dir)
    if rc != 0:
        return rc
    rc = run(["pixi", "run", "-e", "dev", "format-check"], cwd=project_dir)
    if rc != 0:
        return rc
    rc = run(["pixi", "run", "-e", "dev", "typecheck"], cwd=project_dir)
    if rc != 0:
        return rc
    rc = run(["pixi", "run", "-e", "dev", "typecheck-tests"], cwd=project_dir)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
