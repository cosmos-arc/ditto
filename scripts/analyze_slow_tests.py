#!/usr/bin/env python
"""分析慢速测试并报告超过阈值的测试（收集驱动）。

不再手工枚举测试根：一次全量运行（排除 slow/capacity/sandbox_live 标记，
null keyring 隔离个人凭证）解析 junit 证据；阈值、junit 解析与节点归一化
复用 tooling.quality.slow_test_gate 的单一权威实现。unit/integration 预算
优先按标记判定，未打标时按测试文件的路径层级兜底。
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tooling.quality.slow_test_gate import (
    INTEGRATION_THRESHOLD,
    UNIT_THRESHOLD,
    collect_ids,
    layer_budget,
    normalize_node,
    parse_junit,
)

_EXCLUSION = "not slow and not capacity and not sandbox_live"


def _run_suite(junit: Path) -> int:
    """Run the whole suite once with marker exclusion into a junit report."""
    env = dict(os.environ, PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=no",
            "--import-mode=importlib",
            "-o",
            "addopts=",
            "-n",
            "auto",
            "--dist",
            "loadfile",
            "-p",
            "no:cacheprovider",
            "-m",
            _EXCLUSION,
            f"--junitxml={junit}",
        ],
        check=False,
        env=env,
    ).returncode


def _marked_nodes(marker: str) -> set[tuple[str, str]]:
    return {
        node
        for raw in collect_ids(None, marker)
        if (node := normalize_node(raw)) is not None
    }


def analyze_slow_tests() -> int:
    """Run the suite and report tests above their budget; 0 when compliant."""
    with tempfile.TemporaryDirectory() as td:
        junit = Path(td) / "junit.xml"
        exit_code = _run_suite(junit)
        if exit_code not in (0, 1) or not junit.is_file():
            # 0/1 = 完整跑完（含失败）；其他退出码或缺失报告 = 证据不完整，fail closed
            print(
                f"[analyze-slow-tests] FAIL: 套件未完整运行 (pytest exit {exit_code})"
            )
            return 2
        durations = parse_junit([junit], Path.cwd())

    print("[*] 收集标记身份...")
    unit_nodes = _marked_nodes("unit")
    integration_nodes = _marked_nodes("integration")

    slow_unit: list[tuple[float, str]] = []
    slow_integration: list[tuple[float, str]] = []
    for file, by_name in sorted(durations.items()):
        for name, seconds in by_name.items():
            limit = layer_budget(file, name, unit_nodes, integration_nodes)
            if seconds <= limit:
                continue
            entry = (seconds, f"{file}::{name}")
            target = slow_unit if limit == UNIT_THRESHOLD else slow_integration
            target.append(entry)

    print("\n" + "=" * 60)
    print("慢速测试报告(已排除 slow/capacity/sandbox_live 标记)")
    print("=" * 60)

    def _report(items: list[tuple[float, str]], label: str, limit: float) -> None:
        if items:
            print(f"\n[!] {label}超过 {limit}s 阈值 ({len(items)} 个):")
            for seconds, node in sorted(items, reverse=True):
                print(f"  {seconds:.2f}s - {node}")
        else:
            print(f"\n[OK] 所有{label}符合性能要求 (<{limit}s)")

    _report(slow_unit, "单元测试", UNIT_THRESHOLD)
    _report(slow_integration, "集成测试", INTEGRATION_THRESHOLD)

    if slow_unit or slow_integration:
        print("\n[建议] 修复建议:")
        print("  - 检查是否有未 mock 的外部依赖")
        print("  - 检查是否有真实的 time.sleep()")
        print("  - 检查是否有重复的 fixture 初始化")
        print("  - 确属慢的测试打 @pytest.mark.slow / capacity 进慢车道")
        return 1
    print("\n[SUCCESS] 所有测试性能良好!")
    return 0


def main() -> int:
    return analyze_slow_tests()


if __name__ == "__main__":
    raise SystemExit(main())
