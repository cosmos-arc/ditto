"""数据根目录初始化提供者."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from ditto_infra.foundation.config.initializer import (
    ConfigInitProvider,
    InitResult,
    InitScope,
)


class DataRootInitProvider(ConfigInitProvider):
    """
    数据根目录初始化.

    职责：创建 DataStoreSettings 中定义的所有目录结构。
    """

    def __init__(self, directories: list[str] | None = None) -> None:
        """
        初始化.

        Args:
            directories: 需要创建的目录列表（相对于 data_root）。
                         None 表示使用默认列表。

        """
        self._directories = directories or self._default_directories()

    @property
    def name(self) -> str:
        """返回初始化提供者名称."""
        return "data_root"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """检查 data_root 是否需要初始化."""
        return not data_root.exists()

    def initialize(self, data_root: Path) -> InitResult:
        """创建目录结构."""
        try:
            created: list[str] = []
            for dir_path in self._directories:
                full_path = data_root / dir_path
                if not full_path.exists():
                    full_path.mkdir(parents=True, exist_ok=True)
                    created.append(dir_path)

            logger.info(
                "DataRoot directories created",
                event="dataroot_init",
                count=len(created),
            )

            return InitResult(
                provider=self.name,
                success=True,
                message=f"Created {len(created)} directories",
            )

        except Exception as e:
            logger.exception("Failed to create DataRoot directories")
            return InitResult(
                provider=self.name,
                success=False,
                message=f"Failed: {e}",
            )

    @staticmethod
    def _default_directories() -> list[str]:
        """默认目录列表（与 DataStoreSettings 属性对应）."""
        return [
            # 市场数据
            "market/stock/bars/daily",
            "market/etf/bars/daily",
            "market/index/bars/daily",
            "market/stock/status",
            "market/etf/status",
            "market/stock/adj",
            "market/etf/adj",
            "market/etf/nav",
            # 元数据
            "metadata",
            # 资金流
            "capital/flow",
            "capital/margin",
            "capital/top_board",
            "capital/limit_board",
            "capital/chip",
            # 基本面
            "fundamental/financial",
            "fundamental/indicator",
            "fundamental/forecast",
            "fundamental/holding",
            # 特征
            "features/technical/price",
            "features/technical/indicators_narrow",
            "features/technical/indicators_wide",
            # 因子
            "factors/narrow/style",
            "factors/wide/style",
            "factors/factors_narrow",
            "factors/factors_wide",
            # 宏观
            "macro/indicators",
            # 通用
            "logs",
            "backups",
            "temp",
            "db",
            "locks",
        ]
