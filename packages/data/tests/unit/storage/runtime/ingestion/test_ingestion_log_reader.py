"""IngestionLogReader 单元测试（#623 补偿发现查询）."""

from __future__ import annotations

from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_data.storage.runtime.ingestion.ingestion_log_reader import (
    IngestionLogReader,
)
from ditto_data.storage.runtime.ingestion.ingestion_log_writer import (
    IngestionLogWriter,
)


def _write_log(
    sqlite_client,
    dataset: str,
    trade_date: str,
    *,
    error_code: str | None = "FETCH_ERROR",
    attempts: int = 1,
) -> None:
    """写一条失败日志（Writer 构造时建表；attempts 由重复 upsert 累加）."""
    writer = IngestionLogWriter(sqlite_client)
    log = IngestionLog(
        dataset=dataset,
        source="tushare",
        trade_date=trade_date,
        status=IngestionStatus.FAIL,
        error_code=error_code,
        error_message=f"stub {error_code}",
    )
    for _ in range(attempts):
        writer.save_log(log)


class TestListFailedErrorGroups:
    """按 (dataset, error_code) 分组的失败统计——补偿发现的数据源。"""

    def test_groups_by_dataset_and_error_code(self, sqlite_client) -> None:
        """同数据集不同错误码分组统计，含最老/最新日期与最大尝试数。"""
        _write_log(sqlite_client, "etf_nav", "2026-10-27", error_code="RATE_LIMIT")
        _write_log(sqlite_client, "etf_nav", "2026-10-28", error_code="RATE_LIMIT")
        _write_log(sqlite_client, "etf_nav", "2026-10-29", error_code="NETWORK_ERROR")

        groups = IngestionLogReader(sqlite_client).list_failed_error_groups(
            source="tushare",
            max_attempts=3,
        )

        assert [(g.dataset, g.error_code, g.failure_count) for g in groups] == [
            ("etf_nav", "NETWORK_ERROR", 1),
            ("etf_nav", "RATE_LIMIT", 2),
        ]
        rate_limit = groups[1]
        assert rate_limit.oldest_trade_date == "2026-10-27"
        assert rate_limit.newest_trade_date == "2026-10-28"

    def test_exhausted_attempts_excluded(self, sqlite_client) -> None:
        """尝试次数耗尽（attempts >= max_attempts）的失败不进补偿发现。"""
        _write_log(
            sqlite_client, "etf_nav", "2026-10-28", error_code="RATE_LIMIT", attempts=3
        )

        groups = IngestionLogReader(sqlite_client).list_failed_error_groups(
            source="tushare",
            max_attempts=3,
        )

        assert groups == []

    def test_success_rows_not_grouped(self, sqlite_client) -> None:
        """成功日志不进失败分组。"""
        writer = IngestionLogWriter(sqlite_client)
        writer.save_log(
            IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date="2026-10-29",
                status=IngestionStatus.SUCCESS,
                rows=5571,
            )
        )

        groups = IngestionLogReader(sqlite_client).list_failed_error_groups()

        assert groups == []

    def test_other_sources_isolated(self, sqlite_client) -> None:
        """按 source 过滤——其他源的失败不混入。"""
        writer = IngestionLogWriter(sqlite_client)
        writer.save_log(
            IngestionLog(
                dataset="etf_nav",
                source="fuyao",
                trade_date="2026-10-29",
                status=IngestionStatus.FAIL,
                error_code="RATE_LIMIT",
            )
        )

        groups = IngestionLogReader(sqlite_client).list_failed_error_groups(
            source="tushare",
        )

        assert groups == []


class TestListFailedLogsFailureFilter:
    """SQL 内失败分类过滤（correctness #623 F1：瞬态不得被永久饿死）。"""

    @staticmethod
    def _seed_window(sqlite_client) -> None:
        """10 条更早的永久失败 + 1 条更新的瞬态失败。"""
        for day in range(1, 11):
            _write_log(
                sqlite_client,
                "stock_daily",
                f"2024-12-{day:02d}",
                error_code="DQ_BLOCKED",
            )
        _write_log(
            sqlite_client,
            "stock_daily",
            "2024-12-11",
            error_code="RATE_LIMIT",
        )

    def test_transient_filter_not_starved_by_permanent_window(
        self, sqlite_client
    ) -> None:
        """永久失败（attempts 冻结）占满 LIMIT 窗口时瞬态仍可见。

        若过滤在 Python 侧做，LIMIT=10 会先截出 10 条永久行，瞬态行
        既不重试也不留痕——永久饿死。
        """
        self._seed_window(sqlite_client)

        logs = IngestionLogReader(sqlite_client).list_failed_logs(
            dataset="stock_daily",
            limit=10,
            failure_filter="transient",
        )

        assert [log.trade_date for log in logs] == ["2024-12-11"]
        assert logs[0].error_code == "RATE_LIMIT"

    def test_non_transient_filter_returns_permanent_partition(
        self, sqlite_client
    ) -> None:
        """非瞬态分区=瞬态码之外（含 NULL 与未知码，fail-closed 同口径）。"""
        self._seed_window(sqlite_client)
        _write_log(sqlite_client, "stock_daily", "2024-12-12", error_code=None)
        _write_log(
            sqlite_client, "stock_daily", "2024-12-13", error_code="SOME_NEW_CODE"
        )

        logs = IngestionLogReader(sqlite_client).list_failed_logs(
            dataset="stock_daily",
            limit=15,
            failure_filter="non_transient",
        )

        assert [log.trade_date for log in logs] == [
            f"2024-12-{day:02d}" for day in range(1, 11)
        ] + ["2024-12-12", "2024-12-13"]

    def test_all_filter_keeps_legacy_semantics(self, sqlite_client) -> None:
        """默认不过滤：LIMIT 按日期取最旧 10 条（既有语义不变）。"""
        self._seed_window(sqlite_client)

        logs = IngestionLogReader(sqlite_client).list_failed_logs(
            dataset="stock_daily",
            limit=10,
        )

        assert [log.trade_date for log in logs] == [
            f"2024-12-{day:02d}" for day in range(1, 11)
        ]
