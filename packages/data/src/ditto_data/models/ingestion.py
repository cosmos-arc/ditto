"""Ingestion metadata models for data tracking."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ============ New Ingestion System: Event Log + Cursor ============


class IngestionStatus(StrEnum):
    """Ingestion status for a specific trade date."""

    SUCCESS = "SUCCESS"  # Data successfully ingested
    FAIL = "FAIL"  # Ingestion failed (fetch error / DQ blocked / empty df)


@dataclass(frozen=True)
class IngestionLog:
    """
    Event log for a specific trade date (one record per date).

    Each trading day has exactly one record that can be updated on retry.
    Non-trading days are NOT recorded (check calendar table instead).

    Attributes:
        dataset: Dataset name (e.g., "stock_daily")
        source: Data source identifier (e.g., "tushare")
        trade_date: Trade date (YYYY-MM-DD)
        status: Current status (SUCCESS or FAIL)
        checksum: Data checksum (only when SUCCESS)
        rows: Number of rows (only when SUCCESS)
        error_code: Error code (only when FAIL)
        error_message: Error message (only when FAIL)
        attempts: Number of attempts (incremented on retry)
        first_attempt_at: First attempt timestamp (ISO format)
        last_attempt_at: Last attempt timestamp (ISO format)

    """

    dataset: str
    source: str
    trade_date: str
    status: IngestionStatus
    checksum: str | None = None
    rows: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempts: int = 1
    first_attempt_at: str | None = None
    last_attempt_at: str | None = None


@dataclass(frozen=True)
class IngestionCursor:
    """
    Cursor for tracking ingestion progress (redundant for fast queries).

    This is a denormalized cache for fast access to the last successful date.

    Attributes:
        dataset: Dataset name (e.g., "stock_daily")
        source: Data source identifier (e.g., "tushare")
        last_success: Last successful trade date (YYYY-MM-DD)
        last_attempted: Last attempted trade date (including FAIL) (YYYY-MM-DD)
        updated_at: Cursor update timestamp (ISO format)

    """

    dataset: str
    source: str
    last_success: str | None  # None if no successful ingestion yet
    last_attempted: str | None  # None if never attempted
    updated_at: str


# ============ New Ingestion System: Exceptions ============


class NotTradingDayError(Exception):
    """Raised when trying to ingest data for a non-trading day."""

    def __init__(self, trade_date: str) -> None:
        """
        Initialize NotTradingDayError.

        Args:
            trade_date: The non-trading date (YYYY-MM-DD).

        """
        self.trade_date = trade_date
        super().__init__(f"{trade_date} is not a trading day")


class DataChangedError(Exception):
    """Raised when data checksum changed and force=False."""

    def __init__(
        self,
        trade_date: str,
        old_checksum: str,
        new_checksum: str,
    ) -> None:
        """
        Initialize DataChangedError.

        Args:
            trade_date: The trade date (YYYY-MM-DD).
            old_checksum: Previous checksum.
            new_checksum: New checksum.

        """
        self.trade_date = trade_date
        self.old_checksum = old_checksum
        self.new_checksum = new_checksum
        super().__init__(
            f"Data changed for {trade_date}: checksum {old_checksum} → {new_checksum}. "
            + "Use force=True to overwrite."
        )


# ============ Late Arrival Policy ============


class DataLateArrivalPolicy(StrEnum):
    """
    数据摄入层延迟到达策略.

    控制写入层对 knowledge_date 晚于 trade_date 的数据的处理行为。
    与 Engine 层 ``LateArrivalPolicy``（研究快照级别）不同，此枚举面向
    数据摄入层，语义为写入时的实时决策。

    Attributes:
        REJECT: 超过 max_delay_days 的数据拒绝写入.
        ACCEPT: 始终接受，不做延迟检查.
        REBUILD: 接受写入，但标记需要重算受影响的因子.

    """

    REJECT = "reject"
    ACCEPT = "accept"
    REBUILD = "rebuild"


@dataclass(frozen=True)
class LateArrivalCheckResult:
    """
    延迟到达检查结果.

    Attributes:
        accepted: 数据是否被接受.
        needs_rebuild: 是否需要重算受影响的因子.
        delay_days: 延迟天数（knowledge_date - trade_date，最小为 0）.
        policy: 使用的策略.

    """

    accepted: bool
    needs_rebuild: bool
    delay_days: int
    policy: DataLateArrivalPolicy


class LateArrivalRejectedError(Exception):
    """延迟到达数据被拒绝时抛出."""

    def __init__(
        self,
        delay_days: int,
        max_delay_days: int,
        trade_date: str,
        knowledge_date: str,
    ) -> None:
        """
        初始化 LateArrivalRejectedError.

        Args:
            delay_days: 实际延迟天数.
            max_delay_days: 允许的最大延迟天数.
            trade_date: 交易日期 (YYYY-MM-DD).
            knowledge_date: 数据可知日期 (YYYY-MM-DD).

        """
        self.delay_days = delay_days
        self.max_delay_days = max_delay_days
        self.trade_date = trade_date
        self.knowledge_date = knowledge_date
        super().__init__(
            f"数据延迟到达被拒绝: trade_date={trade_date}, "
            + f"knowledge_date={knowledge_date}, "
            + f"延迟 {delay_days} 天超过阈值 {max_delay_days} 天"
        )


# ============ Result Models (from ditto_data consolidation) ============

# InstrumentIngestParams is now in ditto_kernel.types (re-exported above)


@dataclass(frozen=True)
class IngestionResult:
    """数据摄取结果。"""

    dataset: str
    trade_date: str
    status: str  # "success" | "skipped" | "failed"
    row_count: int | None = None
    checksum: str | None = None
    message: str = ""
    error: str | None = None


@dataclass(frozen=True)
class ResultCounts:
    """摄取结果统计。"""

    success: int
    failed: int
    skipped: int


@dataclass(frozen=True)
class BackfillResult:
    """回补结果统计。"""

    dataset: str
    total_dates: int
    success_count: int
    skipped_count: int
    failed_count: int
    results: tuple[IngestionResult, ...]


@dataclass(frozen=True)
class RetryResult:
    """重试结果。"""

    dataset: str
    total_failed: int
    retried_count: int
    success_count: int
    still_failed_count: int
    results: tuple[IngestionResult, ...]
