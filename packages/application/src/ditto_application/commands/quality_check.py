"""数据质量检查 Command — 写入时 DQ 校验的原子写操作."""

from __future__ import annotations

import polars as pl
import polars.exceptions as pl_exceptions
from ditto_data.ingestion.quality_record_service import QualityRecordService
from ditto_data.quality import QualityEngine
from ditto_data.quality.quality_types import DQIssue, DQResult
from ditto_platform.foundation import logger

from ditto_application.contracts import CheckDataQualityCommand
from ditto_application.exceptions import AppCommandError

__all__ = [
    "CheckDataQualityHandler",
]


class CheckDataQualityHandler:
    """
    数据质量检查 Command Handler — L1/L2 检查 + 隔离写入.

    直接依赖 ditto_data 层服务（QualityEngine + QualityRecordService），
    编排 check -> quarantine 写入的完整流程。
    """

    def __init__(
        self,
        engine: QualityEngine,
        quarantine_writer: QualityRecordService | None = None,
    ) -> None:
        self._engine = engine
        self._quarantine_writer = quarantine_writer

    def handle(self, cmd: CheckDataQualityCommand) -> tuple[pl.DataFrame, bool]:
        """执行 L1/L2 质量检查，必要时隔离不良数据."""
        try:
            result = self._engine.check(
                df=cmd.df,
                dataset=cmd.dataset,
                levels=["l1", "l2"],
                context=cmd.context,
            )
        except ValueError as exc:
            raise AppCommandError(
                str(exc),
                command="check_data_quality",
                dataset=cmd.dataset,
            ) from exc

        self._log_check_result(result, cmd.dataset)

        if result.issues:
            self._quarantine_data(cmd.df, result, cmd.dataset)

        return cmd.df, result.has_errors

    # -- Private helpers (absorbed from QualityService) --

    def _log_check_result(self, result: DQResult, dataset: str) -> None:
        """记录 DQ 检查结果."""
        if result.issues:
            logger.warning(
                "DQ issues found during write",
                event="dq_write_check",
                dataset=dataset,
                issue_count=len(result.issues),
                error_count=result.error_count,
                warn_count=result.warn_count,
            )
        else:
            logger.debug(
                "DQ check passed",
                event="dq_write_check",
                dataset=dataset,
            )

    def _quarantine_data(
        self,
        _df: pl.DataFrame,
        result: DQResult,
        dataset: str,
    ) -> None:
        """隔离存在质量问题的数据."""
        if self._quarantine_writer is None:
            logger.info(
                "Quarantine store not configured, skipping quarantine",
                event="dq_quarantine_skipped",
                dataset=dataset,
                issue_count=len(result.issues),
            )
            return

        for issue in result.issues:
            if issue.affected_rows == 0 or not issue.sample_data:
                continue
            self._save_quarantine_issue(dataset, issue)

    def _save_quarantine_issue(self, dataset: str, issue: DQIssue) -> None:
        """保存单个 issue 的隔离数据."""
        if self._quarantine_writer is None:
            raise AppCommandError("quarantine_writer 未初始化")
        try:
            failed_df = pl.DataFrame(issue.sample_data)
            self._quarantine_writer.save_failed_data(
                dataset=dataset,
                rule_id=issue.rule_name,
                severity=issue.severity.value,
                failed_data=failed_df,
                trade_date=None,
            )
            logger.info(
                "Quarantined bad data",
                event="dq_quarantine",
                dataset=dataset,
                rule_id=issue.rule_name,
                severity=issue.severity.value,
                affected_rows=issue.affected_rows,
            )
        except (pl_exceptions.ComputeError, pl_exceptions.SchemaError, TypeError) as e:
            logger.error(
                "Failed to quarantine data",
                event="dq_quarantine_failed",
                dataset=dataset,
                rule_id=issue.rule_name,
                error=str(e),
            )
        except Exception:
            logger.exception(
                "Unexpected error during quarantine",
                event="dq_quarantine_unexpected_error",
                dataset=dataset,
                rule_id=issue.rule_name,
            )
