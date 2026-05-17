"""Default data quality configuration paths."""

from pathlib import Path

from ditto_platform.foundation import find_project_root

__all__ = [
    "get_default_dq_rules_dir",
    "get_default_golden_dataset_path",
]


def get_default_dq_rules_dir() -> Path:
    """
    获取默认 DQ 规则目录。

    Returns:
        config/default/dq_rules 目录路径

    Raises:
        RuntimeError: 找不到项目根目录

    """
    return find_project_root() / "config" / "default" / "dq_rules"


def get_default_golden_dataset_path() -> Path:
    """
    获取默认黄金数据集配置路径。

    Returns:
        config/default/golden_dataset.yml 文件路径

    Raises:
        RuntimeError: 找不到项目根目录

    """
    return find_project_root() / "config" / "default" / "golden_dataset.yml"
