"""数据质量默认配置路径测试。"""


class TestDefaultConfigPaths:
    """数据质量默认配置路径测试。"""

    def test_default_dq_rules_dir_exists_and_has_yaml_files(self) -> None:
        """默认 DQ 规则目录必须存在并包含规则文件。"""
        from ditto_data.quality.config_paths import get_default_dq_rules_dir

        dq_dir = get_default_dq_rules_dir()

        assert dq_dir.exists(), f"DQ rules directory not found: {dq_dir}"
        yaml_files = list(dq_dir.glob("*.yml"))
        assert yaml_files, f"No DQ rule files in: {dq_dir}"
        assert any(f.name == "stock_daily.yml" for f in yaml_files)

    def test_default_golden_dataset_path_exists(self) -> None:
        """默认黄金数据集配置文件必须存在。"""
        from ditto_data.quality.config_paths import (
            get_default_golden_dataset_path,
        )

        golden_path = get_default_golden_dataset_path()

        assert golden_path.exists(), f"Golden dataset config not found: {golden_path}"
        assert golden_path.name == "golden_dataset.yml"
