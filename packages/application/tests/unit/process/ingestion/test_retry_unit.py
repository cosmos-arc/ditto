"""Tests for RetryManager."""

import pytest
from ditto_application.processes.ingestion.retry_manager import RetryManager
from ditto_data.models.ingestion import (
    IngestionFailedErrorGroup,
    IngestionLog,
    IngestionResult,
    IngestionStatus,
    RetryResult,
)
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    init,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=True,
        verbose_logging=False,
        tracing_enabled=True,
        tracing_sample_rate=1.0,
        metrics_enabled=True,
    )
    init(config, force=True)
    yield
    reset_for_testing()


def _failed_log(
    day: str,
    *,
    dataset: str = "stock_daily",
    error_code: str | None = "FETCH_ERROR",
    attempts: int = 1,
) -> IngestionLog:
    """构造一条失败日志（默认瞬态 FETCH_ERROR）。"""
    return IngestionLog(
        dataset=dataset,
        source="tushare",
        trade_date=day,
        status=IngestionStatus.FAIL,
        error_code=error_code,
        attempts=attempts,
    )


def _error_group(
    dataset: str,
    error_code: str | None,
    *,
    count: int = 1,
) -> IngestionFailedErrorGroup:
    return IngestionFailedErrorGroup(
        dataset=dataset,
        error_code=error_code,
        failure_count=count,
        oldest_trade_date="2024-12-25",
        newest_trade_date="2024-12-26",
    )


@pytest.fixture
def mock_coordinator(mocker):
    """创建 Mock IngestionCoordinator。"""
    coordinator = mocker.Mock()
    coordinator.ingest_date = mocker.Mock()
    return coordinator


@pytest.fixture
def mock_ingestion_log_store(mocker):
    """创建 Mock IngestionLogStore。"""
    service = mocker.Mock()
    service.list_failed_logs = mocker.Mock(return_value=[])
    service.list_failed_error_groups = mocker.Mock(return_value=[])
    return service


def _wire_failed_logs(mock_ingestion_log_store, logs: list[IngestionLog]) -> None:
    """按 failure_filter 语义分派的日志桩（与 SQL 过滤口径一致）。"""
    from ditto_data.models.ingestion import is_retryable_ingestion_failure

    def _list(*, failure_filter="all", **kwargs):
        if failure_filter == "transient":
            return [
                log for log in logs if is_retryable_ingestion_failure(log.error_code)
            ]
        if failure_filter == "non_transient":
            return [
                log
                for log in logs
                if not is_retryable_ingestion_failure(log.error_code)
            ]
        return logs

    mock_ingestion_log_store.list_failed_logs.side_effect = _list


@pytest.fixture
def retry_manager(mock_coordinator, mock_ingestion_log_store):
    """创建 RetryManager 实例。"""
    return RetryManager(
        coordinator=mock_coordinator,
        ingestion_log_store=mock_ingestion_log_store,
        source="tushare",
    )


@pytest.mark.unit
class TestRetryResult:
    """测试 RetryResult 类。"""

    def test_create_retry_result(self) -> None:
        """创建重试结果。"""
        results = (
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="failed",
                error="FETCH_ERROR",
                message="获取数据失败",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="success",
                row_count=1000,
            ),
        )

        result = RetryResult(
            dataset="stock_daily",
            total_failed=3,
            retried_count=3,
            success_count=2,
            still_failed_count=1,
            results=results,
        )

        assert result.dataset == "stock_daily"
        assert result.total_failed == 3
        assert result.retried_count == 3
        assert result.success_count == 2
        assert result.still_failed_count == 1
        assert len(result.results) == 3
        assert result.excluded_failures == ()


@pytest.mark.unit
class TestGetFailedDates:
    """测试 get_failed_dates 方法（#623：仅瞬态失败进入自动重试）。"""

    def test_get_failed_dates_returns_transient_failures(
        self, retry_manager, mock_ingestion_log_store
    ) -> None:
        """瞬态失败（限流/网络/一般取数错误）返回待重试日期。"""
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25", error_code="RATE_LIMIT"),
                _failed_log("2024-12-26", error_code="NETWORK_ERROR"),
                _failed_log("2024-12-27", error_code="FETCH_ERROR"),
            ],
        )

        dates = retry_manager.get_failed_dates(
            dataset="stock_daily",
            max_attempts=3,
        )

        assert dates == ["2024-12-25", "2024-12-26", "2024-12-27"]
        mock_ingestion_log_store.list_failed_logs.assert_called_once_with(
            dataset="stock_daily",
            source="tushare",
            limit=10,
            max_attempts=3,
            failure_filter="transient",
        )

    def test_get_failed_dates_excludes_non_transient_failures(
        self, retry_manager, mock_ingestion_log_store
    ) -> None:
        """永久/源缺失/不支持分类的失败不进入自动重试（#623）。"""
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25", error_code="RATE_LIMIT"),
                _failed_log("2024-12-26", error_code="UNKNOWN_ERROR"),
                _failed_log("2024-12-27", error_code="EMPTY_DATA"),
                _failed_log("2024-12-28", error_code="SOURCE_UNSUPPORTED"),
            ],
        )

        dates = retry_manager.get_failed_dates(dataset="stock_daily")

        assert dates == ["2024-12-25"]

    def test_get_failed_dates_with_custom_limit(
        self, retry_manager, mock_ingestion_log_store
    ) -> None:
        """使用自定义限制获取失败日期。"""
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25"),
                _failed_log("2024-12-26"),
            ],
        )

        dates = retry_manager.get_failed_dates(
            dataset="stock_daily",
            max_attempts=3,
            limit=2,
        )

        assert dates == ["2024-12-25", "2024-12-26"]
        mock_ingestion_log_store.list_failed_logs.assert_called_once_with(
            dataset="stock_daily",
            source="tushare",
            limit=2,
            max_attempts=3,
            failure_filter="transient",
        )

    def test_get_failed_dates_empty(
        self, retry_manager, mock_ingestion_log_store
    ) -> None:
        """没有失败日期时返回空列表。"""
        _wire_failed_logs(mock_ingestion_log_store, [])

        dates = retry_manager.get_failed_dates(dataset="stock_daily")

        assert dates == []

    def test_get_failed_dates_prioritizes_fewer_attempts_then_older_failures(
        self,
        mock_coordinator,
        mock_ingestion_log_store,
    ) -> None:
        """#394:按 success log 的尝试簿记排序——尝试少、更早的失败优先。"""

        def _log(day: str, attempts: int, last: str | None) -> IngestionLog:
            return IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date=day,
                status=IngestionStatus.FAIL,
                error_code="FETCH_ERROR",
                attempts=attempts,
                last_attempt_at=last,
            )

        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _log("2024-12-25", 3, "2024-12-25T08:00:00+00:00"),
                _log("2024-12-26", 1, None),
                _log("2024-12-27", 1, "2024-12-27T09:00:00+00:00"),
            ],
        )
        mock_ingestion_log_store.get_log.side_effect = (
            lambda dataset, source, trade_date: {
                "2024-12-25": _log("2024-12-25", 3, "2024-12-25T08:00:00+00:00"),
                "2024-12-26": None,
                "2024-12-27": _log("2024-12-27", 1, "2024-12-27T09:00:00+00:00"),
            }.get(trade_date)
        )
        retry_manager = RetryManager(
            coordinator=mock_coordinator,
            ingestion_log_store=mock_ingestion_log_store,
            source="tushare",
        )

        dates = retry_manager.get_failed_dates(dataset="stock_daily")

        # 26 无簿记(从未落账)最优先;27 尝试少;25 尝试多垫底。
        assert dates == ["2024-12-26", "2024-12-27", "2024-12-25"]


@pytest.mark.unit
class TestCompensationSelection:
    """测试补偿发现（#623：按真实失败记录选择，仅瞬态进入自动补偿）。"""

    def test_compensation_selection_splits_transient_from_excluded(
        self, retry_manager, mock_ingestion_log_store
    ) -> None:
        """单次选择：瞬态失败数据集进重试（升序去重），非瞬态留痕。"""
        # 顺序模拟 reader 的 dataset ASC, error_code ASC 分组序。
        mock_ingestion_log_store.list_failed_error_groups.return_value = [
            _error_group("cash_flow", "RATE_LIMIT", count=3),
            _error_group("etf_nav", "EMPTY_DATA_UNEXPECTED", count=2),
            _error_group("etf_nav", "RATE_LIMIT"),
            _error_group("etf_reference", "SOURCE_UNSUPPORTED"),
            _error_group("hk_hold", "EMPTY_DATA", count=5),
            _error_group("stock_daily", "UNKNOWN_ERROR"),
        ]

        retryable, excluded = retry_manager.compensation_selection(
            max_attempts=3,
        )

        assert retryable == ["cash_flow", "etf_nav"]
        assert [item["dataset"] for item in excluded] == [
            "etf_reference",
            "hk_hold",
            "stock_daily",
        ]
        assert excluded[1]["error_code"] == "EMPTY_DATA"
        assert excluded[1]["kind"] == "source_missing"
        assert excluded[1]["failure_count"] == 5
        assert excluded[1]["oldest_trade_date"] == "2024-12-25"
        assert excluded[1]["newest_trade_date"] == "2024-12-26"
        mock_ingestion_log_store.list_failed_error_groups.assert_called_once_with(
            source="tushare", max_attempts=3
        )

    def test_compensation_selection_empty_when_no_transient(
        self, retry_manager, mock_ingestion_log_store
    ) -> None:
        """无瞬态失败时不发现任何重试数据集（非瞬态不自动补偿）。"""
        mock_ingestion_log_store.list_failed_error_groups.return_value = [
            _error_group("stock_daily", "UNKNOWN_ERROR"),
        ]

        retryable, excluded = retry_manager.compensation_selection()

        assert retryable == []
        assert len(excluded) == 1

    def test_excluded_failure_groups_keep_typed_records(
        self, retry_manager, mock_ingestion_log_store
    ) -> None:
        """非瞬态失败分组保留类型化记录（原因 + 补偿范围）。"""
        mock_ingestion_log_store.list_failed_error_groups.return_value = [
            _error_group("etf_nav", "RATE_LIMIT"),
            _error_group("stock_daily", "UNKNOWN_ERROR"),
            _error_group("hk_hold", "EMPTY_DATA", count=5),
        ]

        excluded = retry_manager.excluded_failure_groups(max_attempts=3)

        assert [group.dataset for group in excluded] == [
            "stock_daily",
            "hk_hold",
        ]
        assert excluded[0].error_code == "UNKNOWN_ERROR"
        assert excluded[1].failure_count == 5


@pytest.mark.unit
class TestRetryFailed:
    """测试 retry_failed 方法。"""

    def test_retry_failed_all_success(
        self, retry_manager, mock_coordinator, mock_ingestion_log_store
    ) -> None:
        """重试失败任务，全部成功。"""
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25"),
                _failed_log("2024-12-26"),
                _failed_log("2024-12-27"),
            ],
        )

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="success",
                row_count=1000,
            ),
        ]

        result = retry_manager.retry_failed(dataset="stock_daily")

        assert result.dataset == "stock_daily"
        assert result.total_failed == 3
        assert result.retried_count == 3
        assert result.success_count == 3
        assert result.still_failed_count == 0
        assert len(result.results) == 3
        assert result.excluded_failures == ()
        mock_coordinator.ingest_date.assert_called()

    def test_retry_failed_partial_success(
        self, retry_manager, mock_coordinator, mock_ingestion_log_store
    ) -> None:
        """重试失败任务，部分成功。"""
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25"),
                _failed_log("2024-12-26"),
                _failed_log("2024-12-27"),
            ],
        )

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="failed",
                error="FETCH_ERROR",
                message="获取数据失败",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="success",
                row_count=1000,
            ),
        ]

        result = retry_manager.retry_failed(dataset="stock_daily")

        assert result.total_failed == 3
        assert result.retried_count == 3
        assert result.success_count == 2
        assert result.still_failed_count == 1

    def test_retry_failed_excludes_permanent_with_reason(
        self, retry_manager, mock_coordinator, mock_ingestion_log_store
    ) -> None:
        """永久失败被排除出重试且保留原因与补偿范围（#623 验收）。"""
        permanent = IngestionLog(
            dataset="global_index_daily",
            source="tushare",
            trade_date="2026-10-27",
            status=IngestionStatus.FAIL,
            error_code="UNKNOWN_ERROR",
            error_message="ColumnNotFoundError: unable to find column",
            attempts=1,
        )
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25", error_code="RATE_LIMIT"),
                permanent,
            ],
        )
        mock_coordinator.ingest_date.return_value = IngestionResult(
            dataset="global_index_daily",
            trade_date="2024-12-25",
            status="success",
            row_count=1000,
        )

        result = retry_manager.retry_failed(dataset="global_index_daily")

        # 只重试瞬态日期；永久失败保留在 excluded_failures。
        assert result.retried_count == 1
        mock_coordinator.ingest_date.assert_called_once_with(
            dataset="global_index_daily", trade_date="2024-12-25", force=True
        )
        assert len(result.excluded_failures) == 1
        excluded = result.excluded_failures[0]
        assert excluded.trade_date == "2026-10-27"
        assert excluded.error_code == "UNKNOWN_ERROR"
        assert "ColumnNotFoundError" in (excluded.error_message or "")

    def test_retry_failed_with_limit(
        self, retry_manager, mock_coordinator, mock_ingestion_log_store
    ) -> None:
        """使用限制参数重试部分失败任务。"""
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25"),
                _failed_log("2024-12-26"),
            ],
        )

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="success",
                row_count=1000,
            ),
        ]

        result = retry_manager.retry_failed(
            dataset="stock_daily",
            limit=2,
        )

        assert result.total_failed == 2  # 有3个失败，但只返回2个
        assert result.retried_count == 2
        assert result.success_count == 2

    def test_retry_failed_no_failed_dates(
        self, retry_manager, mock_ingestion_log_store
    ) -> None:
        """没有失败日期时返回空结果。"""
        _wire_failed_logs(mock_ingestion_log_store, [])

        result = retry_manager.retry_failed(dataset="stock_daily")

        assert result.dataset == "stock_daily"
        assert result.total_failed == 0
        assert result.retried_count == 0
        assert result.success_count == 0
        assert result.still_failed_count == 0
        assert len(result.results) == 0

    def test_retry_failed_uses_force_true(
        self, retry_manager, mock_coordinator, mock_ingestion_log_store
    ) -> None:
        """重试时使用 force=True 强制重新摄取。"""
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25"),
            ],
        )

        mock_coordinator.ingest_date.return_value = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-25",
            status="success",
            row_count=1000,
        )

        retry_manager.retry_failed(dataset="stock_daily")

        mock_coordinator.ingest_date.assert_called_once_with(
            dataset="stock_daily", trade_date="2024-12-25", force=True
        )

    def test_retry_failed_filters_by_max_attempts(
        self, retry_manager, mock_coordinator, mock_ingestion_log_store
    ) -> None:
        """按最大尝试次数筛选失败任务。"""
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25"),
            ],
        )

        mock_coordinator.ingest_date.return_value = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-25",
            status="success",
            row_count=1000,
        )

        retry_manager.retry_failed(
            dataset="stock_daily",
            max_attempts=2,
        )

        assert mock_ingestion_log_store.list_failed_logs.call_count == 2
        for call in mock_ingestion_log_store.list_failed_logs.call_args_list:
            assert call.kwargs["max_attempts"] == 2
            assert call.kwargs["failure_filter"] in {"transient", "non_transient"}

    def test_retry_failed_all_still_failed(
        self, retry_manager, mock_coordinator, mock_ingestion_log_store
    ) -> None:
        """重试全部仍然失败。"""
        _wire_failed_logs(
            mock_ingestion_log_store,
            [
                _failed_log("2024-12-25"),
                _failed_log("2024-12-26"),
            ],
        )

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="failed",
                error="FETCH_ERROR",
                message="获取数据失败",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="failed",
                error="RATE_LIMIT",
                message="限流",
            ),
        ]

        result = retry_manager.retry_failed(dataset="stock_daily")

        assert result.total_failed == 2
        assert result.retried_count == 2
        assert result.success_count == 0
        assert result.still_failed_count == 2
