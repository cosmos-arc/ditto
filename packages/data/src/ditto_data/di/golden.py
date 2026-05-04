"""Engine 层组件注册 - 黄金数据集配置。"""

from pathlib import Path

import yaml
from dishka import Provider, Scope, provide
from ditto_platform.foundation import logger
from pydantic import ValidationError

from ditto_data.quality.config_paths import get_default_golden_dataset_path
from ditto_data.quality.golden import GoldenDatasetSpec

__all__ = ["GoldenDatasetProvider"]


class GoldenDatasetProvider(Provider):
    """黄金数据集配置 Provider。"""

    scope = Scope.APP

    def _load_from_file(self, path: Path) -> GoldenDatasetSpec | None:
        """
        从文件加载配置。

        Args:
            path: 配置文件路径

        Returns:
            GoldenDatasetSpec 实例，加载失败返回 None

        """
        if not path.exists():
            return None

        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                return None

            return GoldenDatasetSpec(**data)
        except (ValidationError, TypeError) as e:
            # TypeError: YAML 解析为非字典类型（如列表、标量）
            # ValidationError: Pydantic 验证失败
            logger.warning(
                "Invalid golden dataset config, using defaults",
                event="golden_config_invalid",
                file=str(path),
                error=str(e),
            )
            return None
        except yaml.YAMLError as e:
            logger.warning(
                "Failed to parse golden dataset YAML, using defaults",
                event="golden_config_parse_error",
                file=str(path),
                error=str(e),
            )
            return None

    @provide
    def golden_dataset_spec(self, data_root: Path) -> GoldenDatasetSpec | None:
        """
        加载黄金数据集配置。

        支持用户配置覆盖默认配置：
        1. 默认配置: config/default/golden_dataset.yml
        2. 用户配置: {data_root}/config/golden_dataset.yml (覆盖)

        Args:
            data_root: 数据根目录

        Returns:
            GoldenDatasetSpec | None: 黄金数据集配置实例，无配置时返回 None

        """
        # 1. 加载默认配置
        default_path = get_default_golden_dataset_path()
        default_spec = self._load_from_file(default_path)

        # 2. 加载用户配置（覆盖）
        user_path = Path(data_root) / "config" / "golden_dataset.yml"
        user_spec = self._load_from_file(user_path)

        # 3. 优先返回用户配置
        if user_spec:
            logger.debug(
                "Using user golden dataset config",
                event="golden_config_user",
                tickers=len(user_spec.tickers),
            )
            return user_spec

        if default_spec:
            logger.debug(
                "Using default golden dataset config",
                event="golden_config_default",
                tickers=len(default_spec.tickers),
            )
            return default_spec

        # 4. 无配置则返回空配置（禁用）
        logger.debug(
            "No golden dataset config found, feature disabled",
            event="golden_config_disabled",
        )
        return GoldenDatasetSpec()
