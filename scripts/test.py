#!/usr/bin/env python3
"""
task test 命令包装脚本

简化测试命令，支持参数驱动：
- task test --              # 默认：非 snapshot/sandbox 测试（并行）
- task test -- --unit       # 只跑单元测试（并行）
- task test -- --integration # 只跑集成测试（串行）
- task test -- --fast       # 快速测试（跳过 slow/integration）
- task test -- --cov        # 带覆盖率报告
- task test -- --cov-xml    # 覆盖率 XML（CI 用）
- task test -- --snapshot   # 支持 inline-snapshot（串行）
- uv run --no-sync pytest -m sandbox_live  # 物理容器安全验收（显式运行）
"""

import os
import subprocess
import sys
from pathlib import Path

# scripts/ 不在 sys.path 上；引导仓库根后共享同一 fast 选择表达式。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tooling.quality.test_selection import FAST_LANE_EXPR


def build_pytest_command() -> list[str]:
    """根据参数构建 pytest 命令"""
    args = sys.argv[1:]  # 跳过脚本名

    # 默认基础参数
    cmd = ["pytest", "-v", "--import-mode=importlib"]

    # 处理特殊参数
    has_snapshot = "--snapshot" in args
    has_unit = "--unit" in args
    has_integration = "--integration" in args
    has_fast = "--fast" in args
    has_cov = "--cov" in args
    has_cov_xml = "--cov-xml" in args

    # Consume wrapper flags only; preserve pytest options and their values.
    wrapper_flags = {
        "--snapshot",
        "--unit",
        "--integration",
        "--fast",
        "--cov",
        "--cov-xml",
    }
    forwarded = [arg for arg in args if arg not in wrapper_flags]

    # Snapshot 模式：只运行 snapshot 测试（串行）
    if has_snapshot:
        cmd.extend(["--snapshot-update", "-n", "0"])
        cmd.extend(["-m", "snapshot"])
        if forwarded:
            cmd.extend(forwarded)
        return cmd

    # 覆盖率相关
    if has_cov_xml:
        cmd.extend(
            [
                "--cov",
                "--cov-report=xml",
                "--cov-report=json:coverage.json",
                "--cov-report=term-missing",
            ]
        )
    elif has_cov:
        cmd.extend(["--cov", "--cov-report=html", "--cov-report=term-missing"])

    # 测试类型选择
    if has_integration:
        # 集成测试：串行（排除 snapshot）
        cmd.extend(["-m", "integration and not snapshot", "-n", "0"])
    elif has_fast:
        # 快速测试：按资源/旅程成本选择（slow/serial/e2e/snapshot/sandbox_live/
        # capacity），不含 unit/integration 层级——低成本真实集成可进入快速车道；
        # 10s/用例硬顶超时兜住异常用例(挂死/失控)——0.5s 分类阈值由时长门禁
        # 与 analyze-slow-tests 治理,硬顶只杀真异常,不误杀边界人群（#330 B1）
        cmd.extend(
            [
                "-m",
                FAST_LANE_EXPR,
                "--timeout=10",
                "--no-cov",
                "-q",
            ]
        )
    elif has_unit:
        # 单元测试：并行（排除 snapshot）
        cmd.extend(["-m", "unit and not snapshot", "-n", "auto"])
    else:
        # 默认：并行运行非 snapshot 测试，物理容器验收必须显式串行运行
        cmd.extend(["-m", "not snapshot and not sandbox_live", "-n", "auto"])

    # 添加路径参数
    if forwarded:
        cmd.extend(forwarded)

    return cmd


def main() -> int:
    """主函数"""
    cmd = build_pytest_command()
    print(f"Running: {' '.join(cmd)}", file=sys.stderr)
    # Apply before collection; xdist workers and test subprocesses inherit it.
    environment = {
        **os.environ,
        "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        "_TYPER_FORCE_DISABLE_TERMINAL": "1",
    }
    return subprocess.run(cmd, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
