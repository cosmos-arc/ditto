#!/usr/bin/env python3
"""
测试所有更新后的脚本
"""

import subprocess
import sys


def run_script(script_name: str) -> bool:
    """运行脚本并返回是否成功."""
    print(f"\n{'=' * 60}")
    print(f"运行脚本: {script_name}")
    print("=" * 60)

    try:
        result = subprocess.run(
            ["pixi", "run", "python", f"scripts/{script_name}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # 打印输出
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        return result.returncode == 0
    except Exception as e:
        print(f"运行脚本失败: {e}")
        return False


def main():
    """主函数."""
    print("开始测试所有更新后的脚本...")

    scripts = [
        "test_data_flow_simple.py",
        "update_data.py",
    ]

    results = {}

    for script in scripts:
        success = run_script(script)
        results[script] = success

        if success:
            print(f"\n[OK] {script} 运行成功!")
        else:
            print(f"\n[ERROR] {script} 运行失败!")

    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结:")
    print("=" * 60)

    for script, success in results.items():
        status = "[OK]" if success else "[ERROR]"
        print(f"  {status} {script}")

    # 统计
    success_count = sum(results.values())
    total_count = len(results)

    print(f"\n总计: {success_count}/{total_count} 个脚本运行成功")

    if success_count == total_count:
        print("\n[OK] 所有脚本都运行成功!")
        return 0
    else:
        print(f"\n[WARNING] {total_count - success_count} 个脚本运行失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
