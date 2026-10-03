"""#395 ETF/index 扩展与 etf_reference_observation 生产写侧集成测试。

实际摄取调用链（IngestionDataWriter.write_data("etf_basic")）验证：
- instrument/instrument_mapping 注册（幂等）
- instrument_etf 扩展表接通
- etf_reference_observation 观察行（绑定确定性 source_snapshot_id）
- 读侧 find_etf_reference 能消费新事实（Paper 参考链路入口）
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.post_ingest import process_fetched_data
from ditto_data.models.ingestion import IngestionResult
from ditto_data.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_data.services.metadata_service import MetadataService
from ditto_data.storage.metadata.instrument import (
    EtfReferenceObservationWriter,
    InstrumentReader,
    InstrumentWriter,
    NameHistoryReader,
    NameHistoryWriter,
)
from ditto_platform.foundation import DataCache, SQLiteClient, SQLitePool
from packages.application.tests.integration.test_ingestion_evidence_recovery import (
    _pipeline,
)


@pytest.mark.integration
class TestEtfReferenceWriteSideIntegration:
    """etf_basic 摄取 → 扩展表 + 参考观察行。"""

    @pytest.fixture
    def pool(self, tmp_path: Path) -> SQLitePool:
        schema_path = (
            Path(__file__).parents[3]
            / "data"
            / "src"
            / "ditto_data"
            / "scripts"
            / "schema.sql"
        )
        pool = SQLitePool(":memory:", schema_path=schema_path)
        pool.init_schema()
        return pool

    @pytest.fixture
    def client(self, pool: SQLitePool) -> SQLiteClient:
        return SQLiteClient(pool)

    @pytest.fixture
    def metadata(self, client: SQLiteClient, pool: SQLitePool) -> MetadataService:
        cache: DataCache[Any] = DataCache[Any](ttl_seconds=60, max_size=100)
        return MetadataService(
            instrument_reader=InstrumentReader(client),
            instrument_writer=InstrumentWriter(client, cache),
            name_history_reader=NameHistoryReader(client, cache),
            name_history_writer=NameHistoryWriter(client, cache),
            calendar_reader=MagicMock(),
            calendar_writer=MagicMock(),
            industry_reader=MagicMock(),
            industry_writer=MagicMock(),
            industry_mapping_reader=MagicMock(),
            industry_mapping_writer=MagicMock(),
            universe_reader=MagicMock(),
            universe_writer=MagicMock(),
            rebalance_reader=MagicMock(),
            rebalance_writer=MagicMock(),
            instrument_id_allocator=InstrumentIdAllocator(pool),
            index_composition_reader=MagicMock(),
            exchange_transformers=MagicMock(),
            etf_reference_writer=EtfReferenceObservationWriter(client, cache),
        )

    @pytest.fixture
    def writer(self, metadata: MetadataService) -> IngestionDataWriter:
        return IngestionDataWriter(
            metadata_service=metadata,
            market_write_service=None,  # type: ignore[arg-type] — etf_basic 不触发行情写
            fundamental_store=None,  # type: ignore[arg-type] — 未用写侧
            capital_store=None,  # type: ignore[arg-type] — 未用写侧
            macro_service=None,  # type: ignore[arg-type] — 未用写侧
            source_name="tushare",
        )

    @pytest.fixture
    def ingest(
        self, writer: IngestionDataWriter, client: SQLiteClient, tmp_path: Path
    ) -> Iterator[Callable[[], IngestionResult]]:
        with _pipeline(tmp_path, "etf_basic") as pipeline:
            frame = self._etf_basic_frame().with_columns(pl.lit(1.0).alias("close"))
            ctx = replace(
                pipeline.context,
                data_writer=writer,
                snapshot_reader=pipeline.ports.snapshot_reader,
                list_date_inference=MagicMock(),
            )

            def run() -> IngestionResult:
                result = process_fetched_data(
                    frame, "etf_basic", "2026-09-18", True, ctx=ctx
                )
                assert result.status == "success", result
                rows = client.fetchall(
                    "SELECT DISTINCT source_snapshot_id FROM etf_reference_observation"
                )
                for row in rows:
                    snapshot = pipeline.ports.snapshot_reader.get_snapshot(
                        str(row["source_snapshot_id"])
                    )
                    assert snapshot is not None
                    assert snapshot.payload_retained
                    assert snapshot.checksum != result.checksum
                return result

            yield run

    @staticmethod
    def _etf_basic_frame() -> pl.DataFrame:
        return pl.DataFrame(
            {
                "source_ticker": ["510300.SH", "159915.SZ"],
                "ticker": ["510300", "159915"],
                "name": ["沪深300ETF", "创业板ETF"],
                "exchange": ["SSE", "SZSE"],
                "list_date": [date(2012, 5, 28), date(2011, 12, 9)],
            }
        )

    def test_etf_basic_ingestion_registers_extension_and_observations(
        self, ingest: Callable[[], IngestionResult], client: SQLiteClient
    ) -> None:
        """一次 etf_basic 摄取：注册 + instrument_etf 行 + 参考观察行。"""
        result = ingest()

        assert result.row_count == 2

        # instrument 主表 + ETF 扩展表接通
        instruments = client.fetchall(
            "SELECT instrument_id, ticker FROM instrument WHERE asset_class = 'etf'"
        )
        assert instruments is not None
        assert len(instruments) == 2
        etf_rows = client.fetchall("SELECT instrument_id FROM instrument_etf")
        assert etf_rows is not None
        assert len(etf_rows) == 2

        # 参考观察行：2 标的 × (name/exchange/list_date) = 6 行，
        # 均带确定性 snapshot 身份
        observations = client.fetchall(
            """SELECT instrument_id, field, value, unit, observed_on, published_at,
                      effective_from, source, source_snapshot_id
            FROM etf_reference_observation ORDER BY instrument_id, field"""
        )
        assert observations is not None
        assert len(observations) == 6
        fields = {(row["instrument_id"], row["field"]) for row in observations}
        assert all(
            (row["instrument_id"], expected) in fields
            for row in instruments
            for expected in ("name", "exchange", "list_date")
        )
        for row in observations:
            assert row["observed_on"] == "2026-09-18"
            assert row["source"] == "tushare"
            # CHECK 约束：published_at 必须是 ISO Z 时刻
            assert row["published_at"].endswith("Z")
            assert row["source_snapshot_id"].startswith("snapshot:tushare:etf_basic:")

    def test_etf_basic_reregistration_is_idempotent(
        self, ingest: Callable[[], IngestionResult], client: SQLiteClient
    ) -> None:
        """重复摄取同帧：注册幂等（跳过），观察行整行替换不膨胀。"""
        ingest()
        first = client.fetchall(
            "SELECT * FROM etf_reference_observation ORDER BY instrument_id, field"
        )
        ingest()
        assert (
            client.fetchall(
                "SELECT * FROM etf_reference_observation ORDER BY instrument_id, field"
            )
            == first
        )

        instruments = client.fetchall(
            "SELECT instrument_id FROM instrument WHERE asset_class = 'etf'"
        )
        assert instruments is not None
        assert len(instruments) == 2
        observations = client.fetchall(
            "SELECT COUNT(*) AS n FROM etf_reference_observation"
        )
        assert observations is not None
        assert observations[0]["n"] == 6  # 同 snapshot 身份整行替换

    def test_find_etf_reference_consumes_new_observations(
        self, ingest: Callable[[], IngestionResult], metadata: MetadataService
    ) -> None:
        """Paper 读侧入口（find_etf_reference）能消费新观察事实。"""
        ingest()

        snapshots = metadata.instrument.list_etf_reference_snapshots(
            cutoff="2999-01-01T00:00:00Z"
        )
        assert snapshots, "观察行绑定的快照身份可被发现"
        instruments, observations = metadata.instrument.find_etf_reference(
            asof="2026-09-20",
            cutoff="2999-01-01T00:00:00Z",
            source_snapshot_id=snapshots[0],
            observed_since="2000-01-01",
        )
        assert len(instruments) == 2
        assert len(observations) == 6
        names = {
            row["instrument_id"]: row["value"]
            for row in observations
            if row["field"] == "name"
        }
        assert "沪深300ETF" in names.values()
        assert "创业板ETF" in names.values()

    def test_etf_candidate_query_consumes_new_observations(
        self, ingest: Callable[[], IngestionResult], metadata: MetadataService
    ) -> None:
        """Paper 候选查询（ETFCandidateQuery）消费新观察事实生成候选。"""
        from ditto_application.queries.etf_candidates import ETFCandidateQuery

        ingest()

        query = ETFCandidateQuery(metadata=metadata)
        snapshots = query.snapshots(cutoff="2999-01-01T00:00:00Z")
        assert snapshots, "ETFCandidateQuery 可发现新写入的参考快照"

        candidates = query.list_candidates(
            asof="2026-09-20",
            cutoff="2999-01-01T00:00:00Z",
            source_snapshot_id=snapshots[0],
        )
        tickers = {candidate.ticker for candidate in candidates}
        assert {"510300", "159915"} <= tickers
        names = {candidate.ticker: candidate.name for candidate in candidates}
        assert names["510300"] == "沪深300ETF"
        assert names["159915"] == "创业板ETF"
