"""Ingestion metadata models for data tracking."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

# ============ New Ingestion System: Event Log + Cursor ============


class IngestionStatus(StrEnum):
    """Ingestion status for a specific trade date."""

    SUCCESS = "SUCCESS"  # Data successfully ingested
    FAIL = "FAIL"  # Ingestion failed (fetch error / DQ blocked / empty df)


class IngestionFailureKind(StrEnum):
    """
    摄取失败的可行动分类（#623）。

    与 :class:`IngestionStatus` 正交：status 只说明成败，kind 说明失败后
    该做什么——自动重试（transient）、人工修复（permanent）、覆盖缺口
    裁定（source_missing / unsupported）。正常无事件不是失败，零行
    SUCCESS 不进入本分类。
    """

    TRANSIENT = "transient"  # 限流/网络/供应商晚发——自动重试有意义
    PERMANENT = "permanent"  # 代码/配置/数据质量——重试无意义，保留原因人工处理
    SOURCE_MISSING = "source_missing"  # 源可达但无该数据（覆盖缺口），不按日盲目回补
    UNSUPPORTED = "unsupported"  # 管线声明该源不支持该数据集（能力缺口，非故障）


@dataclass(frozen=True)
class IngestionFailedErrorGroup:
    """
    One (dataset, error_code) failure summary for compensation selection (#623).

    Reader 层投影：仅原始计数，无分类——失败分类词汇表的唯一权威
    实现是本模块的 :data:`INGESTION_ERROR_CODE_KINDS`。
    """

    dataset: str
    error_code: str | None
    failure_count: int
    oldest_trade_date: str | None
    newest_trade_date: str | None


# 闭合错误码词汇表：error_code → 失败分类。未知码 fail-closed 归
# permanent（不可分类的失败不自动重试，由人工裁决——与 #608 响亮失败
# 一致）。唯一例外是 FETCH_ERROR：它本身是已知类别"取数失败但原因
# 未细分"（供应商 5xx 等），本质上多为瞬态，默认进入重试并由
# attempts 上界兜底——与未知码的 fail-closed 区分是刻意设计。
INGESTION_ERROR_CODE_KINDS: Mapping[str, IngestionFailureKind] = MappingProxyType(
    {
        # 瞬态：下一预算窗口/网络恢复/供应商发布后重试可恢复
        "RATE_LIMIT": IngestionFailureKind.TRANSIENT,
        "NETWORK_ERROR": IngestionFailureKind.TRANSIENT,
        "FETCH_ERROR": IngestionFailureKind.TRANSIENT,
        "EMPTY_DATA_UNEXPECTED": IngestionFailureKind.TRANSIENT,
        # 永久：重试不改变结果
        "UNKNOWN_ERROR": IngestionFailureKind.PERMANENT,
        "WRITE_ERROR": IngestionFailureKind.PERMANENT,
        "DQ_BLOCKED": IngestionFailureKind.PERMANENT,
        # 认证/权限类：凭证或接口权限问题，人工处理后才会变化
        "SOURCE_AUTH_ERROR": IngestionFailureKind.PERMANENT,
        "SOURCE_PERMISSION_DENIED": IngestionFailureKind.PERMANENT,
        "PARTITION_INTENT_FAILED": IngestionFailureKind.PERMANENT,
        "PARTITION_LIFECYCLE_FAILED": IngestionFailureKind.PERMANENT,
        "PARTITION_COMPLETE_FAILED": IngestionFailureKind.PERMANENT,
        "PARTITION_FAILURE_RECORD_FAILED": IngestionFailureKind.PERMANENT,
        "SNAPSHOT_WRITE_FAILED": IngestionFailureKind.PERMANENT,
        "SNAPSHOT_CANONICAL_DRIFT": IngestionFailureKind.PERMANENT,
        "CATALOG_WRITE_FAILED": IngestionFailureKind.PERMANENT,
        "CATALOG_EVIDENCE_FAILED": IngestionFailureKind.PERMANENT,
        "SUCCESS_LOG_WRITE_FAILED": IngestionFailureKind.PERMANENT,
        "PIT_SNAPSHOT_MISSING": IngestionFailureKind.PERMANENT,
        "PIT_CUTOFF_DATE_INVALID": IngestionFailureKind.PERMANENT,
        "PIT_KNOWLEDGE_DATE_MISSING": IngestionFailureKind.PERMANENT,
        "PIT_KNOWLEDGE_DATE_INVALID": IngestionFailureKind.PERMANENT,
        "PIT_KNOWLEDGE_DATE_AFTER_CUTOFF": IngestionFailureKind.PERMANENT,
        "INGESTION_QUALITY_CHECK_REQUIRED": IngestionFailureKind.PERMANENT,
        "QUALITY_CHECK_REQUIRED": IngestionFailureKind.PERMANENT,
        "EVIDENCE_COMMITTER_REQUIRED": IngestionFailureKind.PERMANENT,
        "R2_PROVIDER_PAYLOAD_STORE_REQUIRED": IngestionFailureKind.PERMANENT,
        "R2_PROVIDER_PAYLOAD_RETENTION_FAILED": IngestionFailureKind.PERMANENT,
        "R2_EVIDENCE_COMMIT_FAILED": IngestionFailureKind.PERMANENT,
        # DQ 证据校验失败（载荷与声明不符/证据无效）= 完整性问题
        "INGESTION_DATASET_MISMATCH": IngestionFailureKind.PERMANENT,
        "INGESTION_DATE_MISMATCH": IngestionFailureKind.PERMANENT,
        "PERSISTED_ASOF_EVIDENCE_INVALID": IngestionFailureKind.PERMANENT,
        # 源缺失：覆盖缺口，另行裁定（P0 覆盖合同），不按日盲目重试
        "EMPTY_DATA": IngestionFailureKind.SOURCE_MISSING,
        # 不支持：源能力声明（如 etf_reference 仅 config 源），非故障
        "SOURCE_UNSUPPORTED": IngestionFailureKind.UNSUPPORTED,
    }
)


def classify_ingestion_failure(error_code: str | None) -> IngestionFailureKind:
    """
    按 error_code 分类摄取失败。

    未知码与缺失码 fail-closed 归 :attr:`PERMANENT`：不可分类的失败不
    进入自动重试，由人工裁决（#623）。
    """
    if error_code is None:
        return IngestionFailureKind.PERMANENT
    return INGESTION_ERROR_CODE_KINDS.get(error_code, IngestionFailureKind.PERMANENT)


def is_retryable_ingestion_failure(error_code: str | None) -> bool:
    """该失败是否应进入自动重试（瞬态类）。"""
    return classify_ingestion_failure(error_code) is IngestionFailureKind.TRANSIENT


# 瞬态错误码集合（由词汇表派生的唯一权威值）——存储层 SQL 过滤与
# 应用层分类共用，避免"SQL LIMIT 先截断、Python 再过滤"饿死瞬态行
# （correctness #623 F1）。
TRANSIENT_ERROR_CODES: frozenset[str] = frozenset(
    code
    for code, kind in INGESTION_ERROR_CODE_KINDS.items()
    if kind is IngestionFailureKind.TRANSIENT
)


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


# ============ Result Models (from ditto_data consolidation) ============

# Instrument ingestion parameters live in ditto_kernel.instrument.


@dataclass(frozen=True)
class IngestionSnapshotEvidence:
    """Explicit evidence for a sparse dataset's persisted PIT snapshot."""

    kind: Literal["persisted_asof_catalog_snapshot"]
    source: str
    signal_date: str
    checked_at: str
    effective_partition_date: str
    source_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    row_count: int
    freshness_sla_hours: int


@dataclass(frozen=True)
class IngestionQualityEvidence:
    """Explicit write-time quality-gate attestation for one ingestion outcome."""

    kind: Literal["write_time_l1_l2", "persisted_ingestion_l1_l2", "no_new_rows"]
    status: Literal["passed", "not_applicable_no_new_rows"]
    source: str
    trade_date: str
    levels: tuple[Literal["l1", "l2"], ...]
    row_count: int
    checksum: str | None = None


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
    snapshot_evidence: IngestionSnapshotEvidence | None = None
    quality_evidence: IngestionQualityEvidence | None = None


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
    """重试结果统计."""

    dataset: str
    total_failed: int
    retried_count: int
    success_count: int
    still_failed_count: int
    results: tuple[IngestionResult, ...]
    # #623：满足尝试次数门槛但按失败分类被排除出自动重试的日志
    # （永久/源缺失/不支持）——保留原因与补偿范围供人工裁决。
    excluded_failures: tuple[IngestionLog, ...] = ()
