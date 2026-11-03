"""
Ingestion log reader for tracking per-trade-date ingestion events.

Provides read-only access to ingestion log data.
"""

from typing import Any, Literal

from ditto_platform.foundation import SQLiteClient

from ditto_data.models.ingestion import (
    TRANSIENT_ERROR_CODES,
    IngestionFailedErrorGroup,
    IngestionLog,
    IngestionStatus,
    UnresolvedFailureGroup,
)

# 失败过滤口径："all"=全部（遗留语义）；"transient"=仅瞬态（自动重试
# 资格）；"non_transient"=瞬态之外（永久/源缺失/不支持/未知码——
# fail-closed 与分类一致：未知码按永久处理）。
FailureFilter = Literal["all", "transient", "non_transient"]


class IngestionLogReader:
    """
    Reader for ingestion event logs.

    Provides read-only access to ingestion logs that track ingestion events
    per trade date with SUCCESS/FAIL status.

    Table: ingestion_log
    - dataset, source, trade_date: PRIMARY KEY
    - status: 'SUCCESS' or 'FAIL'
    - checksum, rows: populated when SUCCESS
    - error_code, error_message: populated when FAIL
    - attempts: incremented on retry
    - first_attempt_at, last_attempt_at: timestamps
    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize reader.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

    def _row_to_log(self, row: dict[str, Any]) -> IngestionLog:
        """Convert database row to IngestionLog object."""
        return IngestionLog(
            dataset=row["dataset"],
            source=row["source"],
            trade_date=row["trade_date"],
            status=IngestionStatus(row["status"]),
            checksum=row["checksum"],
            rows=row["rows"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            attempts=row["attempts"],
            first_attempt_at=row["first_attempt_at"],
            last_attempt_at=row["last_attempt_at"],
        )

    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None:
        """
        Get ingestion log for a specific date.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (e.g., "tushare")
            trade_date: Trade date (YYYY-MM-DD)

        Returns:
            IngestionLog if found, None otherwise.

        """
        sql = """
            SELECT dataset, source, trade_date, status,
                   checksum, rows, error_code, error_message,
                   attempts, first_attempt_at, last_attempt_at
            FROM ingestion_log
            WHERE dataset = ? AND source = ? AND trade_date = ?
        """

        row = self._client.fetchone(sql, [dataset, source, trade_date])

        if not row:
            return None

        return self._row_to_log(row)

    def list_failed_dates(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
    ) -> list[str]:
        """
        Get failed trade dates that need retry.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")
            limit: Maximum number of dates to return
            max_attempts: Only return dates with attempts < max_attempts

        Returns:
            List of trade dates (YYYY-MM-DD) that need retry.

        """
        sql = """
            SELECT trade_date
            FROM ingestion_log
            WHERE dataset = ? AND source = ? AND status = 'FAIL'
              AND attempts < ?
            ORDER BY trade_date ASC
            LIMIT ?
        """

        rows = self._client.fetchall(sql, [dataset, source, max_attempts, limit])
        return [row["trade_date"] for row in rows]

    def count_success_rate(
        self,
        dataset: str,
        source: str = "tushare",
        start_date: str | None = None,
    ) -> float:
        """
        Calculate success rate for a dataset.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")
            start_date: Optional start date filter (YYYY-MM-DD)

        Returns:
            Success rate as a float (0.0 to 1.0).

        """
        if start_date:
            sql = """
                SELECT
                    COUNT(CASE WHEN status = 'SUCCESS'
                        THEN 1 END) * 1.0 / COUNT(*) as rate
                FROM ingestion_log
                WHERE dataset = ? AND source = ? AND trade_date >= ?
            """
            row = self._client.fetchone(sql, [dataset, source, start_date])
        else:
            sql = """
                SELECT
                    COUNT(CASE WHEN status = 'SUCCESS'
                        THEN 1 END) * 1.0 / COUNT(*) as rate
                FROM ingestion_log
                WHERE dataset = ? AND source = ?
            """
            row = self._client.fetchone(sql, [dataset, source])

        return float(row["rate"]) if row and row["rate"] is not None else 0.0

    def get_stats(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> dict[str, int]:
        """
        Get ingestion statistics for a dataset.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")

        Returns:
            Dictionary with statistics: success_count, fail_count, total_count

        """
        sql = """
            SELECT
                COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as success_count,
                COUNT(CASE WHEN status = 'FAIL' THEN 1 END) as fail_count,
                COUNT(*) as total_count
            FROM ingestion_log
            WHERE dataset = ? AND source = ?
        """

        row = self._client.fetchone(sql, [dataset, source])

        return {
            "success_count": row["success_count"] if row else 0,
            "fail_count": row["fail_count"] if row else 0,
            "total_count": row["total_count"] if row else 0,
        }

    def list_ingested_dates(
        self,
        dataset: str,
        source: str = "tushare",
        status: IngestionStatus | None = None,
    ) -> list[str]:
        """
        Get all ingested trade dates for a dataset.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")
            status: Optional status filter (SUCCESS or FAIL). If None,
                returns all dates.

        Returns:
            List of trade dates (YYYY-MM-DD) that have been ingested.

        """
        if status:
            sql = """
                SELECT trade_date
                FROM ingestion_log
                WHERE dataset = ? AND source = ? AND status = ?
                ORDER BY trade_date ASC
            """
            rows = self._client.fetchall(sql, [dataset, source, status.value])
        else:
            sql = """
                SELECT trade_date
                FROM ingestion_log
                WHERE dataset = ? AND source = ?
                ORDER BY trade_date ASC
            """
            rows = self._client.fetchall(sql, [dataset, source])

        return [row["trade_date"] for row in rows]

    def list_failed_logs(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
        failure_filter: FailureFilter = "all",
    ) -> list[IngestionLog]:
        """
        Get failed ingestion logs that need retry.

        过滤在 SQL 内完成（correctness #623 F1）：瞬态过滤若在 Python
        侧做，永久失败行（attempts 冻结）会占满 LIMIT 窗口饿死更新的
        瞬态失败。

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default "tushare")
            limit: Maximum number of logs to return
            max_attempts: Only return logs with attempts < max_attempts
            failure_filter: "all"（不过滤）/"transient"（仅瞬态错误码）/
                "non_transient"（瞬态之外，含 NULL 与未知码）

        Returns:
            List of IngestionLog that need retry.

        """
        sql = """
            SELECT dataset, source, trade_date, status,
                   checksum, rows, error_code, error_message,
                   attempts, first_attempt_at, last_attempt_at
            FROM ingestion_log
            WHERE dataset = ? AND source = ? AND status = 'FAIL'
              AND attempts < ?
        """
        params: list[object] = [dataset, source, max_attempts]
        if failure_filter == "transient":
            placeholders = ", ".join("?" for _ in TRANSIENT_ERROR_CODES)
            sql += f" AND error_code IN ({placeholders})"
            params.extend(sorted(TRANSIENT_ERROR_CODES))
        elif failure_filter == "non_transient":
            placeholders = ", ".join("?" for _ in TRANSIENT_ERROR_CODES)
            sql += f" AND (error_code IS NULL OR error_code NOT IN ({placeholders}))"
            params.extend(sorted(TRANSIENT_ERROR_CODES))
        sql += """
            ORDER BY trade_date ASC
            LIMIT ?
        """
        params.append(limit)

        rows = self._client.fetchall(sql, params)

        return [self._row_to_log(row) for row in rows]

    def count_retryable_failures(
        self,
        dataset: str,
        source: str = "tushare",
        max_attempts: int = 3,
    ) -> int:
        """
        瞬态且未耗尽的失败行数（#658 批次1B 精确 pending_beyond_limit）.

        与 list_failed_logs 的 transient 过滤同口径（SQL 内过滤），供
        重试报告计算超出本轮 limit 的真实积压数——limit+1 探测只能给出
        0/1 截断信号，会低估积压。

        Args:
            dataset: 数据集名称
            source: 数据源标识（默认 "tushare"）
            max_attempts: 仅统计尝试次数小于此值的失败

        Returns:
            符合自动重试资格的失败行数。

        """
        transient = sorted(TRANSIENT_ERROR_CODES)
        placeholders = ", ".join("?" for _ in transient)
        sql = "SELECT COUNT(*) as retryable FROM ingestion_log "
        sql += "WHERE dataset = ? AND source = ? AND status = 'FAIL' "
        sql += f"AND attempts < ? AND error_code IN ({placeholders})"
        row = self._client.fetchall(sql, [dataset, source, max_attempts, *transient])
        return int(row[0]["retryable"]) if row else 0

    def list_failed_error_groups(
        self,
        source: str = "tushare",
        max_attempts: int = 3,
    ) -> list[IngestionFailedErrorGroup]:
        """
        按 (dataset, error_code) 分组统计待处理失败（#623 补偿发现）。

        只返回 status=FAIL 且 attempts < max_attempts 的行——与
        list_failed_logs 的重试资格口径一致；调用方按失败分类决定哪些
        数据集进入自动补偿。

        Args:
            source: 数据源标识（默认 "tushare"）
            max_attempts: 仅统计尝试次数小于此值的失败

        Returns:
            分组统计列表（dataset 升序，组内按 error_code 升序）。

        """
        sql = """
            SELECT dataset, error_code, COUNT(*) as failure_count,
                   MIN(trade_date) as oldest_trade_date,
                   MAX(trade_date) as newest_trade_date
            FROM ingestion_log
            WHERE source = ? AND status = 'FAIL' AND attempts < ?
            GROUP BY dataset, error_code
            ORDER BY dataset ASC, error_code ASC
        """
        rows = self._client.fetchall(sql, [source, max_attempts])
        return [
            IngestionFailedErrorGroup(
                dataset=row["dataset"],
                error_code=row["error_code"],
                failure_count=row["failure_count"],
                oldest_trade_date=row["oldest_trade_date"],
                newest_trade_date=row["newest_trade_date"],
            )
            for row in rows
        ]

    def list_unresolved_failures(
        self,
        source: str = "tushare",
        limit: int = 1000,
    ) -> list[IngestionLog]:
        """
        全部未解决失败行（status=FAIL，不做尝试次数/瞬态过滤）.

        #658 批次1B 终态判定输入：以账本当前行为准——后续成功按主键
        upsert 翻转本行为 SUCCESS 即视为已解决；attempts 达上限（耗尽）
        的行不出现在 list_failed_logs/list_failed_error_groups，但仍是
        未解决事实，在此持续可见。

        Args:
            source: 数据源标识（默认 "tushare"）
            limit: 返回的最大行数（防全量倾倒；配合汇总查询使用）

        Returns:
            未解决失败行（trade_date 升序）。

        """
        sql = """
            SELECT dataset, source, trade_date, status,
                   checksum, rows, error_code, error_message,
                   attempts, first_attempt_at, last_attempt_at
            FROM ingestion_log
            WHERE source = ? AND status = 'FAIL'
            ORDER BY trade_date ASC, dataset ASC
            LIMIT ?
        """
        rows = self._client.fetchall(sql, [source, limit])
        return [self._row_to_log(row) for row in rows]

    def list_unresolved_failure_groups(
        self,
        source: str = "tushare",
        max_attempts: int = 3,
    ) -> list[UnresolvedFailureGroup]:
        """
        按数据集分桶统计最终未解决失败（#658 批次1B）.

        桶口径（互斥）：exhausted=attempts≥max_attempts（重试耗尽）；
        pending_transient=未耗尽且瞬态错误码（可继续自动重试）；
        pending_non_transient=未耗尽且非瞬态（人工/覆盖缺口裁决）。

        Args:
            source: 数据源标识（默认 "tushare"）
            max_attempts: 耗尽阈值

        Returns:
            分桶统计列表（dataset 升序；total=0 的数据集不出现）。

        """
        transient = sorted(TRANSIENT_ERROR_CODES)
        transient_placeholders = ", ".join("?" for _ in transient)
        sql = """
            SELECT dataset, COUNT(*) as total,
                   SUM(CASE WHEN attempts >= ? THEN 1 ELSE 0 END) as exhausted,
        """
        sql += f"""
                   SUM(CASE WHEN attempts < ? AND error_code IN
                        ({transient_placeholders}) THEN 1 ELSE 0 END)
                        as pending_transient,
        """
        sql += f"""
                   SUM(CASE WHEN attempts < ? AND (error_code IS NULL OR
                        error_code NOT IN ({transient_placeholders}))
                        THEN 1 ELSE 0 END) as pending_non_transient,
        """
        sql += """
                   MIN(trade_date) as oldest_trade_date,
                   MAX(trade_date) as newest_trade_date
            FROM ingestion_log
            WHERE source = ? AND status = 'FAIL'
            GROUP BY dataset
            ORDER BY dataset ASC
        """
        params: list[object] = [
            max_attempts,
            max_attempts,
            *transient,
            max_attempts,
            *transient,
            source,
        ]
        rows = self._client.fetchall(sql, params)
        return [
            UnresolvedFailureGroup(
                dataset=row["dataset"],
                total=row["total"],
                exhausted=row["exhausted"],
                pending_transient=row["pending_transient"],
                pending_non_transient=row["pending_non_transient"],
                oldest_trade_date=row["oldest_trade_date"],
                newest_trade_date=row["newest_trade_date"],
            )
            for row in rows
        ]

    def get_last_success_date(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> str | None:
        """获取最后成功的交易日期。"""
        sql = """
            SELECT MAX(trade_date) as last_success
            FROM ingestion_log
            WHERE dataset = ? AND source = ? AND status = 'SUCCESS'
        """
        row = self._client.fetchone(sql, [dataset, source])
        return row["last_success"] if row else None
