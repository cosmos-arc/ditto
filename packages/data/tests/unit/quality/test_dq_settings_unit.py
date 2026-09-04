from __future__ import annotations

from pathlib import Path

import pytest
from ditto_data.quality.config import DQSettings
from pydantic import ValidationError


def test_config_root_is_required() -> None:
    """Data 配置模型不得自行发现部署或 checkout 根目录。"""
    with pytest.raises(ValidationError, match="config_root"):
        DQSettings.model_validate({})


def test_custom_config_root(tmp_path: Path) -> None:
    settings = DQSettings(config_root=tmp_path)
    assert settings.config_root == tmp_path


def test_rules_path_relative_to_config_root(tmp_path: Path) -> None:
    settings = DQSettings(config_root=tmp_path, rules_dir="custom/rules")
    assert settings.rules_path == tmp_path / "custom" / "rules"


def test_rules_path_absolute_unchanged(tmp_path: Path) -> None:
    abs_path = Path("/absolute/rules")
    settings = DQSettings(config_root=tmp_path, rules_dir=str(abs_path))
    assert settings.rules_path == abs_path


def test_get_rules_paths_env_rules_found(tmp_path: Path) -> None:
    env_dir = tmp_path / "config" / "testing" / "dq_rules"
    env_dir.mkdir(parents=True)
    env_file = env_dir / "stock_daily.yml"
    env_file.write_text("rules: []\n", encoding="utf-8")

    settings = DQSettings(environment="testing", config_root=tmp_path)
    paths = settings.get_rules_paths("stock_daily")
    assert env_file in paths


def test_get_rules_paths_default_rules_found(tmp_path: Path) -> None:
    default_dir = tmp_path / "config" / "default" / "dq_rules"
    default_dir.mkdir(parents=True)
    default_file = default_dir / "stock_daily.yml"
    default_file.write_text("rules: []\n", encoding="utf-8")

    settings = DQSettings(environment="testing", config_root=tmp_path)
    paths = settings.get_rules_paths("stock_daily")
    assert any(p == default_file for p in paths)


def test_get_rules_paths_empty_when_none_exist(tmp_path: Path) -> None:
    settings = DQSettings(config_root=tmp_path)
    paths = settings.get_rules_paths("nonexistent_dataset")
    assert paths == []


def test_cwd_independence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DQSettings 路径解析应不依赖进程 CWD。"""

    # 创建固定的 config_root 和规则文件
    rules_dir = tmp_path / "config" / "default" / "dq_rules"
    rules_dir.mkdir(parents=True)
    rules_file = rules_dir / "test.yml"
    rules_file.write_text("rules: []\n", encoding="utf-8")

    settings = DQSettings(config_root=tmp_path)

    # 切换 CWD 到无关目录
    other_dir = tmp_path / "unrelated"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    # 路径解析仍然基于 config_root，不依赖 CWD
    assert settings.config_root == tmp_path
    assert settings.rules_path == tmp_path / "config" / "default" / "dq_rules"
    assert rules_file in settings.get_rules_paths("test")
