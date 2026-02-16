"""
项目根目录发现模块。

参考业界最佳实践:
- pyrootutils: https://pypi.org/project/pyrootutils/
- pyprojroot: https://github.com/chendaniely/pyprojroot
"""

from pathlib import Path
from typing import Final

__all__ = ["find_project_root", "get_default_dq_rules_dir"]

# 优先级：pixi.toml > pyproject.toml > .git
# pixi.toml 在 monorepo 根目录，优先级最高
_ROOT_MARKERS: Final = ("pixi.toml", "pyproject.toml", ".git")


def find_project_root(start: Path | None = None) -> Path:
    """
    从给定路径向上查找项目根目录。

    使用 pixi.toml / pyproject.toml / .git 作为根标记。
    策略：优先级 + 最近命中（按 marker 优先级查找，同 marker 返回最近的）。

    Args:
        start: 起始路径，默认为当前文件所在目录

    Returns:
        项目根目录路径

    Raises:
        RuntimeError: 找不到项目根目录

    Example:
        >>> root = find_project_root()
        >>> (root / "pixi.toml").exists()
        True

    """
    path = (start or Path(__file__)).resolve()

    # 按 marker 优先级顺序查找，找到即返回（同 marker 多层时返回最近的）
    for marker in _ROOT_MARKERS:
        for parent in path.parents:
            if (parent / marker).exists():
                return parent

    raise RuntimeError(f"Cannot find project root from {path}")


def get_default_dq_rules_dir() -> Path:
    """
    获取默认 DQ 规则目录。

    Returns:
        config/default/dq_rules 目录路径

    Raises:
        RuntimeError: 找不到项目根目录

    """
    return find_project_root() / "config" / "default" / "dq_rules"
