"""Tests for MetadataManager."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from ditto_application.processes.ingestion.metadata_manager import MetadataManager
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_platform.foundation import (
    ChecksumCompute,
    Environment,
    ObservabilityConfig,
    init,
    reset_for_testing,
)


@pytest.fixture
def mock_ingestion_log_store(mocker):
    """创建 Mock IngestionLogStore。"""
    service = mocker.Mock()
    service.get_log = mocker.Mock(return_value=None)
    return service


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


@pytest.mark.unit
class TestShouldSkip:
    """测试 should_skip 方法。"""

    def _catalog_with_asset(
        self,
        *,
        dataset: str = "stock_daily",
        trade_date: str = "2024-12-27",
        source: str = "tushare",
        checksum: str = "abc123",
        row_count: int = 1000,
        freshness_at: datetime | None = None,
    ) -> InMemoryDataCatalog:
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id=dataset,
                    namespace="market",
                    partition_keys=(f"trade_date={trade_date}",),
                ),
                storage_uri=f"{dataset}/2024",
                schema=DataSchemaFingerprint(
                    schema_hash=f"schema:{dataset}:v1",
                    row_count=row_count,
                    created_at=datetime(2024, 12, 27, 18, 0, tzinfo=UTC),
                ),
                source=source,
                freshness_at=freshness_at or datetime(2024, 12, 27, 18, 5, tzinfo=UTC),
                source_snapshot_id=(
                    f"snapshot:{source}:{dataset}:{trade_date}:{checksum}:quality=l1-l2"
                ),
            )
        )
        return catalog

    def test_should_not_skip_when_force_is_true(self, mock_ingestion_log_store) -> None:
        """force=True 时不跳过。"""
        manager = MetadataManager(mock_ingestion_log_store)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=True,
        )

        assert should_skip is False
        assert reason is None

    def test_should_not_skip_when_no_history(self, mock_ingestion_log_store) -> None:
        """无历史记录时不跳过。"""
        # Mock get_log 返回 None（无历史记录）
        mock_ingestion_log_store.get_log.return_value = None
        manager = MetadataManager(mock_ingestion_log_store)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None
        mock_ingestion_log_store.get_log.assert_called_once()

    def test_catalog_without_success_log_is_reingested(
        self,
        mock_ingestion_log_store,
    ) -> None:
        """Catalog-only 残留不能形成永久 skip/DQ 死循环。"""
        mock_ingestion_log_store.get_log.return_value = None
        manager = MetadataManager(
            mock_ingestion_log_store,
            data_catalog_reader=self._catalog_with_asset(
                freshness_at=datetime.now(UTC),
            ),
        )

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None

    def test_should_not_skip_when_catalog_asset_is_stale(
        self,
        mock_ingestion_log_store,
    ) -> None:
        """无 log 历史但 catalog 资产超过 freshness SLA 时不跳过。"""
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        mock_ingestion_log_store.get_log.return_value = None
        manager = MetadataManager(
            mock_ingestion_log_store,
            data_catalog_reader=self._catalog_with_asset(
                freshness_at=now - timedelta(hours=60),
            ),
            now=lambda: now,
        )

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None

    def test_previous_failure_overrides_catalog_skip(
        self,
        mock_ingestion_log_store,
    ) -> None:
        """历史失败记录优先重试，不被 catalog entry 直接跳过。"""
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network error",
        )
        manager = MetadataManager(
            mock_ingestion_log_store,
            data_catalog_reader=self._catalog_with_asset(
                freshness_at=datetime.now(UTC),
            ),
        )

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None

    def test_should_skip_when_previous_success(self, mock_ingestion_log_store) -> None:
        """历史成功时跳过。"""
        # Mock get_log 返回成功的历史记录
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        manager = MetadataManager(
            mock_ingestion_log_store,
            data_catalog_reader=self._catalog_with_asset(),
        )

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is True
        assert reason is not None
        assert "成功" in reason or "SUCCESS" in reason

    def test_sparse_range_success_skips_only_with_attested_cumulative_snapshot(
        self,
        mock_ingestion_log_store,
    ) -> None:
        """Range-shaped sparse evidence must replay locally without a provider call."""
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="corporate_actions",
            source="tushare",
            trade_date="2024-03-28",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=126,
        )
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="corporate_actions",
                    namespace="capital",
                    partition_keys=(
                        "start_date=2024-03-28",
                        "end_date=2024-03-28",
                    ),
                ),
                storage_uri="corporate_actions/2024",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:corporate_actions:v2",
                    row_count=126,
                ),
                source="tushare",
                freshness_at=datetime(2024, 3, 28, 18, 5, tzinfo=UTC),
                source_snapshot_id=(
                    "snapshot:tushare:corporate_actions:all:2024-03-28:"
                    "2024-03-28:abc123:quality=l1-l2"
                ),
            )
        )
        manager = MetadataManager(
            mock_ingestion_log_store,
            data_catalog_reader=catalog,
        )

        decision = manager.get_skip_decision(
            dataset="corporate_actions",
            trade_date="2024-03-28",
            source="tushare",
        )

        assert decision.should_skip is True
        assert decision.checksum == "abc123"
        assert decision.row_count == 126

    @pytest.mark.parametrize(
        ("checksum", "rows"),
        [(None, 0), ("", 0), ("sha256:known", None), ("sha256:known", -1)],
    )
    def test_previous_success_without_snapshot_evidence_is_retried(
        self,
        mock_ingestion_log_store,
        checksum: str | None,
        rows: int | None,
    ) -> None:
        """An empty sparse success must not permanently mask missing PIT evidence."""
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="balance_sheet",
            source="tushare",
            trade_date="2025-01-06",
            status=IngestionStatus.SUCCESS,
            checksum=checksum,
            rows=rows,
        )
        manager = MetadataManager(mock_ingestion_log_store)

        decision = manager.get_skip_decision(
            dataset="balance_sheet",
            trade_date="2025-01-06",
            source="tushare",
        )

        assert decision.should_skip is False
        assert decision.checksum is None
        assert decision.row_count is None

    def test_should_not_skip_when_previous_failed(
        self, mock_ingestion_log_store
    ) -> None:
        """历史失败时不跳过。"""
        # Mock get_log 返回失败的历史记录
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network error",
        )
        manager = MetadataManager(mock_ingestion_log_store)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None

    def test_should_not_skip_when_log_store_not_set(self) -> None:
        """log_store=None 时不跳过。"""
        manager = MetadataManager(None)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        # 没有 ingestion_log_store，不跳过
        assert should_skip is False
        assert reason is None

    def test_should_skip_uses_source_parameter(self, mock_ingestion_log_store) -> None:
        """should_skip 应使用传入的 source 参数，而非硬编码。"""
        # Mock get_log 返回成功的历史记录
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="akshare",  # 不同的数据源
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        manager = MetadataManager(
            mock_ingestion_log_store,
            data_catalog_reader=self._catalog_with_asset(source="akshare"),
        )

        # 使用 akshare 数据源
        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            source="akshare",
            force=False,
        )

        # 验证 get_log 被调用时使用了正确的 source
        assert mock_ingestion_log_store.get_log.call_count == 2
        for call in mock_ingestion_log_store.get_log.call_args_list:
            assert call.kwargs == {
                "dataset": "stock_daily",
                "source": "akshare",
                "trade_date": "2024-12-27",
            }

        assert should_skip is True
        assert reason is not None


@pytest.mark.unit
class TestCompareData:
    """测试 compare_data 方法。"""

    def test_compare_returns_true_when_data_same(
        self, mock_ingestion_log_store
    ) -> None:
        """相同数据返回 True。"""
        manager = MetadataManager(mock_ingestion_log_store)

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df)

        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum=checksum,
            rows=2,
        )

        result = manager.compare_data(df, existing_log)

        assert result is True

    def test_compare_returns_false_when_data_different(
        self, mock_ingestion_log_store
    ) -> None:
        """不同数据返回 False。"""
        manager = MetadataManager(mock_ingestion_log_store)

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        # 不同的 checksum
        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="different_checksum",
            rows=2,
        )

        result = manager.compare_data(df, existing_log)

        assert result is False

    def test_compare_returns_false_when_row_count_different(
        self, mock_ingestion_log_store
    ) -> None:
        """行数不同返回 False。"""
        manager = MetadataManager(mock_ingestion_log_store)

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df)

        # 行数不匹配
        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum=checksum,
            rows=999,  # 不匹配
        )

        result = manager.compare_data(df, existing_log)

        assert result is False

    def test_compare_handles_null_checksum_in_log(
        self, mock_ingestion_log_store
    ) -> None:
        """处理 log 中 checksum 为 None 的情况。"""
        manager = MetadataManager(mock_ingestion_log_store)

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        # checksum 为 None（失败的记录）
        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            checksum=None,
            error_code="ERROR",
            error_message="Some error",
        )

        result = manager.compare_data(df, existing_log)

        assert result is False

    def test_compare_returns_true_when_rows_is_none(
        self, mock_ingestion_log_store
    ) -> None:
        """当 existing_log.rows 为 None 时，仅比较 checksum。"""
        manager = MetadataManager(mock_ingestion_log_store)

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df)

        # rows 为 None（老数据可能没有记录行数）
        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum=checksum,
            rows=None,  # 行数为 None
        )

        result = manager.compare_data(df, existing_log)

        # checksum 相同，rows 为 None 时不比较行数，应返回 True
        assert result is True


@pytest.mark.unit
class TestShouldSkipEdgeCases:
    """测试 should_skip 方法的边界情况。"""

    def test_skip_reason_contains_checksum_and_rows(
        self, mock_ingestion_log_store
    ) -> None:
        """跳过原因应包含 checksum 和 rows 信息。"""
        # Mock get_log 返回成功的历史记录
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abcdef1234567890",
            rows=1000,
        )
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="stock_daily/2024",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=1000,
                ),
                source="tushare",
                freshness_at=datetime(2024, 12, 27, 18, 5, tzinfo=UTC),
                source_snapshot_id=(
                    "snapshot:tushare:stock_daily:2024-12-27:"
                    "abcdef1234567890:quality=l1-l2"
                ),
            )
        )
        manager = MetadataManager(
            mock_ingestion_log_store,
            data_catalog_reader=catalog,
        )

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is True
        assert reason is not None
        assert "2024-12-27" in reason
        assert "abcdef12" in reason  # checksum 前 8 个字符
        assert "1000" in reason  # 行数

    def test_success_without_checksum_is_retried_for_authoritative_evidence(
        self, mock_ingestion_log_store
    ) -> None:
        """A success row without a checksum cannot prove a persisted snapshot."""
        # Mock get_log 返回成功但无 checksum 的历史记录
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum=None,
            rows=1000,
        )
        manager = MetadataManager(mock_ingestion_log_store)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None
