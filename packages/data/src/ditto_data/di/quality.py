"""Core 层组件注册 - DQ 质量引擎。"""

from collections.abc import Iterator
from pathlib import Path

import yaml
from dishka import Provider, Scope, provide
from ditto_infra.foundation.config import get_default_dq_rules_dir
from loguru import logger
from pydantic import ValidationError

from ditto_data.quality import QualityEngine
from ditto_data.quality.spec import DatasetRules, DQSpec

__all__ = ["QualityProvider"]


class QualityProvider(Provider):
    """
    Core 层 DQ 组件 Provider.

    仅注册 Core 层服务（DQSpec、QualityEngine），
    App 层 QualityService 已迁入 ditto_app.providers。
    """

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
        1. 默认配置: config/default/dq_rules/*.yml
        2. 用户配置: {data_root}/config/dq/*.yml (覆盖)

        Args:
            data_root: 数据根目录

        Returns:
            DQSpec: DQ 配置实例

        """
        # 1. 加载默认配置（使用标准路径发现）
        default_config_dir = get_default_dq_rules_dir()
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
