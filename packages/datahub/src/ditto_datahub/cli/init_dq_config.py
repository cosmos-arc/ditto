#!/usr/bin/env python3
"""
初始化 DQ 配置脚本

将包内默认 DQ 配置复制到 {data_root}/config/dq/，供用户自定义。
"""

import shutil
from pathlib import Path


def init_dq_config(data_root: str | Path) -> None:
    """
    初始化 DQ 配置目录。

    Args:
        data_root: 数据根目录

    """
    data_root = Path(data_root)
    user_config_dir = data_root / "config" / "dq"

    # 创建用户配置目录
    user_config_dir.mkdir(parents=True, exist_ok=True)

    # 复制包内默认配置
    # 获取包内配置目录：从当前文件位置找到包根目录
    # 实际位置: packages/datahub/config/dq_rules/
    current_file = Path(__file__)
    package_config_dir = current_file.parent.parent / "config" / "dq_rules"

    if not package_config_dir.exists():
        print("警告: 找不到包内默认配置目录")
        print(f"  尝试路径: {package_config_dir}")
        return

    # 复制配置文件
    copied_count = 0
    skipped_count = 0

    for config_file in package_config_dir.glob("*.yml"):
        target = user_config_dir / config_file.name
        if not target.exists():
            shutil.copy(config_file, target)
            print(f"Created: {target}")
            copied_count += 1
        else:
            print(f"Skipped (exists): {target}")
            skipped_count += 1

    # 同时检查 .yaml 文件（虽然项目中使用 .yml）
    for config_file in package_config_dir.glob("*.yaml"):
        target = user_config_dir / config_file.name
        if not target.exists():
            shutil.copy(config_file, target)
            print(f"Created: {target}")
            copied_count += 1
        else:
            print(f"Skipped (exists): {target}")
            skipped_count += 1

    print(f"\nDQ config initialized at: {user_config_dir}")
    print(f"  Created: {copied_count} files")
    print(f"  Skipped: {skipped_count} files")
    print("You can now customize these files.")


if __name__ == "__main__":
    import sys

    # CLI 参数: script.py [data_root]
    MIN_ARGS = 2
    data_root = Path.cwd() / "data" if len(sys.argv) < MIN_ARGS else Path(sys.argv[1])
    init_dq_config(data_root)
