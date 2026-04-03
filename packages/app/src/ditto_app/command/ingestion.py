"""入库命令 DTO — 单次写入操作的输入参数."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class IngestDateCommand:
    """单日入库命令."""

    dataset: str
    trade_date: date
    force: bool = False


@dataclass(frozen=True)
class IngestRangeCommand:
    """日期范围入库命令."""

    dataset: str
    start_date: date
    end_date: date
    force: bool = False
    parallel: int = 4


@dataclass(frozen=True)
class BackfillRangeCommand:
    """缺失数据回填命令."""

    dataset: str
    start_date: date
    end_date: date
    parallel: int = 4
