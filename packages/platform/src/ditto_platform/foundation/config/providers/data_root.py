"""数据根目录初始化提供者."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from ditto_platform.foundation.config.initializer import (
    InitResult,
    InitScope,
)


class DataRootInitProvider:
    """
    数据根目录初始化.

    职责：创建目录结构。目录列表由上层注入
    （来自 Data 层 DataStoreSettings.all_directories()）。
    """

    def __init__(self, directories: list[str]) -> None:
        self._directories = directories

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
        if not data_root.exists():
            return True
        return any(
            not (data_root / dir_path).exists() for dir_path in self._directories
        )

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
