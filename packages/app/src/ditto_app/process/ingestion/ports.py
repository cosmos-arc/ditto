"""
摄取流程 Handler Protocol — 解耦 process 对 command 具体类的依赖.

process 子模块通过 Protocol 定义所需 Handler 接口，
由 DI 层（coordinator_factory）在运行时注入具体实现。
"""

from __future__ import annotations

from typing import Protocol

import polars as pl
from ditto_data.models.ingestion import IngestionResult

from ditto_app.contracts import CheckDataQualityCommand, IngestDateCommand


class IngestDateHandlerProtocol(Protocol):
    """单日入库 Handler 接口."""

    def handle(self, command: IngestDateCommand) -> IngestionResult:
        """处理单日入库命令."""
        ...


class QualityCheckerProtocol(Protocol):
    """数据质量检查 Handler 接口."""

    def handle(self, cmd: CheckDataQualityCommand) -> tuple[pl.DataFrame, bool]:
        """执行数据质量检查."""
        ...


__all__ = ["IngestDateHandlerProtocol", "QualityCheckerProtocol"]
