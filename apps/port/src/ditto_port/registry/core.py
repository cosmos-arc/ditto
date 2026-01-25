"""Core 层组件注册."""

from collections.abc import Iterator
from pathlib import Path

import yaml
from dishka import Provider, Scope, provide
from ditto_core.quality import QualityEngine
from ditto_core.quality.spec import DatasetRules, DQSpec
from loguru import logger
from pydantic import ValidationError

__all__ = ["CoreProvider"]


class CoreProvider(Provider):
    """Core 层组件 Provider."""

    scope = Scope.APP

    def _load_dq_spec(self, config_dir: Path) -> DQSpec:
        """
        从目录加载 DQ 配置 (Port 层内部方法).

        Args:
            config_dir: 配置目录路径

        Returns:
            DQSpec 实例

        """
        if not config_dir.exists():
            return DQSpec()

        datasets: dict[str, DatasetRules] = {}

        for yaml_file in config_dir.glob("*.yml"):
            try:
                with yaml_file.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data and "dataset" in data:
                    dataset_rules = DatasetRules(**data)
                    datasets[dataset_rules.dataset] = dataset_rules
            except (ValidationError, ValueError) as e:
                logger.warning(
                    "Invalid DQ config file, skipping",
                    event="dq_config_invalid",
                    file=str(yaml_file),
                    error=str(e),
                )
                continue
            except yaml.YAMLError as e:
                logger.warning(
                    "Failed to parse YAML config, skipping",
                    event="dq_config_parse_error",
                    file=str(yaml_file),
                    error=str(e),
                )
                continue

        return DQSpec(datasets=datasets)

    @provide
    def dq_spec(self, data_root: Path) -> DQSpec:
        """
        加载 DQ 配置规范.

        支持用户配置覆盖默认配置：
        1. 默认配置: {package_dir}/config/dq_rules/*.yml
        2. 用户配置: {data_root}/config/dq/*.yml (覆盖)

        Args:
            data_root: 数据根目录

        Returns:
            DQSpec: DQ 配置实例

        """
        # 1. 加载包内默认配置
        default_config_dir = (
            Path(__file__).parent.parent.parent.parent.parent
            / "packages"
            / "core"
            / "src"
            / "ditto_core"
            / "config"
            / "dq_rules"
        )
        default_config = self._load_dq_spec(default_config_dir)

        # 2. 加载用户自定义配置（覆盖默认配置）
        user_config_dir = Path(data_root) / "config" / "dq"
        user_config = self._load_dq_spec(user_config_dir)

        # 3. 合并配置（用户配置覆盖默认配置）
        merged_datasets = default_config.datasets.copy()
        merged_datasets.update(user_config.datasets)

        return DQSpec(datasets=merged_datasets)

    @provide
    def dq_engine(self, dq_spec: DQSpec) -> Iterator[QualityEngine]:
        """
        数据质量引擎（应用层 DQ 检查使用）.

        Args:
            dq_spec: DQ 配置规范（通过 DI 注入）

        Yields:
            QualityEngine: DQ 引擎实例

        """
        engine = QualityEngine(config=dq_spec)
        yield engine
