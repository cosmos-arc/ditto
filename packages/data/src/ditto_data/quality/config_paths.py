"""Default data quality configuration paths."""

from pathlib import Path

__all__ = [
    "get_default_dq_rules_dir",
    "get_default_golden_dataset_path",
]


def get_default_dq_rules_dir(config_root: Path) -> Path:
    """
    获取默认 DQ 规则目录。

    Args:
        config_root: 由 composition root 注入的配置根目录

    Returns:
        config/default/dq_rules 目录路径

    """
    return config_root / "config" / "default" / "dq_rules"


def get_default_golden_dataset_path(config_root: Path) -> Path:
    """
    获取默认黄金数据集配置路径。

    Args:
        config_root: 由 composition root 注入的配置根目录

    Returns:
        config/default/golden_dataset.yml 文件路径

    """
    return config_root / "config" / "default" / "golden_dataset.yml"
