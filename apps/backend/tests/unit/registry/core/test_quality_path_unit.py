"""DQ 规则路径测试。"""

from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[6]


class TestDQRulesPath:
    """DQ 规则路径测试。"""

    def test_default_dq_rules_dir_exists(self) -> None:
        """默认 DQ 规则目录必须存在。"""
        from ditto_data.quality.config_paths import get_default_dq_rules_dir

        dq_dir = get_default_dq_rules_dir(_WORKSPACE_ROOT)
        assert dq_dir.exists(), f"DQ rules directory not found: {dq_dir}"

    def test_default_dq_rules_dir_has_yaml_files(self) -> None:
        """默认 DQ 规则目录必须包含 yml 文件。"""
        from ditto_data.quality.config_paths import get_default_dq_rules_dir

        dq_dir = get_default_dq_rules_dir(_WORKSPACE_ROOT)
        yaml_files = list(dq_dir.glob("*.yml"))
        assert yaml_files, f"No DQ rule files in: {dq_dir}"
        # 验证至少包含 stock_daily.yml
        assert any(f.name == "stock_daily.yml" for f in yaml_files)


class TestQualityProviderUsesCorrectPath:
    """验证 QualityProvider 使用正确的路径。"""

    def test_quality_provider_imports_data_owned_config_paths(self) -> None:
        """QualityProvider 应该导入 data-owned 默认配置路径。"""
        import ast

        from ditto_data.di.quality import QualityProvider

        # 读取源文件
        source_file = Path(QualityProvider.__module__.replace(".", "/") + ".py")
        if not source_file.exists():
            # 使用 __file__ 属性找到源文件
            import ditto_data.di.quality as mod

            source_file = Path(mod.__file__)

        source = source_file.read_text()
        tree = ast.parse(source)

        imported_modules: set[str] = set()
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    imported_modules.add(node.module)
                for alias in node.names:
                    imported_names.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)

        assert "ditto_data.quality.config_paths" in imported_modules
        assert "get_default_dq_rules_dir" in imported_names, (
            "QualityProvider should import get_default_dq_rules_dir from data"
        )
