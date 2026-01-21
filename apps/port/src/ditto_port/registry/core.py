"""Core 层组件注册."""

from collections.abc import Iterator
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_core.quality import QualityEngine

__all__ = ["CoreProvider"]


class CoreProvider(Provider):
    """Core 层组件 Provider."""

    scope = Scope.APP

    @provide
    def dq_engine(self, data_root: Path) -> Iterator[QualityEngine]:
        """
        数据质量引擎（应用层 DQ 检查使用）.

        Args:
            data_root: 数据根目录

        Yields:
            QualityEngine: DQ 引擎实例

        """
        engine = QualityEngine(data_root=data_root)
        yield engine
