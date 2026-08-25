#!/usr/bin/env python3
"""
pixi test 命令包装脚本

简化测试命令，支持参数驱动：
- pixi run test              # 默认：单元测试（并行）+ 集成测试（串行）
- pixi run test --unit       # 只跑单元测试（并行）
- pixi run test --integration # 只跑集成测试（串行）
- pixi run test --fast       # 快速测试（跳过 slow/integration）
- pixi run test --cov        # 带覆盖率报告
- pixi run test --cov-xml    # 覆盖率 XML（CI 用）
- pixi run test --snapshot   # 支持 inline-snapshot（串行）
- pixi run -e dev pytest -m sandbox_live  # 物理容器安全验收（显式运行）
"""

import subprocess
import sys


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

    # 过滤掉我们的自定义参数，保留路径参数
    paths = [
        arg
        for arg in args
        if arg.startswith("-") is False
        and arg
        not in ["--snapshot", "--unit", "--integration", "--fast", "--cov", "--cov-xml"]
    ]

    # Snapshot 模式：只运行 snapshot 测试（串行）
    if has_snapshot:
        cmd.append("--snapshot-update")
        cmd.extend(["-m", "snapshot"])
        if paths:
            cmd.extend(paths)
        return cmd

    # 覆盖率相关
    if has_cov_xml:
        cmd.extend(
            [
                "--cov",
                "--cov-report=xml",
                "--cov-report=term-missing",
                "--cov-fail-under=80",
            ]
        )
    elif has_cov:
        cmd.extend(["--cov", "--cov-report=html", "--cov-report=term-missing"])

    # 测试类型选择
    if has_integration:
        # 集成测试：串行（排除 snapshot）
        cmd.extend(["-m", "integration and not snapshot", "-n", "0"])
    elif has_fast:
        # 快速测试：跳过 slow/integration/snapshot 和物理容器验收
        cmd.extend(
            [
                "-m",
                "not slow and not integration and not snapshot and not sandbox_live",
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
    if paths:
        cmd.extend(paths)

    return cmd


def main() -> int:
    """主函数"""
    cmd = build_pytest_command()
    print(f"Running: {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
