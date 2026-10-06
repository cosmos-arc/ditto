"""ServiceBackedDataProvider 单元测试."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.builders.data_provider import ServiceBackedDataProvider
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
)
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleEvent,
    PartitionLifecycleStatus,
)
from ditto_data.provider import BarQuery, InstrumentQuery


def _make_mock_service(name: str) -> MagicMock:
    """创建 mock service."""
    return MagicMock(name=name)


def _snapshot(
    *,
    snapshot_id: str,
    request_start: str,
    request_end: str,
    observed_at: datetime,
    dataset: str = "etf_daily",
    namespace: str = "market",
    source_ticker: str | None = None,
) -> ProviderSnapshot:
    """数据集级 canonical 资产的 provider snapshot(可选标的元数据)。"""
    metadata = (("snapshot_layer", "normalized_provider_payload"),)
    if source_ticker is not None:
        metadata = (*metadata, ("source_ticker", source_ticker))
    return ProviderSnapshot(
        snapshot_id=snapshot_id,
        dataset_id=dataset,
        source="tushare",
        request_start=request_start,
        request_end=request_end,
        schema_version="etf.daily.v1",
        checksum="0" * 32,
        canonical_asset=DataAssetRef(dataset_id=dataset, namespace=namespace),
        request_parameters_hash="sha256:test",
        response_metadata=tuple(sorted(metadata)),
        row_count=1,
        payload_uri="provider_payloads/tushare/etf_daily/x.parquet",
        payload_retained=True,
        created_at=observed_at,
        observations=(observed_at,),
    )


class _SnapshotReader:
    """按数据集级 canonical 资产过滤的快照读端口 double。"""

    def __init__(self, *snapshots: ProviderSnapshot) -> None:
        self._snapshots = snapshots
        self.calls: list[DataAssetRef] = []

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        for snapshot in self._snapshots:
            if snapshot.snapshot_id == snapshot_id:
                return snapshot
        return None

    def get_observed_at(self, snapshot_id: str) -> datetime | None:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            return None
        return min(snapshot.observations) if snapshot.observations else None

    def get_predecessor(self, snapshot_id: str) -> str | None:
        return None

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        if canonical_asset is not None:
            self.calls.append(canonical_asset)
        return tuple(
            snapshot
            for snapshot in self._snapshots
            if canonical_asset is None or snapshot.canonical_asset == canonical_asset
        )


class _LifecycleReader:
    def __init__(self, reader: _SnapshotReader) -> None:
        self.reader = reader

    def get_latest_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return None

    def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return None

    def list_incomplete(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
    ) -> tuple[PartitionCheckpoint, ...]:
        return ()

    def list_complete(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
    ) -> tuple[PartitionCheckpoint, ...]:
        return tuple(
            PartitionCheckpoint(
                chunk_id=snapshot.snapshot_id,
                dataset_id=snapshot.dataset_id,
                source=snapshot.source,
                request_start=snapshot.request_start,
                request_end=snapshot.request_end,
                status=PartitionLifecycleStatus.COMPLETE,
                payload_id=f"payload:{snapshot.checksum}:test:{snapshot.snapshot_id}",
                complete_evidence_id=snapshot.snapshot_id,
                error_code=None,
                updated_at=snapshot.created_at,
            )
            for snapshot in self.reader._snapshots
            if dataset_id is None or snapshot.dataset_id == dataset_id
        )

    def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
        return ()


class TestServiceBackedDataProvider:
    """ServiceBackedDataProvider 测试."""

    def _make_provider(self) -> tuple[ServiceBackedDataProvider, dict[str, MagicMock]]:
        """创建 provider + mock services."""
        market = _make_mock_service("market")
        metadata = _make_mock_service("metadata")
        derived = _make_mock_service("derived")

        provider = ServiceBackedDataProvider(
            market_service=market,
            metadata_service=metadata,
            derived_service=derived,
        )
        return provider, {"market": market, "metadata": metadata, "derived": derived}

    # --- get_bars ---

    def test_get_bars_resolves_tickers(self) -> None:
        """get_bars 应先 resolve ticker -> instrument_id."""
        provider, mocks = self._make_provider()

        # ticker -> id 映射
        mocks["metadata"].instrument.resolve_instrument_ids_batch.return_value = {
            "000001.SZ": 1,
            "600000.SH": 2,
        }
        # bars 数据
        expected_df = pl.DataFrame({"instrument_id": [1, 2], "close": [10.0, 20.0]})
        mocks["market"].find_bars.return_value = expected_df

        query = BarQuery(
            instruments=["000001.SZ", "600000.SH"],
            start="2024-01-01",
            end="2024-12-31",
        )
        result = provider.get_bars(query)

        assert result.equals(expected_df)
        mocks[
            "metadata"
        ].instrument.resolve_instrument_ids_batch.assert_called_once_with(
            identifiers=["000001.SZ", "600000.SH"],
            source="tushare",
            asof=None,
        )

    def test_get_bars_empty_ticker_mapping(self) -> None:
        """get_bars 在无 ticker 映射时应返回空 DataFrame."""
        provider, mocks = self._make_provider()

        mocks["metadata"].instrument.resolve_instrument_ids_batch.return_value = {}

        query = BarQuery(
            instruments=["INVALID.XX"],
            start="2024-01-01",
            end="2024-12-31",
        )
        result = provider.get_bars(query)

        assert result.is_empty()
        mocks["market"].find_bars.assert_not_called()

    def test_get_bars_with_adj(self) -> None:
        """get_bars 应正确传递复权参数."""
        provider, mocks = self._make_provider()

        mocks["metadata"].instrument.resolve_instrument_ids_batch.return_value = {
            "000001.SZ": 1,
        }
        mocks["market"].find_bars.return_value = pl.DataFrame()

        query = BarQuery(
            instruments=["000001.SZ"],
            start="2024-01-01",
            end="2024-12-31",
            adj="hfq",
        )
        provider.get_bars(query)

        # 验证 find_bars 被调用时包含正确的 adj 参数
        call_args = mocks["market"].find_bars.call_args
        bars_query = call_args[0][0]
        assert bars_query.adj.value == "hfq"

    def test_get_bars_partial_ticker_resolution(self) -> None:
        """get_bars 只解析到部分 ticker 时应只查询已解析的."""
        provider, mocks = self._make_provider()

        mocks["metadata"].instrument.resolve_instrument_ids_batch.return_value = {
            "000001.SZ": 1,
            # 600000.SH 未解析到
        }
        mocks["market"].find_bars.return_value = pl.DataFrame(
            {"instrument_id": [1], "close": [10.0]}
        )

        query = BarQuery(
            instruments=["000001.SZ", "600000.SH"],
            start="2024-01-01",
            end="2024-12-31",
        )
        provider.get_bars(query)

        call_args = mocks["market"].find_bars.call_args
        bars_query = call_args[0][0]
        assert bars_query.instrument_ids == [1]

    def test_get_bars_attaches_latest_observed_covering_snapshot(self) -> None:
        """覆盖该行日期的最新观察快照赢得行级 lineage。"""
        market = _make_mock_service("market")
        metadata = _make_mock_service("metadata")
        derived = _make_mock_service("derived")
        reader = _SnapshotReader(
            _snapshot(
                snapshot_id="snapshot-old",
                request_start="2022-10-01",
                request_end="2024-03-29",
                observed_at=datetime(2026, 9, 1, 10, tzinfo=UTC),
            ),
            _snapshot(
                snapshot_id="snapshot-current",
                request_start="2023-01-01",
                request_end="2024-03-29",
                observed_at=datetime(2026, 9, 1, 11, tzinfo=UTC),
            ),
            # 更晚观察但覆盖更窄区间的快照不覆盖 2024-01-02。
            _snapshot(
                snapshot_id="snapshot-recent-narrow",
                request_start="2024-03-01",
                request_end="2024-03-29",
                observed_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
            ),
        )
        metadata.instrument.resolve_instrument_ids_batch.return_value = {
            "518880.SH": 2_001_724,
        }
        market.find_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [2_001_724, 2_001_724],
                "trade_date": [date(2024, 1, 2), date(2024, 3, 29)],
                "source": ["tushare", "tushare"],
                "source_ticker": ["518880.SH", "518880.SH"],
                "close": [92.0, 98.0],
            }
        )
        provider = ServiceBackedDataProvider(
            market_service=market,
            metadata_service=metadata,
            derived_service=derived,
            snapshot_reader=reader,
            lifecycle_reader=_LifecycleReader(reader),
        )

        result = provider.get_bars(
            BarQuery(
                instruments=["518880.SH"],
                start="2024-01-01",
                end="2024-03-29",
                dataset_id="etf_daily",
            )
        )

        assert result["source_snapshot_id"].to_list() == [
            "snapshot-current",
            "snapshot-recent-narrow",
        ]
        assert reader.calls == [
            DataAssetRef(dataset_id="etf_daily", namespace="market")
        ]

    def test_get_bars_leaves_unresolved_source_snapshot_null(self) -> None:
        """The adapter preserves rows so the consuming PIT boundary can fail closed."""
        market = _make_mock_service("market")
        metadata = _make_mock_service("metadata")
        derived = _make_mock_service("derived")
        reader = _SnapshotReader()
        metadata.instrument.resolve_instrument_ids_batch.return_value = {
            "518880.SH": 2_001_724,
        }
        market.find_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [2_001_724],
                "trade_date": [date(2024, 1, 2)],
                "source": ["tushare"],
                "source_ticker": ["518880.SH"],
                "close": [92.0],
            }
        )
        provider = ServiceBackedDataProvider(
            market_service=market,
            metadata_service=metadata,
            derived_service=derived,
            snapshot_reader=reader,
            lifecycle_reader=_LifecycleReader(reader),
        )

        result = provider.get_bars(
            BarQuery(
                instruments=["518880.SH"],
                start="2024-01-01",
                end="2024-03-29",
            )
        )

        assert result["source_snapshot_id"].to_list() == [None]

    # --- get_instruments ---

    def test_get_instruments_with_asset_class(self) -> None:
        """get_instruments 应按 asset_class 过滤."""
        provider, mocks = self._make_provider()

        expected_df = pl.DataFrame(
            {"instrument_id": [1, 2], "asset_class": ["etf", "etf"]}
        )
        mocks["metadata"].find_securities.return_value = expected_df

        query = InstrumentQuery(asset_class="etf")
        result = provider.get_instruments(query)

        assert result.equals(expected_df)
        mocks["metadata"].find_securities.assert_called_once_with(
            None, asset_class="etf", exchange=None
        )

    def test_get_instruments_no_filter(self) -> None:
        """get_instruments 无过滤应返回全部."""
        provider, mocks = self._make_provider()

        expected_df = pl.DataFrame({"instrument_id": [1, 2]})
        mocks["metadata"].find_securities.return_value = expected_df

        query = InstrumentQuery()
        result = provider.get_instruments(query)

        assert result.equals(expected_df)
        mocks["metadata"].find_securities.assert_called_once_with(
            None, asset_class=None, exchange=None
        )

    def test_get_instruments_with_exchange(self) -> None:
        """get_instruments 应按 exchange 过滤."""
        provider, mocks = self._make_provider()

        expected_df = pl.DataFrame({"instrument_id": [1], "exchange": ["XSHE"]})
        mocks["metadata"].find_securities.return_value = expected_df

        query = InstrumentQuery(exchange="XSHE")
        result = provider.get_instruments(query)

        assert result.equals(expected_df)
        mocks["metadata"].find_securities.assert_called_once_with(
            None, asset_class=None, exchange="XSHE"
        )

    # --- get_schedule ---

    def test_get_schedule(self) -> None:
        """get_schedule 应返回交易日历."""
        provider, mocks = self._make_provider()

        expected = pl.DataFrame({"trade_date": ["2024-01-02", "2024-01-03"]})
        mocks["metadata"].calendar.list_calendar_range.return_value = expected

        result = provider.get_schedule("2024-01-01", "2024-01-31")

        assert result.equals(expected)
        mocks["metadata"].calendar.list_calendar_range.assert_called_once_with(
            "2024-01-01", "2024-01-31", only_open=True
        )

    # --- get_factor ---

    def test_get_factor(self) -> None:
        """get_factor 应委托给 DerivedQueryService."""
        provider, mocks = self._make_provider()

        mocks["metadata"].instrument.resolve_instrument_ids_batch.return_value = {
            "000001.SZ": 1,
        }
        expected = pl.DataFrame(
            {
                "derived_id": ["momentum_20d"],
                "instrument_id": [1],
                "trade_date": ["2024-01-02"],
                "value": [0.5],
            }
        )
        mocks["derived"].query_for_evaluation.return_value = expected

        result = provider.get_factor(
            name="momentum_20d",
            instruments=("000001.SZ",),
            start="2024-01-01",
            end="2024-12-31",
        )
        assert result.equals(expected)
        mocks["derived"].query_for_evaluation.assert_called_once_with(
            derived_ids=("momentum_20d",),
            instrument_ids=(1,),
            start="2024-01-01",
            end="2024-12-31",
        )

    def test_get_factor_empty_instruments(self) -> None:
        """get_factor 在无 ticker 映射时应返回空 DataFrame."""
        provider, mocks = self._make_provider()

        mocks["metadata"].instrument.resolve_instrument_ids_batch.return_value = {}

        result = provider.get_factor(
            name="momentum_20d",
            instruments=("INVALID.XX",),
            start="2024-01-01",
            end="2024-12-31",
        )

        assert result.is_empty()
        mocks["derived"].query_for_evaluation.assert_not_called()

    # --- Protocol 一致性 ---

    def test_satisfies_data_provider_protocol(self) -> None:
        """ServiceBackedDataProvider 应满足 DataProvider Protocol."""
        provider, _ = self._make_provider()
        # Protocol 一致性：结构检查
        assert hasattr(provider, "get_bars")
        assert hasattr(provider, "get_instruments")
        assert hasattr(provider, "get_schedule")
        assert hasattr(provider, "get_factor")


class TestVectorizedLineagePrecedence:
    """同日多窗口时按观察事件时序取最新。"""

    def test_fresher_observation_wins_for_same_date(self) -> None:
        market = _make_mock_service("market")
        metadata = _make_mock_service("metadata")
        derived = _make_mock_service("derived")
        reader = _SnapshotReader(
            _snapshot(
                snapshot_id="older-observation",
                request_start="2024-03-29",
                request_end="2024-03-29",
                observed_at=datetime(2026, 9, 1, 10, tzinfo=UTC),
            ),
            _snapshot(
                snapshot_id="newer-observation",
                request_start="2024-01-01",
                request_end="2024-03-29",
                observed_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
            ),
        )
        metadata.instrument.resolve_instrument_ids_batch.return_value = {
            "518880.SH": 2_001_724,
        }
        market.find_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [2_001_724],
                "trade_date": [date(2024, 3, 29)],
                "source": ["tushare"],
                "source_ticker": ["518880.SH"],
                "close": [98.0],
            }
        )
        provider = ServiceBackedDataProvider(
            market_service=market,
            metadata_service=metadata,
            derived_service=derived,
            snapshot_reader=reader,
            lifecycle_reader=_LifecycleReader(reader),
        )

        result = provider.get_bars(
            BarQuery(instruments=["518880.SH"], start="2024-03-01", end="2024-03-29")
        )

        assert result["source_snapshot_id"].to_list() == ["newer-observation"]


@pytest.mark.parametrize("registered", [True, False])
def test_uncompleted_revision_cannot_claim_canonical_bar_lineage(registered):
    from packages.application.tests.unit.process.ingestion import (
        snapshot_evidence_support,
    )

    evidence_stores = snapshot_evidence_support.evidence_stores
    commit_snapshot = snapshot_evidence_support.commit_snapshot

    with evidence_stores() as stores:
        for hour, complete in ((9, True), (10, False)):
            if hour == 10 and not registered:
                stores.lifecycle.plan_partition(
                    PartitionCheckpoint(
                        chunk_id="pending-revision",
                        dataset_id="stock_daily",
                        source="tushare",
                        request_start="2026-07-01",
                        request_end="2026-07-01",
                        status=PartitionLifecycleStatus.PLANNED,
                        payload_id="intent:10:unregistered",
                        complete_evidence_id=None,
                        error_code=None,
                        updated_at=datetime(2026, 7, 1, 10, tzinfo=UTC),
                    )
                )
                continue
            commit_snapshot(
                stores,
                dataset="stock_daily",
                request_start="2026-07-01",
                request_end="2026-07-01",
                checksum=str(hour),
                row_count=1,
                schema_version="market.stock_daily.v1",
                observed_at=datetime(2026, 7, 1, hour, tzinfo=UTC),
                complete=complete,
            )
        market = MagicMock()
        metadata = MagicMock()
        metadata.instrument.resolve_instrument_ids_batch.return_value = {"000001.SZ": 1}
        market.find_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 7, 1)],
                "source": ["tushare"],
                "source_ticker": ["000001.SZ"],
                "close": [99.0],
            }
        )
        provider = ServiceBackedDataProvider(
            market_service=market,
            metadata_service=metadata,
            derived_service=MagicMock(),
            snapshot_reader=stores.snapshots,
            lifecycle_reader=stores.lifecycle,
        )
        frame = provider.get_bars(
            BarQuery(
                instruments=["000001.SZ"],
                start="2026-07-01",
                end="2026-07-01",
                dataset_id="stock_daily",
            )
        )
        assert frame["source_snapshot_id"].to_list() == [None]
