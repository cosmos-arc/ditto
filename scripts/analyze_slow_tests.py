#!/usr/bin/env python
"""分析慢速测试并报告超过阈值的测试"""

import subprocess
import sys
from pathlib import Path

# 性能阈值（秒）
UNIT_TEST_THRESHOLD = 0.5
INTEGRATION_TEST_THRESHOLD = 5.0
_MIN_PARTS = 3


def get_durations(test_path: str, count: int = 50) -> dict:
    """运行 pytest 并获取耗时数据

    如果测试路径不存在，返回空字典
    """
    # 检查路径是否存在
    if not Path(test_path).exists():
        return {}

    cmd = [
        "pytest",
        test_path,
        "--durations",
        str(count),
        "--quiet",
        "--tb=no",
        "-v",
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",  # 明确指定编码
        errors="replace",  # 替换无法解码的字符
        check=False,
    )

    # 解析输出
    durations = {}
    for line in result.stdout.split("\n"):
        if "s setup" in line or "s call" in line:
            # 格式: "2.34s call     tests/unit/test_foo.py::test_bar"
            parts = line.split()
            if len(parts) >= _MIN_PARTS:
                duration_str = parts[0].rstrip("s")
                test_name = parts[2]
                try:
                    duration = float(duration_str)
                    durations[test_name] = duration
                except ValueError:
                    continue

    return durations


def analyze_slow_tests() -> None:
    """分析慢速测试并生成报告"""

    # 分析单元测试
    print("[*] 分析单元测试...")
    unit_durations = {}
    for package in ["kernel", "data", "infra", "app", "engine", "analytics"]:
        path = f"packages/{package}/tests/unit"
        unit_durations.update(get_durations(path, count=50))
    path = "interfaces/tests/unit"
    unit_durations.update(get_durations(path, count=50))

    slow_unit_tests = {
        name: duration
        for name, duration in unit_durations.items()
        if duration > UNIT_TEST_THRESHOLD
    }

    # 分析集成测试
    print("[*] 分析集成测试...")
    integration_durations = {}
    for package in ["kernel", "data", "infra", "app", "engine", "analytics"]:
        path = f"packages/{package}/tests/integration"
        integration_durations.update(get_durations(path, count=50))
    path = "interfaces/tests/integration"
    integration_durations.update(get_durations(path, count=50))

    slow_integration_tests = {
        name: duration
        for name, duration in integration_durations.items()
        if duration > INTEGRATION_TEST_THRESHOLD
    }

    # 生成报告
    print("\n" + "=" * 60)
    print("慢速测试报告")
    print("=" * 60)

    if slow_unit_tests:
        msg = (
            f"\n[!] 单元测试超过 {UNIT_TEST_THRESHOLD}s 阈值 "
            f"({len(slow_unit_tests)} 个):"
        )
        print(msg)
        for name, duration in sorted(
            slow_unit_tests.items(),
            key=lambda x: -x[1],
        ):
            print(f"  {duration:.2f}s - {name}")
    else:
        msg = f"\n[OK] 所有单元测试符合性能要求 (<{UNIT_TEST_THRESHOLD}s)"
        print(msg)

    if slow_integration_tests:
        msg = (
            f"\n[!] 集成测试超过 {INTEGRATION_TEST_THRESHOLD}s 阈值 "
            f"({len(slow_integration_tests)} 个):"
        )
        print(msg)
        for name, duration in sorted(
            slow_integration_tests.items(),
            key=lambda x: -x[1],
        ):
            print(f"  {duration:.2f}s - {name}")
    else:
        msg = f"\n[OK] 所有集成测试符合性能要求 (<{INTEGRATION_TEST_THRESHOLD}s)"
        print(msg)

    # 返回退出码
    if slow_unit_tests or slow_integration_tests:
        print("\n[建议] 修复建议:")
        print("  - 检查是否有未 mock 的外部依赖")
        print("  - 检查是否有真实的 time.sleep()")
        print("  - 检查是否有重复的 fixture 初始化")
        sys.exit(1)
    else:
        print("\n[SUCCESS] 所有测试性能良好!")
        sys.exit(0)


if __name__ == "__main__":
    analyze_slow_tests()
