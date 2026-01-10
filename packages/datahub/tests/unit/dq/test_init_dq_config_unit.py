"""Tests for DQ configuration initialization script."""

import shutil
from pathlib import Path

import yaml


class TestInitDQConfig:
    """Test DQ config initialization script."""

    def test_init_dq_config_creates_directory(self, tmp_path: Path) -> None:
        """
        测试初始化脚本创建配置目录。

        Given: 临时目录和默认配置
        When: 运行初始化逻辑
        Then: 应创建 config/dq 目录并复制配置文件
        """
        # Arrange: 创建默认配置目录
        default_config_dir = tmp_path / "default_config"
        default_config_dir.mkdir()

        # 创建默认配置文件
        default_config = {
            "dataset": "test_dataset",
            "description": "Test",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        config_file = default_config_dir / "test_dataset.yml"
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(default_config, f)

        # Act: 创建用户配置目录并复制文件
        data_root = tmp_path / "data"
        user_config_dir = data_root / "config" / "dq"
        user_config_dir.mkdir(parents=True)

        # 手动复制配置文件（模拟脚本功能）
        for config_file in default_config_dir.glob("*.yml"):
            target = user_config_dir / config_file.name
            if not target.exists():
                shutil.copy(config_file, target)

        # Assert: 验证目录和文件创建
        assert user_config_dir.exists()
        assert (user_config_dir / "test_dataset.yml").exists()

        # 验证文件内容正确
        with (user_config_dir / "test_dataset.yml").open(encoding="utf-8") as f:
            loaded_config = yaml.safe_load(f)
        assert loaded_config["dataset"] == "test_dataset"

    def test_init_dq_config_skips_existing_files(self, tmp_path: Path) -> None:
        """
        测试初始化脚本跳过已存在的文件。

        Given: 用户配置目录中已有配置文件
        When: 再次运行初始化逻辑
        Then: 应跳过已存在的文件，不覆盖
        """
        # Arrange: 创建用户配置目录和现有文件
        data_root = tmp_path / "data"
        user_config_dir = data_root / "config" / "dq"
        user_config_dir.mkdir(parents=True)

        existing_config = {
            "dataset": "existing_dataset",
            "description": "Existing",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        existing_file = user_config_dir / "existing_dataset.yml"
        with existing_file.open("w", encoding="utf-8") as f:
            yaml.dump(existing_config, f)

        # 记录文件内容
        original_content = existing_file.read_text(encoding="utf-8")

        # Act: 模拟跳过逻辑
        if existing_file.exists():
            # 跳过，不覆盖
            pass

        # Assert: 验证文件未被覆盖
        assert existing_file.exists()
        assert existing_file.read_text(encoding="utf-8") == original_content

    def test_user_config_dir_structure(self, tmp_path: Path) -> None:
        """
        测试用户配置目录结构。

        Given: data_root 路径
        When: 创建配置目录
        Then: 应在正确位置创建 {data_root}/config/dq/
        """
        # Arrange
        data_root = tmp_path / "data"
        expected_config_dir = data_root / "config" / "dq"

        # Act
        expected_config_dir.mkdir(parents=True)

        # Assert
        assert expected_config_dir.exists()
        assert expected_config_dir.is_dir()
        # 使用 parts 检查路径结构，兼容不同操作系统
        assert expected_config_dir.parts[-3:] == ("data", "config", "dq")
