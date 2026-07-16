"""摄取结果处理 — count_results + IngestionResultHandler."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import cast

import polars as pl
from ditto_data.errors import SourceFetchError
from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.models.ingestion import (
    IngestionLog,
    IngestionQualityEvidence,
    IngestionResult,
    IngestionSnapshotEvidence,
    IngestionStatus,
    ResultCounts,
)
from ditto_platform.foundation import WriteResult

from ditto_application.catalog_freshness import (
    aggregate_source_snapshot_ids,
    catalog_source_snapshot_id,
)
from ditto_application.processes.ingestion.sparse_pit import SparsePITCutoffError


@dataclass(frozen=True)
class PersistedIngestionDQEvidence:
    """Exact-date L1/L2 evidence implied by a persisted ingestion outcome."""

    passed: bool
    trade_date: str
    checksum: str | None = None
    row_count: int | None = None
    snapshot_id: str | None = None
    evidence: dict[str, object] | None = None
    quality_evidence: dict[str, object] | None = None
    error: str | None = None


def persisted_ingestion_dq_evidence(  # noqa: PLR0911 - fail-closed parser
    payload: Mapping[str, object],
    *,
    dataset: str,
    trade_date: str,
) -> PersistedIngestionDQEvidence:
    """Validate whether one serialized ingestion result proves exact-date DQ."""
    payload_dataset = payload.get("dataset")
    if payload_dataset != dataset:
        return PersistedIngestionDQEvidence(
            passed=False,
            trade_date=trade_date,
            error="INGESTION_DATASET_MISMATCH",
        )

    payload_date = payload.get("trade_date")
    if payload_date != trade_date:
        return PersistedIngestionDQEvidence(
            passed=False,
            trade_date=trade_date,
            error="INGESTION_DATE_MISMATCH",
        )

    error = payload.get("error")
    status = payload.get("status")
    if status not in {"success", "skipped"}:
        return PersistedIngestionDQEvidence(
            passed=False,
            trade_date=trade_date,
            error=error if isinstance(error, str) and error else "INGESTION_NOT_READY",
        )

    if status == "skipped" and isinstance(error, str) and error:
        return PersistedIngestionDQEvidence(
            passed=False,
            trade_date=trade_date,
            error=error,
        )

    quality_evidence, quality_error = _validated_quality_evidence(
        payload,
        dataset=dataset,
        trade_date=trade_date,
    )
    if quality_evidence is None:
        return PersistedIngestionDQEvidence(
            passed=False,
            trade_date=trade_date,
            error=quality_error,
        )

    raw_snapshot_evidence = payload.get("snapshot_evidence")
    if isinstance(raw_snapshot_evidence, dict):
        asof_evidence = validated_asof_snapshot_evidence(
            cast(dict[object, object], raw_snapshot_evidence),
            trade_date=trade_date,
        )
        if asof_evidence is None:
            return PersistedIngestionDQEvidence(
                passed=False,
                trade_date=trade_date,
                error="PERSISTED_ASOF_EVIDENCE_INVALID",
            )
        snapshot_id = cast(str, asof_evidence["source_snapshot_id"])
        asof_row_count = cast(int, asof_evidence["row_count"])
        return PersistedIngestionDQEvidence(
            passed=True,
            trade_date=trade_date,
            row_count=asof_row_count,
            snapshot_id=snapshot_id,
            evidence=asof_evidence,
            quality_evidence=quality_evidence,
        )

    checksum = payload.get("checksum")
    row_count = payload.get("row_count")
    if (
        not isinstance(checksum, str)
        or not checksum.strip()
        or not isinstance(row_count, int)
        or isinstance(row_count, bool)
        or row_count < 0
    ):
        return PersistedIngestionDQEvidence(
            passed=False,
            trade_date=trade_date,
            error=(
                error
                if isinstance(error, str) and error
                else "PERSISTED_INGESTION_EVIDENCE_INVALID"
            ),
        )

    return PersistedIngestionDQEvidence(
        passed=True,
        trade_date=trade_date,
        checksum=checksum,
        row_count=row_count,
        snapshot_id=checksum,
        evidence={
            "kind": "persisted_ingestion_l1_l2",
            "trade_date": trade_date,
            "checksum": checksum,
            "row_count": row_count,
        },
        quality_evidence=quality_evidence,
    )


def _validated_quality_evidence(
    payload: Mapping[str, object],
    *,
    dataset: str,
    trade_date: str,
) -> tuple[dict[str, object] | None, str]:
    raw = payload.get("quality_evidence")
    if not isinstance(raw, dict):
        return None, "INGESTION_QUALITY_EVIDENCE_MISSING"
    evidence = cast(dict[object, object], raw)
    kind = evidence.get("kind")
    status = evidence.get("status")
    source = evidence.get("source")
    evidence_date = evidence.get("trade_date")
    raw_levels = evidence.get("levels")
    evidence_rows = evidence.get("row_count")
    checksum = evidence.get("checksum")
    if not (
        isinstance(source, str)
        and source
        and evidence_date == trade_date
        and isinstance(raw_levels, (list, tuple))
        and isinstance(evidence_rows, int)
        and not isinstance(evidence_rows, bool)
        and evidence_rows >= 0
    ):
        return None, "INGESTION_QUALITY_EVIDENCE_INVALID"
    levels = tuple(cast(list[object] | tuple[object, ...], raw_levels))
    payload_rows = payload.get("row_count")
    raw_snapshot = payload.get("snapshot_evidence")
    if isinstance(raw_snapshot, dict):
        if not isinstance(payload_rows, int) or isinstance(payload_rows, bool):
            return None, "INGESTION_QUALITY_EVIDENCE_INVALID"
        if payload_rows == 0:
            valid = (
                kind == "no_new_rows"
                and status == "not_applicable_no_new_rows"
                and levels == ()
                and evidence_rows == 0
                and checksum is None
            )
        else:
            expected_snapshot_id = (
                catalog_source_snapshot_id(
                    dataset=dataset,
                    trade_date=trade_date,
                    source=source,
                    checksum=checksum,
                    l1_l2_attested=True,
                )
                if isinstance(checksum, str) and checksum
                else None
            )
            raw_snapshot_ids = cast(dict[object, object], raw_snapshot).get(
                "source_snapshot_ids"
            )
            valid = (
                kind in {"write_time_l1_l2", "persisted_ingestion_l1_l2"}
                and status == "passed"
                and levels == ("l1", "l2")
                and evidence_rows == payload_rows
                and expected_snapshot_id is not None
                and isinstance(raw_snapshot_ids, (list, tuple))
                and expected_snapshot_id in raw_snapshot_ids
            )
    else:
        valid = (
            kind in {"write_time_l1_l2", "persisted_ingestion_l1_l2"}
            and status == "passed"
            and levels == ("l1", "l2")
            and evidence_rows == payload_rows
            and checksum == payload.get("checksum")
            and isinstance(checksum, str)
            and bool(checksum)
        )
    if not valid:
        return None, "INGESTION_QUALITY_EVIDENCE_INVALID"
    return {
        "kind": ("persisted_ingestion_l1_l2" if status == "passed" else "no_new_rows"),
        "status": cast(str, status),
        "source": source,
        "trade_date": trade_date,
        "levels": list(cast(tuple[str, ...], levels)),
        "row_count": evidence_rows,
        "checksum": checksum if isinstance(checksum, str) else None,
    }, ""


def validated_asof_snapshot_evidence(  # noqa: PLR0911 - fail-closed parser
    evidence: Mapping[object, object],
    *,
    trade_date: str,
) -> dict[str, object] | None:
    """Validate and normalize one serialized cumulative as-of snapshot."""
    if (
        evidence.get("kind") != "persisted_asof_catalog_snapshot"
        or evidence.get("signal_date") != trade_date
    ):
        return None
    source = evidence.get("source")
    checked_at = evidence.get("checked_at")
    effective_date = evidence.get("effective_partition_date")
    snapshot_id = evidence.get("source_snapshot_id")
    raw_snapshot_ids = evidence.get("source_snapshot_ids")
    row_count = evidence.get("row_count")
    sla_hours = evidence.get("freshness_sla_hours")
    if not (
        isinstance(source, str)
        and source
        and isinstance(checked_at, str)
        and checked_at
        and isinstance(effective_date, str)
        and isinstance(snapshot_id, str)
        and snapshot_id
        and isinstance(raw_snapshot_ids, (list, tuple))
        and isinstance(row_count, int)
        and not isinstance(row_count, bool)
        and row_count >= 0
        and isinstance(sla_hours, int)
        and not isinstance(sla_hours, bool)
        and sla_hours > 0
    ):
        return None
    try:
        checked = datetime.fromisoformat(checked_at)
        signal_day = date.fromisoformat(trade_date)
        effective_day = date.fromisoformat(effective_date)
    except ValueError:
        return None
    if checked.tzinfo is None or effective_day > signal_day:
        return None
    if (signal_day - effective_day).days * 24 > sla_hours:
        return None
    snapshot_values = cast(list[object] | tuple[object, ...], raw_snapshot_ids)
    snapshot_ids = tuple(
        item for item in snapshot_values if isinstance(item, str) and item
    )
    if (
        len(snapshot_ids) != len(snapshot_values)
        or tuple(sorted(set(snapshot_ids))) != snapshot_ids
        or aggregate_source_snapshot_ids(snapshot_ids) != snapshot_id
    ):
        return None
    return {
        "kind": "persisted_asof_catalog_snapshot",
        "source": source,
        "signal_date": trade_date,
        "checked_at": checked_at,
        "effective_partition_date": effective_date,
        "source_snapshot_id": snapshot_id,
        "source_snapshot_ids": list(snapshot_ids),
        "row_count": row_count,
        "freshness_sla_hours": sla_hours,
    }


def count_results(
    results: list[IngestionResult] | dict[str, dict[str, object]],
) -> ResultCounts:
    """
    统计摄取结果。

    Args:
        results: 摄取结果列表或字典

    Returns:
        ResultCounts: 包含 success/failed/skipped 计数

    Examples:
        >>> results = [
        ...     IngestionResult(
        ...         dataset="stock_daily",
        ...         trade_date="2024-01-01",
        ...         status="success",
        ...     ),
        ...     IngestionResult(
        ...         dataset="stock_daily",
        ...         trade_date="2024-01-02",
        ...         status="failed",
        ...         error="FETCH_ERROR",
        ...     ),
        ... ]
        >>> counts = count_results(results)
        >>> counts.success, counts.failed, counts.skipped
        (1, 1, 0)

        >>> # 字典类型结果
        >>> dict_results = {
        ...     "task1": {"status": "success"},
        ...     "task2": {"status": "failed"},
        ... }
        >>> counts = count_results(dict_results)
        >>> counts.success, counts.failed, counts.skipped
        (1, 1, 0)

    """
    if isinstance(results, list):
        # 处理 IngestionResult 列表
        statuses = [r.status for r in results if hasattr(r, "status")]
    else:
        # 处理字典类型结果
        statuses = [v.get("status") for v in results.values() if "status" in v]

    # 使用 Counter 统计
    counter = Counter(statuses)

    return ResultCounts(
        success=counter.get("success", 0),
        failed=counter.get("failed", 0),
        skipped=counter.get("skipped", 0),
    )


class IngestionResultHandler:
    """
    摄取结果处理器。

    负责将摄取操作的各种结果转换为 IngestionResult 并记录日志。
    """

    def __init__(
        self, ingestion_log_store: IngestionLogStore | None, source_name: str
    ) -> None:
        """
        初始化 IngestionResultHandler。

        Args:
            ingestion_log_store: IngestionLogStore 实例，用于访问 ingestion_log
            source_name: 数据源名称

        """
        self._ingestion_log_store = ingestion_log_store
        self._source_name = source_name

    def _save_log(self, log: IngestionLog) -> None:
        """保存日志（如果提供了 ingestion_log_store）。"""
        if self._ingestion_log_store:
            self._ingestion_log_store.save_log(log)

    def handle_fetch_error(
        self, dataset: str, trade_date: str, error: SourceFetchError
    ) -> IngestionResult:
        """
        处理数据获取错误。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            error: 获取错误

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="FETCH_ERROR",
                error_message=str(error),
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="FETCH_ERROR",
            message=f"获取数据失败: {error}",
        )

    def handle_unknown_error(
        self, dataset: str, trade_date: str, error: Exception
    ) -> IngestionResult:
        """
        处理未知错误。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            error: 异常对象

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="UNKNOWN_ERROR",
                error_message=f"{type(error).__name__}: {error}",
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="UNKNOWN_ERROR",
            message=f"未知错误: {error}",
        )

    def handle_empty_data(self, dataset: str, trade_date: str) -> IngestionResult:
        """
        处理空数据。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="EMPTY_DATA",
                error_message="获取的数据为空",
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="EMPTY_DATA",
            message="获取的数据为空",
        )

    def handle_empty_success(
        self,
        dataset: str,
        trade_date: str,
        *,
        message: str = "无新数据",
        snapshot_evidence: IngestionSnapshotEvidence | None = None,
        quality_evidence: IngestionQualityEvidence | None = None,
    ) -> IngestionResult:
        """
        处理允许为空的稀疏事件数据。

        这类数据集在非披露日返回空数据是正常状态，应覆盖旧失败日志。
        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.SUCCESS,
                rows=0,
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="success",
            row_count=0,
            message=message,
            snapshot_evidence=snapshot_evidence,
            quality_evidence=quality_evidence,
        )

    def handle_pit_snapshot_missing(
        self,
        dataset: str,
        trade_date: str,
    ) -> IngestionResult:
        """Fail closed when a sparse dataset has no durable snapshot at D."""
        return self._handle_evidence_failure(
            dataset,
            trade_date,
            error="PIT_SNAPSHOT_MISSING",
            message="稀疏数据缺少可验证的 PIT 快照",
        )

    def handle_catalog_evidence_failed(
        self,
        dataset: str,
        trade_date: str,
    ) -> IngestionResult:
        """Fail closed when required sparse catalog evidence cannot be persisted."""
        return self._handle_evidence_failure(
            dataset,
            trade_date,
            error="CATALOG_EVIDENCE_FAILED",
            message="稀疏数据 catalog 证据持久化失败",
        )

    def handle_pit_cutoff_failure(
        self,
        dataset: str,
        trade_date: str,
        *,
        error: SparsePITCutoffError,
    ) -> IngestionResult:
        """Fail closed when a sparse delta contains future/invalid PIT facts."""
        messages = {
            "PIT_CUTOFF_DATE_INVALID": "PIT 截止日期无效",
            "PIT_KNOWLEDGE_DATE_MISSING": "稀疏数据缺少 knowledge_date",
            "PIT_KNOWLEDGE_DATE_INVALID": "稀疏数据包含无效 knowledge_date",
            "PIT_KNOWLEDGE_DATE_AFTER_CUTOFF": "稀疏数据包含截止日后才可知的事实",
        }
        return self._handle_evidence_failure(
            dataset,
            trade_date,
            error=error,
            message=messages[error],
        )

    def handle_quality_check_required(
        self,
        dataset: str,
        trade_date: str,
    ) -> IngestionResult:
        """Fail before writing an evidence-critical delta without L1/L2 checks."""
        return self._handle_evidence_failure(
            dataset,
            trade_date,
            error="INGESTION_QUALITY_CHECK_REQUIRED",
            message="稀疏数据写入前必须通过 L1/L2 质量检查",
        )

    def _handle_evidence_failure(
        self,
        dataset: str,
        trade_date: str,
        *,
        error: str,
        message: str,
    ) -> IngestionResult:
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code=error,
                error_message=message,
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error=error,
            message=message,
        )

    def handle_write_error(
        self, dataset: str, trade_date: str, error: Exception
    ) -> IngestionResult:
        """
        处理写入错误。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            error: 异常对象

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="WRITE_ERROR",
                error_message=str(error),
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="WRITE_ERROR",
            message=f"写入数据失败: {error}",
        )

    def handle_dq_blocked(
        self, dataset: str, trade_date: str, write_result: WriteResult
    ) -> IngestionResult:
        """
        处理 DQ 阻断。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            write_result: 写入结果

        Returns:
            IngestionResult: 失败结果

        """
        # DQ 检查已移到 App 层，这里使用默认错误计数
        error_count = 1
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="DQ_BLOCKED",
                error_message=f"DQ L1 check failed: {error_count} errors",
            )
        )

        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="DQ_BLOCKED",
            message=(
                "DQ L1 check failed, data rejected (will retry via reprocess task)"
            ),
        )

    def handle_success(
        self,
        dataset: str,
        trade_date: str,
        df: pl.DataFrame,
        write_result: WriteResult,
        *,
        snapshot_evidence: IngestionSnapshotEvidence | None = None,
        quality_evidence: IngestionQualityEvidence | None = None,
    ) -> IngestionResult:
        """
        处理成功写入。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            df: 数据框
            write_result: 写入结果
            snapshot_evidence: 可选累计 PIT 快照证据
            quality_evidence: 可选写入时 L1/L2 质量门禁证据

        Returns:
            IngestionResult: 成功结果

        """
        _ = df
        persisted_rows = write_result.rows_written
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.SUCCESS,
                # 修复：统一使用 write_result.checksum（落盘后包含所有字段的 checksum）
                checksum=write_result.checksum,
                rows=persisted_rows,
            )
        )

        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="success",
            row_count=persisted_rows,
            # 修复：统一使用 write_result.checksum（落盘后包含所有字段的 checksum）
            checksum=(None if snapshot_evidence is not None else write_result.checksum),
            message="数据摄取成功",
            snapshot_evidence=snapshot_evidence,
            quality_evidence=quality_evidence,
        )
