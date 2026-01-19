"""Tests for DQ configuration loading with user override support."""

from pathlib import Path

import pytest
import yaml
from ditto_datahub.dq.engine import DQEngine
from ditto_datahub.models import DQSpec


class TestDQSpecLoading:
    """Test DQ configuration loading with user override."""

    def test_load_default_config_only(self, tmp_path: Path) -> None:
        """
        测试只加载默认配置（无用户配置覆盖）。

        Given: 只有包内默认配置
        When: 加载 DQ 配置
        Then: 应成功加载默认配置
        """
        # Arrange: 创建默认配置目录和文件
        default_config_dir = tmp_path / "default_config"
        default_config_dir.mkdir()

        default_config = {
            "dataset": "test_dataset",
            "description": "Default test dataset",
            "l1_technical": [
                {
                    "rule": "not_null",
                    "columns": ["sid", "trade_date"],
                    "message": "Required fields",
                }
            ],
            "l2_business": [],
            "l3_statistical": [],
        }

        config_file = default_config_dir / "test_dataset.yml"
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(default_config, f)

        # Act: 加载配置
        config = DQSpec.from_yaml_dir(default_config_dir)

        # Assert: 验证加载成功
        assert config.has_dataset("test_dataset")
        rules = config.get_rules("test_dataset")
        assert rules is not None
        assert rules.description == "Default test dataset"
        assert len(rules.l1_technical) == 1

    def test_load_user_config_overrides_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        测试用户配置覆盖默认配置。

        Given: 存在默认配置和用户配置
        When: 使用 load_with_user_override 加载 DQ 配置
        Then: 用户配置应覆盖默认配置
        """
        # Arrange: 创建默认配置
        default_config_dir = tmp_path / "default_config"
        default_config_dir.mkdir()

        default_config = {
            "dataset": "test_dataset",
            "description": "Default description",
            "l1_technical": [
                {
                    "rule": "not_null",
                    "columns": ["sid", "trade_date"],
                    "message": "Default message",
                }
            ],
            "l2_business": [],
            "l3_statistical": [],
        }

        config_file = default_config_dir / "test_dataset.yml"
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(default_config, f)

        # 创建用户配置目录
        data_root = tmp_path / "data"
        user_config_dir = data_root / "config" / "dq"
        user_config_dir.mkdir(parents=True)

        # 用户配置覆盖
        user_config = {
            "dataset": "test_dataset",
            "description": "User custom description",
            "l1_technical": [
                {
                    "rule": "not_null",
                    "columns": ["sid", "trade_date", "close"],
                    "message": "User custom message",
                }
            ],
            "l2_business": [],
            "l3_statistical": [],
        }

        user_config_file = user_config_dir / "test_dataset.yml"
        with user_config_file.open("w", encoding="utf-8") as f:
            yaml.dump(user_config, f)

        # Act: 使用新的加载方法
        merged_config = DQSpec.load_with_user_override(
            default_config_dir=default_config_dir, data_root=data_root
        )

        # Assert: 验证用户配置覆盖了默认配置
        assert merged_config.has_dataset("test_dataset")
        rules = merged_config.get_rules("test_dataset")
        assert rules is not None
        assert rules.description == "User custom description"
        assert len(rules.l1_technical) == 1
        assert rules.l1_technical[0]["columns"] == ["sid", "trade_date", "close"]
        assert rules.l1_technical[0]["message"] == "User custom message"

    def test_user_config_adds_new_dataset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        测试用户配置添加新数据集。

        Given: 默认配置有 dataset_a，用户配置有 dataset_b
        When: 使用 load_with_user_override 加载 DQ 配置
        Then: 应同时包含两个数据集
        """
        # Arrange: 创建默认配置（只有 dataset_a）
        default_config_dir = tmp_path / "default_config"
        default_config_dir.mkdir()

        default_config = {
            "dataset": "dataset_a",
            "description": "Dataset A",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        config_file = default_config_dir / "dataset_a.yml"
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(default_config, f)

        # 创建用户配置（只有 dataset_b）
        data_root = tmp_path / "data"
        user_config_dir = data_root / "config" / "dq"
        user_config_dir.mkdir(parents=True)

        user_config = {
            "dataset": "dataset_b",
            "description": "Dataset B",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        user_config_file = user_config_dir / "dataset_b.yml"
        with user_config_file.open("w", encoding="utf-8") as f:
            yaml.dump(user_config, f)

        # Act: 使用新的加载方法
        merged_config = DQSpec.load_with_user_override(
            default_config_dir=default_config_dir, data_root=data_root
        )

        # Assert: 验证两个数据集都存在
        assert merged_config.has_dataset("dataset_a")
        assert merged_config.has_dataset("dataset_b")
        assert merged_config.get_rules("dataset_a").description == "Dataset A"
        assert merged_config.get_rules("dataset_b").description == "Dataset B"

    def test_missing_user_config_dir_uses_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        测试用户配置目录不存在时使用默认配置。

        Given: 只有默认配置，用户配置目录不存在
        When: 使用 load_with_user_override 加载 DQ 配置
        Then: 应成功加载默认配置
        """
        # Arrange: 创建默认配置
        default_config_dir = tmp_path / "default_config"
        default_config_dir.mkdir()

        default_config = {
            "dataset": "test_dataset",
            "description": "Default only",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        config_file = default_config_dir / "test_dataset.yml"
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(default_config, f)

        # 用户配置目录不存在
        data_root = tmp_path / "data"
        user_config_dir = data_root / "config" / "dq"

        # Act & Assert: 验证用户配置目录不存在
        assert not user_config_dir.exists()

        # 应能加载默认配置
        config = DQSpec.load_with_user_override(
            default_config_dir=default_config_dir, data_root=data_root
        )
        assert config.has_dataset("test_dataset")

    def test_empty_user_config_dir_uses_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        测试用户配置目录为空时使用默认配置。

        Given: 默认配置存在，用户配置目录存在但为空
        When: 使用 load_with_user_override 加载 DQ 配置
        Then: 应成功加载默认配置
        """
        # Arrange: 创建默认配置
        default_config_dir = tmp_path / "default_config"
        default_config_dir.mkdir()

        default_config = {
            "dataset": "test_dataset",
            "description": "Default only",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        config_file = default_config_dir / "test_dataset.yml"
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(default_config, f)

        # 创建空的用户配置目录
        data_root = tmp_path / "data"
        user_config_dir = data_root / "config" / "dq"
        user_config_dir.mkdir(parents=True)

        # Act: 使用新的加载方法
        merged_config = DQSpec.load_with_user_override(
            default_config_dir=default_config_dir, data_root=data_root
        )

        # Assert: 验证默认配置被加载
        assert merged_config.has_dataset("test_dataset")
        assert merged_config.get_rules("test_dataset").description == "Default only"


class TestDQEngineWithUserConfig:
    """Test DQEngine with user configuration override."""

    def test_engine_uses_default_config_without_data_root(self, tmp_path: Path) -> None:
        """
        测试 DQEngine 在没有 data_root 时使用默认配置。

        Given: 创建 DQEngine 时不指定 data_root
        When: 执行 DQ 检查
        Then: 应使用默认配置
        """
        # Arrange: 创建默认配置
        default_config_dir = tmp_path / "default_config"
        default_config_dir.mkdir()

        default_config = {
            "dataset": "test_dataset",
            "description": "Default",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        config_file = default_config_dir / "test_dataset.yml"
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(default_config, f)

        # Act: 使用默认配置创建引擎
        config = DQSpec.from_yaml_dir(default_config_dir)
        engine = DQEngine(config=config)

        # Assert: 验证配置加载成功
        assert engine.config.has_dataset("test_dataset")

    def test_engine_with_data_root_loads_user_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        测试 DQEngine 使用 data_root 加载用户配置。

        Given: 指定 data_root，存在用户配置
        When: 创建 DQEngine
        Then: 应加载用户配置覆盖默认配置
        """
        # Arrange: 创建用户配置目录和自定义配置
        data_root = tmp_path / "data"
        user_config_dir = data_root / "config" / "dq"
        user_config_dir.mkdir(parents=True)

        # 创建用户自定义配置，覆盖包内默认的 stock_daily
        user_config = {
            "dataset": "stock_daily",
            "description": "User custom stock daily config",
            "l1_technical": [
                {
                    "rule": "not_null",
                    "columns": ["sid", "trade_date", "close", "custom_field"],
                    "message": "User custom not null check",
                }
            ],
            "l2_business": [],
            "l3_statistical": [],
        }

        user_config_file = user_config_dir / "stock_daily.yml"
        with user_config_file.open("w", encoding="utf-8") as f:
            yaml.dump(user_config, f)

        # Act: 使用 data_root 创建引擎
        engine = DQEngine(data_root=data_root)

        # Assert: 验证用户配置被加载并覆盖了默认配置
        assert engine.config.has_dataset("stock_daily")
        rules = engine.config.get_rules("stock_daily")
        assert rules is not None
        assert rules.description == "User custom stock daily config"
        assert len(rules.l1_technical) == 1
        # 验证用户自定义的列配置
        assert rules.l1_technical[0]["columns"] == [
            "sid",
            "trade_date",
            "close",
            "custom_field",
        ]
        assert rules.l1_technical[0]["message"] == "User custom not null check"
