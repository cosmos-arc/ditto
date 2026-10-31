"""#623 瞬态失败→分类→自动重试恢复 集成证明.

注入限流错误（10-28/10-29 夜间事故同型），断言：
1. 失败落库为 RATE_LIMIT（细分码），分类 transient，进入补偿发现；
2. 永久失败（UNKNOWN_ERROR）保留原因、排除出自动重试；
3. RetryManager 重试恢复后 FAIL 日志被 SUCCESS 覆盖（attempts 累加）；
4. 同输入再次摄取幂等（已成功日期 skipped，不重复写入）。
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_application.processes.ingestion.retry_manager import RetryManager
from ditto_data.errors import SourceRateLimitError
from ditto_data.models.ingestion import (
    IngestionFailureKind,
    IngestionStatus,
    classify_ingestion_failure,
)
from packages.application.tests.integration.test_ingestion_evidence_recovery import (
    _coordinator,
    _MarketSource,
    _pipeline,
)


class _RateLimitedOnceSource(_MarketSource):
    """首个请求限流，之后恢复的真实源替身（10-28 夜间同型故障）。"""

    def __init__(self) -> None:
        super().__init__()
        self.rate_limited_once = False

    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        if not self.rate_limited_once:
            self.rate_limited_once = True
            raise SourceRateLimitError(
                message="Tushare API 限流 (API: daily)",
                source="tushare",
            )
        return self.payload.filter(
            pl.col("trade_date") == date.fromisoformat(trade_date)
        )


@pytest.mark.integration
def test_transient_rate_limit_recovers_via_classified_retry(
    tmp_path,
) -> None:
    with _pipeline(tmp_path, "stock_daily") as runtime:
        source = _RateLimitedOnceSource()
        coordinator, _ = _coordinator(runtime, source)
        logs = runtime.ports.ingestion_log_store

        # 1. 注入瞬态错误：失败落库为细分码 RATE_LIMIT，分类 transient。
        first = coordinator.ingest_date("stock_daily", "2026-07-16")
        assert first.status == "failed"
        assert first.error == "RATE_LIMIT"
        failed_log = logs.get_log("stock_daily", "tushare", "2026-07-16")
        assert failed_log is not None
        assert failed_log.status is IngestionStatus.FAIL
        assert failed_log.error_code == "RATE_LIMIT"
        assert (
            classify_ingestion_failure(failed_log.error_code)
            is IngestionFailureKind.TRANSIENT
        )
        assert failed_log.attempts == 1

        # 永久失败兄弟样本：同库 UNKNOWN_ERROR 保留原因、分类 permanent。
        runtime.context.result_handler.handle_unknown_error(
            "global_index_daily",
            "2026-10-27",
            ValueError('ColumnNotFoundError: "source_ticker"'),
        )

        # 2. 补偿发现只选中瞬态失败数据集。
        manager = RetryManager(coordinator=coordinator, ingestion_log_store=logs)
        retryable, excluded_groups = manager.compensation_selection()
        assert retryable == ["stock_daily"]
        assert [item["dataset"] for item in excluded_groups] == ["global_index_daily"]
        assert excluded_groups[0]["kind"] == "permanent"

        # 3. 重试恢复：限流窗口过后同输入重试成功，FAIL 被 SUCCESS 覆盖。
        retry = manager.retry_failed("stock_daily")
        assert retry.retried_count == 1
        assert retry.success_count == 1
        assert retry.still_failed_count == 0
        recovered = logs.get_log("stock_daily", "tushare", "2026-07-16")
        assert recovered is not None
        assert recovered.status is IngestionStatus.SUCCESS
        assert recovered.attempts == 2

        # 永久失败不被自动重试：日期不进重试列表，原因保留在库。
        permanent = logs.get_log("global_index_daily", "tushare", "2026-10-27")
        assert permanent is not None
        assert permanent.error_code == "UNKNOWN_ERROR"
        assert "ColumnNotFoundError" in (permanent.error_message or "")
        assert manager.get_failed_dates("global_index_daily") == []

        # 4. 同输入重试幂等：已成功日期再摄取为 skipped，不产生新写入。
        replay = coordinator.ingest_date("stock_daily", "2026-07-16")
        assert replay.status == "skipped"
        final = logs.get_log("stock_daily", "tushare", "2026-07-16")
        assert final is not None
        assert final.status is IngestionStatus.SUCCESS
        assert final.attempts == 2
