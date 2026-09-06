#!/usr/bin/env python3
"""
task type 命令包装脚本

简化类型检查命令，支持参数驱动：
- task type --              # 默认：源码增量类型检查（strict + warnings）
- task type -- --clean      # 源码全量检查（清除缓存后 strict + warnings）
- task type -- --tests      # 测试代码类型检查（basic 模式）
- task type -- --all        # 源码 + 测试全部检查
- task type -- --all --clean # 全量清除缓存后检查所有
"""

import shutil
import subprocess
import sys
from pathlib import Path


def clear_pyright_cache() -> None:
    """清除 basedpyright/pyright 缓存以确保类型检查准确。"""
    for name in (".pyright_cache", ".basedpyright"):
        cache_dir = Path.cwd() / name
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)


def main() -> int:
    """主函数"""
    args = sys.argv[1:]

    # 仅在 --clean 时清除缓存，启用增量检查加速日常开发
    if "--clean" in args:
        clear_pyright_cache()
        args = [a for a in args if a != "--clean"]

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
