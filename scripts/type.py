#!/usr/bin/env python3
"""
pixi type 命令包装脚本

简化类型检查命令，支持参数驱动：
- pixi run type          # 默认：源码类型检查（strict + warnings）
- pixi run type --tests  # 测试代码类型检查（basic 模式）
- pixi run type --all    # 源码 + 测试全部检查
"""

import shutil
import subprocess
import sys
from pathlib import Path


def clear_pyright_cache() -> None:
    """清除 basedpyright/pyright 缓存以确保类型检查准确。"""
    cache_dir = Path.cwd() / ".pyright_cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)


def main() -> int:
    """主函数"""
    args = sys.argv[1:]

    # 清除缓存以确保类型检查准确
    clear_pyright_cache()

    has_tests = "--tests" in args
    has_all = "--all" in args

    if has_all:
        # 运行所有类型检查
        print("Running: basedpyright --warnings", file=sys.stderr)
        rc1 = subprocess.run(["basedpyright", "--warnings"], check=False).returncode
        print("\nRunning: basedpyright --project pyright.tests.json", file=sys.stderr)
        rc2 = subprocess.run(
            ["basedpyright", "--project", "pyright.tests.json"], check=False
        ).returncode
        return rc1 or rc2
    elif has_tests:
        # 只检查测试代码
        print("Running: basedpyright --project pyright.tests.json", file=sys.stderr)
        return subprocess.run(
            ["basedpyright", "--project", "pyright.tests.json"], check=False
        ).returncode
    else:
        # 默认：只检查源码
        print("Running: basedpyright --warnings", file=sys.stderr)
        return subprocess.run(["basedpyright", "--warnings"], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
