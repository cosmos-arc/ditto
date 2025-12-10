#!/usr/bin/env python3
"""Ditto 测试运行脚本 - 提供便捷的测试运行命令集合."""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], cwd: Path | None = None) -> int:
    """运行命令并返回退出码."""
    print(f"\n{'=' * 80}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'=' * 80}\n")

    result = subprocess.run(cmd, check=False, cwd=cwd)
    return result.returncode


def main() -> int:  # noqa: PLR0912, PLR0915
    """主函数."""
    parser = argparse.ArgumentParser(description="Ditto 测试运行脚本")
    parser.add_argument(
        "--type",
        choices=["unit", "integration", "e2e", "perf", "all"],
        default="all",
        help="测试类型 (default: all)",
    )
    parser.add_argument(
        "--package",
        choices=["core", "foundation", "both"],
        default="both",
        help="包选择 (default: both)",
    )
    parser.add_argument("--cov", action="store_true", help="生成覆盖率报告")
    parser.add_argument(
        "--cov-fail-under", type=int, default=80, help="覆盖率阈值 (default: 80)"
    )
    parser.add_argument(
        "--no-cov-fail", action="store_true", help="不因覆盖率不足而失败"
    )
    parser.add_argument("--parallel", "-n", type=int, help="并行测试的进程数")
    parser.add_argument(
        "--verbose", "-v", action="count", default=0, help="详细输出 (-v, -vv)"
    )
    parser.add_argument("--failed-first", action="store_true", help="先运行失败的测试")
    parser.add_argument(
        "--debug", action="store_true", help="调试模式 (停止在第一个错误)"
    )

    args = parser.parse_args()

    # 基础命令
    base_cmd = ["pixi", "run", "pytest"]

    # 构建测试路径
    test_paths = []

    if args.type == "all":
        if args.package in ["core", "both"]:
            test_paths.extend(
                ["packages/core/tests/unit", "packages/core/tests/integration"]
            )
        if args.package in ["foundation", "both"]:
            test_paths.append("packages/foundation/tests/unit")
        test_paths.extend(["tests/e2e", "tests/perf"])
    elif args.type == "unit":
        if args.package in ["core", "both"]:
            test_paths.append("packages/core/tests/unit")
        if args.package in ["foundation", "both"]:
            test_paths.append("packages/foundation/tests/unit")
    elif args.type == "integration":
        if args.package in ["core", "both"]:
            test_paths.append("packages/core/tests/integration")
    elif args.type == "e2e":
        test_paths.append("tests/e2e")
    elif args.type == "perf":
        test_paths.append("tests/perf")

    # 构建完整命令
    cmd = base_cmd + test_paths

    # 添加选项
    if args.verbose:
        cmd.extend(["-v"] * args.verbose)

    if args.failed_first:
        cmd.append("--failed-first")

    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])

    if args.debug:
        cmd.extend(["-x", "--tb=short"])
    else:
        cmd.extend(["--tb=short"])

    # 覆盖率选项
    if args.cov:
        cmd.extend(["--cov=packages"])
        cmd.extend(["--cov=apps"])
        cmd.extend(["--cov-report=term-missing:skip-covered"])
        cmd.extend(["--cov-report=html:htmlcov"])
        cmd.extend(["--cov-report=xml"])
        cmd.extend(["--cov-branch"])

        if not args.no_cov_fail:
            cmd.extend([f"--cov-fail-under={args.cov_fail_under}"])

    # 运行命令
    return run_command(cmd)


if __name__ == "__main__":
    sys.exit(main())
