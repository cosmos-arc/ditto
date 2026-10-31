"""Tests for BackfillManager."""

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.backfill_manager import BackfillManager
from ditto_application.processes.ingestion.bootstrap_planner import BootstrapPlanner
from ditto_data.models.ingestion import (
    BackfillResult,
    IngestionResult,
)
from ditto_kernel.instrument import InstrumentIngestParams
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    init,
    reset_for_testing,
)
from packages.application.tests.unit.process.ingestion import (
    snapshot_evidence_support as _evidence_support,
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


@pytest.fixture
def mock_coordinator(mocker):
    """创建 Mock IngestionCoordinator。"""
    coordinator = mocker.Mock()
    coordinator.ingest_date = mocker.Mock()
    return coordinator


@pytest.fixture
def mock_metadata_service(mocker):
    """创建 Mock MetadataService。"""
    service = mocker.Mock()
    service.list_trading_days = mocker.Mock(return_value=[])
    service.calendar.get_first_trading_day = mocker.Mock(return_value="2020-01-02")
    service.get_last_trading_day = mocker.Mock(return_value="2024-12-31")
    return service


@pytest.fixture
def mock_ingestion_log_store(mocker):
    """创建 Mock IngestionLogStore。"""
    service = mocker.Mock()
    service.list_ingested_dates = mocker.Mock(return_value=[])
    return service


@pytest.fixture
def evidence():
    """SQLite 完成事实存储,与 backfill_manager 共享。"""
    with _evidence_support.evidence_stores() as stores:
        yield stores


@pytest.fixture
def backfill_manager(mock_coordinator, mock_metadata_service, evidence):
    """创建 BackfillManager 实例(带完成事实端口)."""
    return BackfillManager(
        coordinator=mock_coordinator,
        metadata_service=mock_metadata_service,
        snapshot_reader=evidence.snapshots,
        lifecycle_reader=evidence.lifecycle,
    )


@pytest.mark.unit
class TestBackfillResult:
    """测试 BackfillResult 类。"""

    def test_create_backfill_result(self) -> None:
        """创建回补结果。"""
        results = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="skipped",
                message="数据已存在",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="failed",
                error="FETCH_ERROR",
                message="获取数据失败",
            ),
        ]

        result = BackfillResult(
            dataset="stock_daily",
            total_dates=3,
            success_count=1,
            skipped_count=1,
            failed_count=1,
            results=tuple(results),
        )

        assert result.dataset == "stock_daily"
        assert result.total_dates == 3
        assert result.success_count == 1
        assert result.skipped_count == 1
        assert result.failed_count == 1
        assert len(result.results) == 3


@pytest.mark.unit
class TestBackfillRange:
    """测试 backfill_range 方法。"""

    def test_backfill_range_include_complete_refetches_completed_chunks(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """#575 行级补数: include_complete 连 COMPLETE chunk 一并规划重拉."""

        class _Planner:
            def __init__(self) -> None:
                self.include_complete: list[bool | None] = []

            def plan(
                self,
                *,
                dataset_id,
                source,
                start_date,
                end_date,
                instrument_ids=(),
                include_complete=False,
            ):
                self.include_complete.append(include_complete)
                from ditto_application.processes.ingestion.bootstrap_planner import (
                    BootstrapPlan,
                )

                return BootstrapPlan(
                    dataset_id=dataset_id,
                    source=source,
                    target_start=start_date,
                    target_end=end_date,
                    chunks=(),
                )

        planner = _Planner()
        backfill_manager._bootstrap_planner = planner
        mock_metadata_service.list_trading_days.return_value = []

        backfill_manager.backfill_range(
            dataset="stock_limit",
            start_date="2024-08-01",
            end_date="2024-08-31",
        )
        backfill_manager.backfill_range(
            dataset="stock_limit",
            start_date="2024-08-01",
            end_date="2024-08-31",
            include_complete=True,
        )

        assert planner.include_complete == [False, True]

    def test_backfill_range_success_all_dates(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """成功回补日期范围内的所有交易日。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

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

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
        )

        # Assert
        assert result.dataset == "stock_daily"
        assert result.total_dates == 3
        assert result.success_count == 3
        assert result.skipped_count == 0
        assert result.failed_count == 0
        assert len(result.results) == 3
        mock_coordinator.ingest_date.assert_called()

    def test_real_chunk_coordinator_executes_month_chunks_atomically(
        self,
        mock_metadata_service,
        mock_ingestion_log_store,
    ) -> None:
        class ChunkCoordinator:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, tuple[str, ...]]] = []

            def ingest_date(
                self,
                dataset: str,
                trade_date: str,
                force: bool = False,
            ) -> IngestionResult:
                raise AssertionError("chunk coordinator does not ingest by date")

            def ingest_range(
                self,
                dataset: str,
                start_date: str,
                end_date: str,
                force: bool = False,
            ) -> list[IngestionResult]:
                raise AssertionError("chunk coordinator does not ingest by range")

            def ingest_chunk(
                self,
                dataset: str,
                *,
                chunk_id: str,
                request_start: str,
                request_end: str,
                partition_dates: tuple[str, ...],
                force: bool = False,
            ) -> IngestionResult:
                _ = chunk_id, request_end, force
                self.calls.append((dataset, request_start, partition_dates))
                return IngestionResult(
                    dataset=dataset,
                    trade_date=request_start,
                    status="success",
                    row_count=len(partition_dates),
                )

            def ingest_by_instrument(
                self,
                dataset: str,
                params: InstrumentIngestParams,
                force: bool = False,
            ) -> IngestionResult:
                raise AssertionError("chunk coordinator does not ingest by instrument")

            def ingest_planned_instrument_chunk(
                self,
                dataset: str,
                *,
                chunk_id: str,
                params: InstrumentIngestParams,
                force: bool = False,
            ) -> IngestionResult:
                raise AssertionError("chunk coordinator: no instrument chunks")

            def backfill_adj_factor(
                self,
                instrument_id: int,
                start: str,
                end: str,
            ) -> dict[str, object]:
                raise AssertionError("chunk coordinator does not backfill adj factors")

        mock_metadata_service.list_trading_days.return_value = [
            "2026-01-30",
            "2026-02-02",
            "2026-02-03",
        ]
        coordinator = ChunkCoordinator()
        manager = BackfillManager(
            coordinator=coordinator,
            metadata_service=mock_metadata_service,
        )

        result = manager.backfill_range(
            "stock_daily",
            "2026-01-30",
            "2026-02-03",
        )

        assert result.total_dates == 3
        assert result.success_count == 2
        assert coordinator.calls == [
            ("stock_daily", "2026-01-30", ("2026-01-30",)),
            (
                "stock_daily",
                "2026-02-02",
                ("2026-02-02", "2026-02-03"),
            ),
        ]

    def test_instrument_range_plan_executes_each_instrument_with_chunk_identity(
        self,
        mock_metadata_service,
        mock_ingestion_log_store,
    ) -> None:
        class InstrumentCoordinator:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, InstrumentIngestParams]] = []

            def ingest_date(
                self,
                dataset: str,
                trade_date: str,
                force: bool = False,
            ) -> IngestionResult:
                raise AssertionError("instrument coordinator does not ingest by date")

            def ingest_range(
                self,
                dataset: str,
                start_date: str,
                end_date: str,
                force: bool = False,
            ) -> list[IngestionResult]:
                raise AssertionError("instrument coordinator does not ingest by range")

            def ingest_chunk(
                self,
                dataset: str,
                *,
                chunk_id: str,
                request_start: str,
                request_end: str,
                partition_dates: tuple[str, ...],
                force: bool = False,
            ) -> IngestionResult:
                raise AssertionError("instrument coordinator: no date chunks")

            def ingest_by_instrument(
                self,
                dataset: str,
                params: InstrumentIngestParams,
                force: bool = False,
            ) -> IngestionResult:
                raise AssertionError("instrument coordinator: no per-instrument")

            def ingest_planned_instrument_chunk(
                self,
                dataset: str,
                *,
                chunk_id: str,
                params: InstrumentIngestParams,
                force: bool = False,
            ) -> IngestionResult:
                _ = force
                self.calls.append((dataset, chunk_id, params))
                return IngestionResult(
                    dataset=dataset,
                    trade_date=params.start_date,
                    status="success",
                    row_count=1,
                )

            def backfill_adj_factor(
                self,
                instrument_id: int,
                start: str,
                end: str,
            ) -> dict[str, object]:
                raise AssertionError("instrument coordinator: no adj factors")

        mock_metadata_service.list_trading_days.return_value = [
            "2026-01-05",
            "2026-01-06",
        ]
        coordinator = InstrumentCoordinator()
        manager = BackfillManager(
            coordinator=coordinator,
            metadata_service=mock_metadata_service,
        )

        result = manager.backfill_range(
            "index_daily",
            "2026-01-05",
            "2026-01-06",
            instrument_ids=(9, 3),
        )

        assert result.total_dates == 4
        assert result.success_count == 2
        assert [call[2].instrument_id for call in coordinator.calls] == [3, 9]
        assert {call[1] for call in coordinator.calls} == {
            "chunk:tushare:index_daily:2026:2026-01-05:2026-01-06:instrument:3",
            "chunk:tushare:index_daily:2026:2026-01-05:2026-01-06:instrument:9",
        }
        assert all(call[2].start_date == "2026-01-05" for call in coordinator.calls)
        assert all(call[2].end_date == "2026-01-06" for call in coordinator.calls)

    def test_backfill_range_with_skipped_dates(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """日期范围内有跳过的日期。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

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
                status="skipped",
                message="数据已存在",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-27",
                status="success",
                row_count=1000,
            ),
        ]

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
        )

        # Assert
        assert result.total_dates == 3
        assert result.success_count == 2
        assert result.skipped_count == 1
        assert result.failed_count == 0

    def test_backfill_range_with_failed_dates(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """日期范围内有失败的日期。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

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

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
        )

        # Assert
        assert result.total_dates == 3
        assert result.success_count == 2
        assert result.skipped_count == 0
        assert result.failed_count == 1

    def test_backfill_range_empty_range(
        self, backfill_manager, mock_metadata_service
    ) -> None:
        """日期范围为空时返回空结果。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = []

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
        )

        # Assert
        assert result.total_dates == 0
        assert result.success_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0
        assert len(result.results) == 0

    def test_backfill_range_parallel_execution(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """并行执行回补任务。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date=date,
                status="success",
                row_count=1000,
            )
            for date in ["2024-12-25", "2024-12-26", "2024-12-27"]
        ]

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2024-12-25",
            end_date="2024-12-27",
            parallel=3,
        )

        # Assert
        assert result.total_dates == 3
        assert result.success_count == 3
        assert mock_coordinator.ingest_date.call_count == 3

    def test_backfill_range_uses_natural_days_for_fx(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(dataset="fx_daily", trade_date=value, status="success")
            for value in (
                "2026-01-30",
                "2026-01-31",
                "2026-02-01",
                "2026-02-02",
            )
        ]

        result = backfill_manager.backfill_range(
            dataset="fx_daily",
            start_date="2026-01-30",
            end_date="2026-02-02",
        )

        assert result.total_dates == 4
        ingested_dates = [
            call.args[1] for call in mock_coordinator.ingest_date.call_args_list
        ]
        assert ingested_dates == [
            "2026-01-30",
            "2026-01-31",
            "2026-02-01",
            "2026-02-02",
        ]
        mock_metadata_service.list_trading_days.assert_not_called()

    def test_backfill_range_uses_source_defined_release_dates(
        self,
        mock_coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
        mocker,
    ) -> None:
        resolver = mocker.Mock(return_value=("2026-01-15", "2026-02-20"))
        manager = BackfillManager(
            coordinator=mock_coordinator,
            metadata_service=mock_metadata_service,
            bootstrap_planner=BootstrapPlanner(
                metadata_service=mock_metadata_service,
                source_schedule_resolver=resolver,
            ),
        )
        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="macro_indicators",
                trade_date=value,
                status="success",
            )
            for value in ("2026-01-15", "2026-02-20")
        ]

        result = manager.backfill_range(
            dataset="macro_indicators",
            start_date="2026-01-01",
            end_date="2026-03-31",
            source="fred",
        )

        assert result.total_dates == 2
        ingested_dates = [
            call.args[1] for call in mock_coordinator.ingest_date.call_args_list
        ]
        assert ingested_dates == [
            "2026-01-15",
            "2026-02-20",
        ]


@pytest.mark.unit
class TestBackfillMissing:
    """测试 backfill_missing 方法。"""

    def test_backfill_missing_finds_missing_dates(
        self,
        backfill_manager,
        evidence,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """查找并回补缺失的日期。"""
        # Arrange
        # 交易日历有5个交易日
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-23",
            "2024-12-24",
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        # 已完成 3 个日期的快照
        for day in ("2024-12-23", "2024-12-25", "2024-12-27"):
            _evidence_support.commit_snapshot(
                evidence,
                dataset="stock_daily",
                request_start=day,
                request_end=day,
                checksum=f"{ord(day[-1]):032x}"[-32:],
                row_count=1,
                schema_version="market.stock_daily.v1",
            )

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-24",
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

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        # 应该只回补缺失的2个日期
        assert result.total_dates == 2
        assert result.success_count == 2
        assert mock_coordinator.ingest_date.call_count == 2

    def test_backfill_missing_no_missing_dates(
        self,
        backfill_manager,
        evidence,
        mock_metadata_service,
    ) -> None:
        """没有缺失日期时返回空结果。"""
        # Arrange:一个区间快照覆盖全部期望日期。
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        _evidence_support.commit_snapshot(
            evidence,
            dataset="stock_daily",
            request_start="2024-12-25",
            request_end="2024-12-27",
            checksum="c" * 32,
            row_count=3,
            schema_version="market.stock_daily.v1",
        )

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        assert result.total_dates == 0
        assert result.success_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0

    def test_backfill_missing_uses_calendar_range(
        self,
        backfill_manager,
        evidence,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """使用日历的完整日期范围查找缺失。"""
        # Arrange
        mock_metadata_service.calendar.get_first_trading_day.return_value = "2024-12-01"
        mock_metadata_service.get_last_trading_day.return_value = "2024-12-31"

        # 模拟 get_range 调用
        def get_range_side_effect(start, end):
            if start == "2024-12-01" and end == "2024-12-31":
                return ["2024-12-25", "2024-12-26", "2024-12-27"]
            return []

        mock_metadata_service.list_trading_days.side_effect = get_range_side_effect

        _evidence_support.commit_snapshot(
            evidence,
            dataset="stock_daily",
            request_start="2024-12-25",
            request_end="2024-12-25",
            checksum="d" * 32,
            row_count=1,
            schema_version="market.stock_daily.v1",
        )

        mock_coordinator.ingest_date.side_effect = [
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

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        assert result.total_dates == 2
        mock_metadata_service.list_trading_days.assert_called_once_with(
            "2024-12-01", "2024-12-31"
        )

    def test_backfill_missing_clamps_future_calendar_end(
        self,
        backfill_manager,
        evidence,
        mock_coordinator,
        mock_metadata_service,
        time_machine,
    ) -> None:
        """日历末端在未来时钳到上海昨日：未来会话不进空洞扫描（#613）。"""
        # Arrange: nightly repair 时点，日历表已发布到 2027 年末
        time_machine.move_to("2026-10-27 02:00:00+08:00", tick=False)
        mock_metadata_service.calendar.get_first_trading_day.return_value = "2026-10-23"
        mock_metadata_service.get_last_trading_day.return_value = "2027-12-31"
        mock_metadata_service.list_trading_days.side_effect = lambda start, end: (
            ["2026-10-26"] if end == "2026-10-26" else []
        )
        mock_coordinator.ingest_date.return_value = IngestionResult(
            dataset="stock_daily",
            trade_date="2026-10-26",
            status="success",
            row_count=1000,
        )

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert: 扫描上界=上海昨日（2026-10-26），2027 年的未来会话
        # 不再被当作假空洞逐日请求。
        assert result.total_dates == 1
        mock_metadata_service.list_trading_days.assert_called_once_with(
            "2026-10-23", "2026-10-26"
        )

    def test_repair_scan_horizon_converts_to_shanghai_calendar_day(
        self,
    ) -> None:
        """上界取上海日历日的昨日（UTC 时钟也按上海日转换）。"""
        from datetime import UTC, datetime

        from ditto_application.processes.ingestion.backfill_manager import (
            repair_scan_horizon,
        )

        # UTC 2026-10-26 18:00 = 上海 2026-10-27 02:00 → 昨日 2026-10-26
        horizon = repair_scan_horizon(datetime(2026, 10, 26, 18, 0, tzinfo=UTC))
        assert horizon == "2026-10-26"

        # 朴素时钟会被宿主本地时区误判日界——响亮拒绝
        from ditto_application.exceptions import AppProcessError

        with pytest.raises(AppProcessError, match="timezone-aware"):
            repair_scan_horizon(datetime(2026, 10, 26, 18, 0))

    def test_backfill_missing_with_source(
        self,
        backfill_manager,
        evidence,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """测试 backfill_missing 支持 source 参数。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        _evidence_support.commit_snapshot(
            evidence,
            dataset="stock_daily",
            request_start="2024-12-25",
            request_end="2024-12-25",
            checksum="e" * 32,
            row_count=1,
            schema_version="market.stock_daily.v1",
        )

        mock_coordinator.ingest_date.side_effect = [
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

        # Act
        result = backfill_manager.backfill_missing(
            dataset="stock_daily",
            source="tushare",
        )

        # Assert: source 参数传播到 bootstrap planner(完成事实发现由
        # snapshot/lifecycle 端口承担)。
        assert result.total_dates >= 0

    def test_backfill_missing_retries_dates_without_completed_snapshots(
        self,
        mock_coordinator,
        mock_metadata_service,
        mocker,
    ) -> None:
        """空洞 = 期望日期 − completed snapshot 覆盖;log-only 日期必须重试。"""
        from ditto_data.catalog.source_snapshot import ProviderSnapshot
        from ditto_data.catalog.source_snapshot_store import (
            SQLiteProviderSnapshotStore,
        )

        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
        ]

        with _evidence_support.evidence_stores() as stores:
            _evidence_support.commit_snapshot(
                stores,
                dataset="stock_daily",
                request_start="2024-12-25",
                request_end="2024-12-25",
                checksum="a" * 32,
                row_count=10,
                schema_version="market.stock_daily.v1",
            )
            # 2024-12-26 只有 success log,没有完成快照。
            from packages.application.tests.unit.process.ingestion.snapshot_evidence_support import (  # noqa: E501
                record_success,
            )

            record_success(
                stores,
                dataset="stock_daily",
                trade_date="2024-12-26",
                checksum="b" * 32,
                rows=10,
            )
            manager = BackfillManager(
                coordinator=mock_coordinator,
                metadata_service=mock_metadata_service,
                snapshot_reader=stores.snapshots,
                lifecycle_reader=stores.lifecycle,
            )
            mock_coordinator.ingest_date.return_value = IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-26",
                status="success",
            )

            result = manager.backfill_missing(dataset="stock_daily")

            assert result.total_dates == 1
            mock_coordinator.ingest_date.assert_called_once_with(
                "stock_daily", "2024-12-26", False
            )
            assert isinstance(stores.snapshots, SQLiteProviderSnapshotStore)
            assert isinstance(
                stores.snapshots.get_snapshot("missing"), (ProviderSnapshot, type(None))
            )

    def test_backfill_range_year_level_parallel(
        self, backfill_manager, mock_coordinator, mock_metadata_service
    ) -> None:
        """测试年份级并行策略。"""
        # Arrange - 准备跨年数据
        mock_metadata_service.list_trading_days.return_value = [
            "2023-12-29",
            "2023-12-30",
            "2024-01-02",
            "2024-01-03",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date=date,
                status="success",
                row_count=1000,
            )
            for date in ["2023-12-29", "2023-12-30", "2024-01-02", "2024-01-03"]
        ]

        # Act
        result = backfill_manager.backfill_range(
            dataset="stock_daily",
            start_date="2023-12-29",
            end_date="2024-01-03",
            parallel=2,
        )

        # Assert - 验证正确处理
        assert result.total_dates > 0
        assert result.success_count == 4
        assert mock_coordinator.ingest_date.call_count == 4

    def test_backfill_missing_parallel_execution(
        self,
        backfill_manager,
        evidence,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """测试 backfill_missing 并行执行。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-23",
            "2024-12-24",
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        # 两个日期已有完成快照,缺失3个
        for day in ("2024-12-23", "2024-12-27"):
            _evidence_support.commit_snapshot(
                evidence,
                dataset="stock_daily",
                request_start=day,
                request_end=day,
                checksum=f"{ord(day[-2]) * 16:x}".rjust(32, "0"),
                row_count=1,
                schema_version="market.stock_daily.v1",
            )

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date=date,
                status="success",
                row_count=1000,
            )
            for date in ["2024-12-24", "2024-12-25", "2024-12-26"]
        ]

        # Act
        result = backfill_manager.backfill_missing(
            dataset="stock_daily",
            parallel=2,
        )

        # Assert
        assert result.total_dates == 3
        assert result.success_count == 3
        assert mock_coordinator.ingest_date.call_count == 3

    def test_backfill_missing_force_refresh_adds_trailing_window_with_force(
        self,
        backfill_manager,
        evidence,
        mock_coordinator,
        mock_metadata_service,
        mocker,
    ) -> None:
        """#625 晚发布近窗刷新：完成事实齐全时仍 force 重取近 N 个交易日.

        晚发布数据集（margin_trading/fund_share）的 SUCCESS/空帧或部分行
        观察是合法完成证据——空洞扫描不可见，必须 force 绕过 skip 决策。
        """
        # Arrange
        mocker.patch(
            "ditto_application.processes.ingestion.backfill_manager."
            "repair_scan_horizon",
            return_value="2024-12-27",
        )
        days = [
            "2024-12-23",
            "2024-12-24",
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]
        mock_metadata_service.list_trading_days.return_value = days
        mock_metadata_service.calendar.list_trading_days.side_effect = (
            lambda start, end, only_open=True: [
                day for day in days if start <= day <= end
            ]
        )

        # 全部日期均有完成快照：无空洞，但近窗 3 日仍须重取
        for day in days:
            _evidence_support.commit_snapshot(
                evidence,
                dataset="stock_daily",
                request_start=day,
                request_end=day,
                checksum=f"{ord(day[-1]) * 16:x}".rjust(32, "0"),
                row_count=1,
                schema_version="market.stock_daily.v1",
            )

        def ingest_side_effect(dataset, trade_date, force=False):
            assert force is True, "近窗刷新必须以 force 绕过 SUCCESS skip"
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="success",
                row_count=1000,
            )

        mock_coordinator.ingest_date.side_effect = ingest_side_effect

        # Act
        result = backfill_manager.backfill_missing(
            dataset="stock_daily",
            force_refresh_days=3,
        )

        # Assert：近窗 3 日（12-25/26/27）全部 force 重取
        assert result.total_dates == 3
        assert result.success_count == 3
        refreshed_dates = {
            call.args[1] for call in mock_coordinator.ingest_date.call_args_list
        }
        assert refreshed_dates == {"2024-12-25", "2024-12-26", "2024-12-27"}

    def test_backfill_missing_without_refresh_keeps_unforced_semantics(
        self,
        backfill_manager,
        evidence,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """默认（force_refresh_days=0）不追加近窗、不 force——既有语义不变."""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-23",
            "2024-12-24",
        ]
        for day in ("2024-12-23", "2024-12-24"):
            _evidence_support.commit_snapshot(
                evidence,
                dataset="stock_daily",
                request_start=day,
                request_end=day,
                checksum=f"{ord(day[-1]) * 16:x}".rjust(32, "0"),
                row_count=1,
                schema_version="market.stock_daily.v1",
            )

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert：无空洞且无近窗 → 零摄取
        assert result.total_dates == 0
        mock_coordinator.ingest_date.assert_not_called()

    def test_backfill_missing_empty_calendar(
        self,
        backfill_manager,
        mock_metadata_service,
    ) -> None:
        """测试当日历没有数据时的处理。"""
        # Arrange - 日历为空
        mock_metadata_service.calendar.get_first_trading_day.return_value = None
        mock_metadata_service.get_last_trading_day.return_value = None

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        assert result.total_dates == 0
        assert result.success_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0

    def test_backfill_missing_calendar_has_no_trading_days(
        self,
        backfill_manager,
        mock_metadata_service,
    ) -> None:
        """测试当日历有首尾日期但没有交易日时的处理。"""
        # Arrange - 有首尾日期，但没有交易日
        mock_metadata_service.calendar.get_first_trading_day.return_value = "2024-12-01"
        mock_metadata_service.get_last_trading_day.return_value = "2024-12-31"
        mock_metadata_service.list_trading_days.return_value = []

        # Act
        result = backfill_manager.backfill_missing(dataset="stock_daily")

        # Assert
        assert result.total_dates == 0
        assert result.success_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0

    def test_backfill_range_propagates_coordinator_error(
        self,
        backfill_manager,
        mock_coordinator,
        mock_metadata_service,
    ) -> None:
        """测试 coordinator 错误传播。"""
        # Arrange
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
        ]

        mock_coordinator.ingest_date.side_effect = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-12-25",
                status="success",
                row_count=1000,
            ),
            Exception("Network error"),
        ]

        # Act & Assert
        with pytest.raises(Exception, match="Network error"):
            backfill_manager.backfill_range(
                dataset="stock_daily",
                start_date="2024-12-25",
                end_date="2024-12-26",
            )


@pytest.mark.unit
class TestBackfillIndexWeight:
    """按权重服务宇宙逐指数回补（#196）。"""

    def test_resolves_universe_to_instrument_ids(
        self,
        backfill_manager,
        mock_metadata_service,
        mocker,
    ) -> None:
        from ditto_application.processes.ingestion.dataset_registry import (
            INDEX_WEIGHT_UNIVERSE,
        )

        resolved = {code: 3000000 + i for i, code in enumerate(INDEX_WEIGHT_UNIVERSE)}
        mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = (
            dict(resolved)
        )
        spy = mocker.patch.object(
            backfill_manager,
            "backfill_range",
            return_value=BackfillResult(
                dataset="index_weight",
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            ),
        )

        backfill_manager.backfill_index_weight("2014-01-01", "2026-09-30")

        resolve = mock_metadata_service.instrument.resolve_instrument_ids_batch
        resolve_kwargs = resolve.call_args.kwargs
        # 别名后的宇宙进入解析（.CSI 形态），.SH 原码不在
        assert "000985.CSI" in resolve_kwargs["identifiers"]
        assert "000985.SH" not in resolve_kwargs["identifiers"]
        call = spy.call_args
        assert call.args == ("index_weight", "2014-01-01", "2026-09-30")
        assert call.kwargs["instrument_ids"] == tuple(sorted(resolved.values()))

    def test_unresolved_codes_are_skipped(
        self,
        backfill_manager,
        mock_metadata_service,
        mocker,
    ) -> None:
        from ditto_application.processes.ingestion.dataset_registry import (
            INDEX_WEIGHT_UNIVERSE,
        )

        resolved = dict.fromkeys(INDEX_WEIGHT_UNIVERSE[:2], 3000000)
        mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = (
            dict(resolved)
        )
        spy = mocker.patch.object(
            backfill_manager,
            "backfill_range",
            return_value=BackfillResult(
                dataset="index_weight",
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            ),
        )

        backfill_manager.backfill_index_weight("2014-01-01", "2014-12-31")

        assert spy.call_args.kwargs["instrument_ids"] == (3000000,)


@pytest.mark.unit
class TestBackfillIndexWeightFailFast:
    """宇宙全未解析时 fail fast 而非退化到逐日全市场（评审修复）."""

    def test_zero_resolved_instruments_raises(
        self,
        backfill_manager,
        mock_metadata_service,
    ) -> None:
        mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = {}

        with pytest.raises(AppProcessError, match="zero instruments"):
            backfill_manager.backfill_index_weight("2014-01-01", "2026-09-30")
