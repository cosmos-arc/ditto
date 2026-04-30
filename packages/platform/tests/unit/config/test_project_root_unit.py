"""项目根目录发现测试。"""

from pathlib import Path

import pytest


class TestFindProjectRoot:
    """项目根目录发现测试。"""

    def test_find_project_root_from_current_file(self) -> None:
        """从当前文件向上查找应找到项目根目录。"""
        from ditto_platform.foundation.config.project_root import find_project_root

        root = find_project_root()
        # 验证根目录存在 pixi.toml
        assert (root / "pixi.toml").exists()

    def test_find_project_root_with_explicit_start(self) -> None:
        """从指定路径开始查找。"""
        from ditto_platform.foundation.config.project_root import find_project_root

        start_path = Path(__file__)
        root = find_project_root(start=start_path)
        assert (root / "pixi.toml").exists()

    def test_find_project_root_no_marker_raises(self, tmp_path: Path) -> None:
        """无 marker 文件时抛出 RuntimeError。"""
        from ditto_platform.foundation.config.project_root import find_project_root

        # tmp_path 下没有任何 marker 文件
        with pytest.raises(RuntimeError, match="Cannot find project root"):
            find_project_root(start=tmp_path / "nonexistent.py")

    def test_find_project_root_prefers_pixi_toml(self, tmp_path: Path) -> None:
        """不同 marker 时，优先选择 pixi.toml 所在目录。"""
        from ditto_platform.foundation.config.project_root import find_project_root

        # 创建嵌套结构：outer/ (pyproject.toml) / inner/ (pixi.toml)
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / "pyproject.toml").touch()

        inner = outer / "inner"
        inner.mkdir()
        (inner / "pixi.toml").touch()

        # 从 inner 的子目录开始查找
        start = inner / "src" / "module.py"
        start.parent.mkdir(parents=True, exist_ok=True)
        start.touch()

        root = find_project_root(start=start)
        # 应该找到 inner (pixi.toml)，而不是 outer (pyproject.toml)
        assert root == inner

    def test_find_project_root_prefers_nearest_same_marker(
        self, tmp_path: Path
    ) -> None:
        """同 marker 多层嵌套时，返回最近的（内层）。"""
        from ditto_platform.foundation.config.project_root import find_project_root

        # 创建嵌套结构：outer/ (pixi.toml) / inner/ (pixi.toml)
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / "pixi.toml").touch()

        inner = outer / "inner"
        inner.mkdir()
        (inner / "pixi.toml").touch()

        # 从 inner 的子目录开始查找
        start = inner / "src" / "module.py"
        start.parent.mkdir(parents=True)
        start.touch()

        root = find_project_root(start=start)
        # 应该找到 inner（最近的 pixi.toml），而不是 outer
        assert root == inner


class TestGetDefaultDQRulesDir:
    """默认 DQ 规则目录测试。"""

    def test_default_dq_rules_dir_exists(self) -> None:
        """默认 DQ 规则目录必须存在。"""
        from ditto_platform.foundation.config.project_root import (
            get_default_dq_rules_dir,
        )

        dq_dir = get_default_dq_rules_dir()
        assert dq_dir.exists(), f"DQ rules directory not found: {dq_dir}"

    def test_default_dq_rules_dir_has_yaml_files(self) -> None:
        """默认 DQ 规则目录必须包含 yml 文件。"""
        from ditto_platform.foundation.config.project_root import (
            get_default_dq_rules_dir,
        )

        dq_dir = get_default_dq_rules_dir()
        yaml_files = list(dq_dir.glob("*.yml"))
        assert yaml_files, f"No DQ rule files in: {dq_dir}"
        # 验证至少包含 stock_daily.yml
        assert any(f.name == "stock_daily.yml" for f in yaml_files)
