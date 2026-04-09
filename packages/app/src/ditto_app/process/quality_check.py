"""质量服务 — 写入时 DQ 检查."""

from __future__ import annotations

__all__ = [
    "QualityService",
]

from typing import Any

import polars as pl
import polars.exceptions as pl_exceptions
from ditto_infra.foundation import logger
from ditto_kernel.quality import DQIssue, DQResult

from ditto_app.process.quality_protocols import (
    QualityEngineProtocol,
    QuarantineWriterProtocol,
)

# ---------------------------------------------------------------------------
# 写入时 DQ 检查
# ---------------------------------------------------------------------------


class QualityService:
    """
    写入时数据质量检查服务.

    应用层：在数据摄取过程中编排 L1/L2 检查。
    处理隔离逻辑和指标/日志记录。
    """

    def __init__(
        self,
        engine: QualityEngineProtocol,
        quarantine_writer: QuarantineWriterProtocol | None = None,
    ) -> None:
        """
        初始化质量检查服务.

        Args:
            engine: 质量引擎实例
            quarantine_writer: 可选的隔离写入器，用于存储失败数据

        """
        self._engine = engine
        self._quarantine_writer = quarantine_writer

    def check_and_quarantine(
        self,
        df: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[pl.DataFrame, bool]:
        """
        执行 DQ 检查，必要时隔离不良数据.

        Args:
            df: 待检查的数据
            dataset: 数据集标识
            context: 附加上下文（如外键检查的 reference_values）

        Returns:
            元组 (df, should_block):
                - df: 原始 DataFrame（不变；
                  隔离机制会将不良行复制到独立存储）
                - should_block: 是否阻止摄取（发现 L1 错误时为 True）

        """
        result = self._engine.check(
            df=df,
            dataset=dataset,
            levels=["l1", "l2"],
            context=context,
        )

        self._log_check_result(result, dataset)

        if result.issues:
            self._quarantine_data(df, result, dataset)

        return df, result.has_errors

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
        """
        隔离存在质量问题的数据.

        如果配置了隔离存储，则将失败数据保存到隔离区。

        Args:
            _df: 存在问题的数据
            result: DQ 检查结果
            dataset: 数据集标识

        """
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
            raise RuntimeError("quarantine_writer 未初始化, 需先调用 _quarantine_data")
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
