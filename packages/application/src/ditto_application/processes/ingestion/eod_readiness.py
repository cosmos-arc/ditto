"""
EOD 数据就绪核验：以账本证据为准，缺则重拉，仍缺交由宿主告警。

与活体选池的 ``latest_complete_session`` 共用同一条就绪规则
（``latest_row_attested_day``）：一个交易日只有存在"已完成 + 载荷留存
+ 行数 > 0"的窗口覆盖才算就绪——空观察（供应商答"无数据"）不算，
#583 切片 B 之后同晚空响应也不再产生这类假证据。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from ditto_application.processes.selection.assemble_facts import (
    SnapshotCoverageIndex,
    latest_row_attested_day,
)

__all__ = [
    "DEFAULT_EOD_VERIFICATION_DATASETS",
    "EodDatasetReadiness",
    "EodReadinessReport",
    "EodReadinessVerifier",
]

# EOD 关键路径五数据集（每日收盘信号车道的前置）。
DEFAULT_EOD_VERIFICATION_DATASETS: tuple[str, ...] = (
    "stock_daily",
    "adj_factor",
    "stock_status",
    "stock_limit",
    "index_daily",
)


@dataclass(frozen=True)
class EodDatasetReadiness:
    """One dataset's ledger-attested readiness for the target day."""

    dataset: str
    ready: bool
    attested_through: date | None


@dataclass(frozen=True)
class EodReadinessReport:
    """Per-dataset readiness after optional re-ingestion."""

    trade_date: date
    datasets: tuple[EodDatasetReadiness, ...]
    refetched: tuple[str, ...]

    @property
    def missing(self) -> tuple[str, ...]:
        """Datasets without row-attested coverage of the target day."""
        return tuple(item.dataset for item in self.datasets if not item.ready)


class EodReadinessVerifier:
    """Verify target-day readiness from ledger evidence and refetch gaps."""

    def __init__(
        self,
        index: SnapshotCoverageIndex,
        *,
        reingest: Callable[[str, str], object] | None = None,
    ) -> None:
        self._index = index
        self._reingest = reingest

    def _attestations(
        self, datasets: Sequence[str], trade_date: date
    ) -> tuple[EodDatasetReadiness, ...]:
        items = []
        for dataset in datasets:
            windows = self._index.windows(dataset)
            attested = latest_row_attested_day(windows, today=trade_date)
            covers = any(
                window.request_start <= trade_date <= window.request_end
                and window.row_count > 0
                for window in windows
            )
            items.append(
                EodDatasetReadiness(
                    dataset=dataset,
                    ready=covers,
                    attested_through=attested,
                )
            )
        return tuple(items)

    def verify(
        self,
        datasets: Sequence[str] = DEFAULT_EOD_VERIFICATION_DATASETS,
        *,
        trade_date: date,
        retry: bool = True,
    ) -> EodReadinessReport:
        """Check readiness; refetch gaps once and re-read the ledger."""
        first = self._attestations(datasets, trade_date)
        missing = tuple(item.dataset for item in first if not item.ready)
        if not retry or not missing or self._reingest is None:
            return EodReadinessReport(
                trade_date=trade_date, datasets=first, refetched=()
            )
        for dataset in missing:
            self._reingest(dataset, trade_date.isoformat())
        return EodReadinessReport(
            trade_date=trade_date,
            datasets=self._attestations(datasets, trade_date),
            refetched=missing,
        )
