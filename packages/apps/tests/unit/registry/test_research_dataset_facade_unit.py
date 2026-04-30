"""Tests for research dataset snapshot building."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import orjson
import polars as pl
import pytest
from dishka import Provider, Scope, make_container, provide
from ditto_analysis.research.domain import DatasetSnapshot, KnownAtPolicy
from ditto_application.query.research import ResearchDatasetFacade
from ditto_apps.registry import ConfigProvider
from ditto_data.di import (
    CapitalProvider,
    DerivedProvider,
    FundamentalProvider,
    MacroProvider,
    MarketProvider,
    MetadataProvider,
    RuntimeProvider,
    TradeProvider,
)
from ditto_data.models.derived import DerivedSpecRecord, DerivedVersionRecord
from ditto_data.services import DerivedCatalogService, ResearchCatalogService
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_features.materialization.models import DerivedVersionStatus
from ditto_kernel.research import (
    ResearchDatasetSpecRecord,
    ResearchSpineSpecRecord,
)
from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile

# CapitalProvider is used in _make_container to satisfy MetadataService deps


def _sources_provider() -> Provider:
    class SourcesProvider(Provider):
        scope = Scope.APP

        @provide
        def data_sources(self) -> DataSources:
            return DataSources(tushare=MagicMock(), fred=None)

        @provide
        def exchange_transformers(self) -> ExchangeTransformers:
            return ExchangeTransformers(
                tushare=MagicMock(),
                tdx=MagicMock(),
            )

    return SourcesProvider()


def _make_container(*, monkeypatch, tmp_path: Path):
    from ditto_application.providers_market import AppMarketQueryProvider

    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
    return make_container(
        ConfigProvider(),
        _sources_provider(),
        RuntimeProvider(),
        MetadataProvider(),
        MarketProvider(),
        CapitalProvider(),
        DerivedProvider(),
        FundamentalProvider(),
        MacroProvider(),
        TradeProvider(),
        AppMarketQueryProvider(),
    )


def _seed_calendar(sqlite_client: SQLiteClient, dates: list[date]) -> None:
    rows = []
    for idx, trade_date in enumerate(dates):
        prev_trade_date = dates[idx - 1].isoformat() if idx > 0 else None
        next_trade_date = dates[idx + 1].isoformat() if idx + 1 < len(dates) else None
        rows.append(
            (
                trade_date.isoformat(),
                1,
                prev_trade_date,
                next_trade_date,
                11,
                trade_date.month,
                1,
                trade_date.year,
                0,
                0,
                0,
            )
        )
    sqlite_client.executemany(
        """
        INSERT INTO trading_calendar (
            trade_date, is_open, prev_trade_date, next_trade_date,
            week_of_year, month, quarter, year,
            is_week_end, is_month_end, is_quarter_end
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    sqlite_client.commit()


def _seed_universe(sqlite_client: SQLiteClient) -> None:
    sqlite_client.execute(
        """
        INSERT INTO instrument (
            instrument_id, ticker, name, display_name, exchange,
            board, asset_class, list_date, delist_date,
            is_st, is_active, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "000001",
            "Ping An Bank",
            "Ping An Bank",
            "SZSE",
            "main",
            "stock",
            "2020-01-01",
            None,
            0,
            1,
            None,
        ),
    )
    sqlite_client.execute(
        """
        INSERT INTO universe (
            universe_id, name, description, universe_type, source_ref
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("universe.cn.all", "CN All", None, "custom", None),
    )
    sqlite_client.executemany(
        """
        INSERT INTO universe_constituent (
            universe_id, instrument_id, effective_from, effective_to,
            weight, source, source_ticker
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("universe.cn.all", 1, "2026-01-01", None, 1.0, "test", "000001.SZ"),
        ],
    )
    sqlite_client.commit()


def _seed_derived_spec(
    catalog_service: DerivedCatalogService,
    *,
    derived_id: str,
    version: int,
    is_online: bool,
    is_primary: bool,
) -> None:
    spec = DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=MaterializationProfile.SERIES,
        expression="market.close",
    )
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=derived_id,
            version=version,
            role=spec.role.value,
            materialization_profile=spec.materialization_profile.value,
            spec_hash=f"hash:{derived_id}:v{version}",
            spec_json=asdict(spec),
            created_at="2026-03-14T12:00:00+08:00",
        )
    )
    catalog_service.save_version(
        DerivedVersionRecord(
            derived_id=derived_id,
            version=version,
            status=(
                DerivedVersionStatus.PUBLISHED
                if is_primary
                else DerivedVersionStatus.MATERIALIZED
            ),
            engine_version="expr-v1",
            is_online=is_online,
            is_primary=is_primary,
            created_at="2026-03-14T12:00:00+08:00",
            updated_at=None,
        )
    )


def _write_artifact(
    data_root: Path,
    *,
    derived_id: str,
    version: int,
    rows: list[dict[str, object]],
    input_snapshots: tuple[str, ...] = (),
) -> None:
    version_root = (
        data_root / "derived" / "artifacts" / "series" / derived_id / f"v{version}"
    )
    version_root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(version_root / "2026.parquet")
    if input_snapshots:
        metadata_dir = version_root / "_runs" / f"run-{derived_id.replace('.', '-')}"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.joinpath("artifact_metadata.json").write_bytes(
            orjson.dumps(
                {
                    "input_snapshots": list(input_snapshots),
                },
                option=orjson.OPT_INDENT_2,
            )
        )


class TestResearchDatasetFacade:
    """Tests for ResearchDatasetFacade."""

    def test_build_creates_snapshot_with_left_preserving_pit_join(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        """Research build should freeze primary versions and preserve left rows."""
        container = _make_container(monkeypatch=monkeypatch, tmp_path=tmp_path)

        try:
            sqlite_client = container.get(SQLiteClient)
            _seed_calendar(sqlite_client, [date(2026, 3, 10), date(2026, 3, 11)])
            _seed_universe(sqlite_client)

            derived_catalog = container.get(DerivedCatalogService)
            research_catalog = container.get(ResearchCatalogService)
            facade = container.get(ResearchDatasetFacade)

            _seed_derived_spec(
                derived_catalog,
                derived_id="factor.alpha",
                version=2,
                is_online=True,
                is_primary=True,
            )
            _seed_derived_spec(
                derived_catalog,
                derived_id="factor.beta",
                version=1,
                is_online=True,
                is_primary=True,
            )
            _write_artifact(
                tmp_path,
                derived_id="factor.alpha",
                version=2,
                rows=[
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 10),
                        "value": 10.0,
                        "availability_time": date(2026, 3, 11),
                    },
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 11),
                        "value": 20.0,
                        "availability_time": date(2026, 3, 11),
                    },
                ],
            )
            _write_artifact(
                tmp_path,
                derived_id="factor.beta",
                version=1,
                rows=[
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 10),
                        "value": 100.0,
                    },
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 11),
                        "value": 200.0,
                    },
                ],
            )
            research_catalog.save_spine_spec(
                ResearchSpineSpecRecord(
                    spine_id="spine.cn_stock.default",
                    universe_id="universe.cn.all",
                    calendar="cn_stock",
                    grain="1d",
                    entity_key="instrument_id",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )
            research_catalog.save_dataset_spec(
                ResearchDatasetSpecRecord(
                    dataset_id="research.alpha_beta",
                    spine_id="spine.cn_stock.default",
                    derived_ids=("factor.alpha", "factor.beta"),
                    join_policy="left_preserving_pit",
                    known_at_policy="sample_time",
                    late_arrival_policy="require_rebuild",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )

            snapshot = facade.build(
                dataset_id="research.alpha_beta",
                start="2026-03-10",
                end="2026-03-11",
            )

            snapshot_record = research_catalog.get_dataset_snapshot(
                snapshot.snapshot_id
            )
            assert snapshot_record is not None
            assert snapshot.dataset_spec_version == 1
            assert snapshot.builder_version == "unified-derived-research-v1"
            assert snapshot_record.resolved_versions == {
                "factor.alpha": 2,
                "factor.beta": 1,
            }
            assert snapshot_record.dataset_spec_version == 1
            assert snapshot_record.resolved_inputs == (
                {
                    "derived_id": "factor.alpha",
                    "version": 2,
                    "artifact_path": "derived/artifacts/series/factor.alpha/v2",
                },
                {
                    "derived_id": "factor.beta",
                    "version": 1,
                    "artifact_path": "derived/artifacts/series/factor.beta/v1",
                },
            )
            assert snapshot_record.manifest_hash

            frame = pl.read_parquet(tmp_path / snapshot.data_path)
            assert frame.to_dicts() == [
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 10),
                    "known_at": date(2026, 3, 10),
                    "factor.alpha": None,
                    "factor.beta": 100.0,
                },
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 11),
                    "known_at": date(2026, 3, 11),
                    "factor.alpha": 20.0,
                    "factor.beta": 200.0,
                },
            ]
        finally:
            container.close()

    def test_build_respects_explicit_version_overrides(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        """Build requests should be able to freeze non-primary explicit versions."""
        container = _make_container(monkeypatch=monkeypatch, tmp_path=tmp_path)

        try:
            sqlite_client = container.get(SQLiteClient)
            _seed_calendar(sqlite_client, [date(2026, 3, 11)])
            _seed_universe(sqlite_client)

            derived_catalog = container.get(DerivedCatalogService)
            research_catalog = container.get(ResearchCatalogService)
            facade = container.get(ResearchDatasetFacade)

            _seed_derived_spec(
                derived_catalog,
                derived_id="factor.alpha",
                version=2,
                is_online=True,
                is_primary=True,
            )
            _seed_derived_spec(
                derived_catalog,
                derived_id="factor.alpha",
                version=3,
                is_online=False,
                is_primary=False,
            )
            _write_artifact(
                tmp_path,
                derived_id="factor.alpha",
                version=2,
                rows=[
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 11),
                        "value": 20.0,
                    },
                ],
            )
            _write_artifact(
                tmp_path,
                derived_id="factor.alpha",
                version=3,
                rows=[
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 11),
                        "value": 30.0,
                    },
                ],
            )
            research_catalog.save_spine_spec(
                ResearchSpineSpecRecord(
                    spine_id="spine.cn_stock.default",
                    universe_id="universe.cn.all",
                    calendar="cn_stock",
                    grain="1d",
                    entity_key="instrument_id",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )
            research_catalog.save_dataset_spec(
                ResearchDatasetSpecRecord(
                    dataset_id="research.alpha_override",
                    spine_id="spine.cn_stock.default",
                    derived_ids=("factor.alpha",),
                    join_policy="left_preserving_pit",
                    known_at_policy="sample_time",
                    late_arrival_policy="require_rebuild",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )

            snapshot = facade.build(
                dataset_id="research.alpha_override",
                start="2026-03-11",
                end="2026-03-11",
                version_overrides={"factor.alpha": 3},
                explicit_cutoff="2026-03-11",
            )

            record = research_catalog.get_dataset_snapshot(snapshot.snapshot_id)
            assert record is not None
            assert record.known_at_policy == "explicit_cutoff"
            assert record.effective_cutoff == "2026-03-11"
            assert record.resolved_versions == {"factor.alpha": 3}
            assert snapshot.effective_cutoff == "2026-03-11"

            frame = pl.read_parquet(tmp_path / snapshot.data_path)
            assert frame["factor.alpha"].to_list() == [30.0]
            assert frame["known_at"].to_list() == [date(2026, 3, 11)]
        finally:
            container.close()

    def test_build_persists_effective_cutoff_and_source_snapshot_ids(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        """Builds should freeze effective cutoff and aggregated source snapshots."""
        container = _make_container(monkeypatch=monkeypatch, tmp_path=tmp_path)

        try:
            sqlite_client = container.get(SQLiteClient)
            _seed_calendar(sqlite_client, [date(2026, 3, 11)])
            _seed_universe(sqlite_client)

            derived_catalog = container.get(DerivedCatalogService)
            research_catalog = container.get(ResearchCatalogService)
            facade = container.get(ResearchDatasetFacade)

            _seed_derived_spec(
                derived_catalog,
                derived_id="factor.alpha",
                version=2,
                is_online=True,
                is_primary=True,
            )
            _seed_derived_spec(
                derived_catalog,
                derived_id="factor.beta",
                version=1,
                is_online=True,
                is_primary=True,
            )
            _write_artifact(
                tmp_path,
                derived_id="factor.alpha",
                version=2,
                rows=[
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 11),
                        "value": 20.0,
                    },
                ],
                input_snapshots=("market:20260311-001",),
            )
            _write_artifact(
                tmp_path,
                derived_id="factor.beta",
                version=1,
                rows=[
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 11),
                        "value": 200.0,
                    },
                ],
                input_snapshots=("market:20260310-001", "market:20260311-001"),
            )
            research_catalog.save_spine_spec(
                ResearchSpineSpecRecord(
                    spine_id="spine.cn_stock.default",
                    universe_id="universe.cn.all",
                    calendar="cn_stock",
                    grain="1d",
                    entity_key="instrument_id",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )
            research_catalog.save_dataset_spec(
                ResearchDatasetSpecRecord(
                    dataset_id="research.alpha_beta_cutoff",
                    spine_id="spine.cn_stock.default",
                    derived_ids=("factor.alpha", "factor.beta"),
                    join_policy="left_preserving_pit",
                    known_at_policy="sample_time",
                    late_arrival_policy="require_rebuild",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )

            snapshot = facade.build(
                dataset_id="research.alpha_beta_cutoff",
                start="2026-03-11",
                end="2026-03-11",
                explicit_cutoff="2026-03-11",
            )

            record = research_catalog.get_dataset_snapshot(snapshot.snapshot_id)
            assert record is not None
            assert record.effective_cutoff == "2026-03-11"
            assert record.source_snapshot_ids == (
                "market:20260310-001",
                "market:20260311-001",
            )
            assert snapshot.source_snapshot_ids == (
                "market:20260310-001",
                "market:20260311-001",
            )
        finally:
            container.close()

    def test_build_writes_and_loads_build_report(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        """Build should persist a reusable build report next to the snapshot."""
        container = _make_container(monkeypatch=monkeypatch, tmp_path=tmp_path)

        try:
            sqlite_client = container.get(SQLiteClient)
            _seed_calendar(sqlite_client, [date(2026, 3, 10), date(2026, 3, 11)])
            _seed_universe(sqlite_client)

            derived_catalog = container.get(DerivedCatalogService)
            research_catalog = container.get(ResearchCatalogService)
            facade = container.get(ResearchDatasetFacade)

            _seed_derived_spec(
                derived_catalog,
                derived_id="factor.alpha",
                version=2,
                is_online=True,
                is_primary=True,
            )
            _write_artifact(
                tmp_path,
                derived_id="factor.alpha",
                version=2,
                rows=[
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 10),
                        "value": 10.0,
                        "availability_time": date(2026, 3, 11),
                    },
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 11),
                        "value": 20.0,
                        "availability_time": date(2026, 3, 11),
                    },
                ],
                input_snapshots=("market:20260311-001",),
            )
            research_catalog.save_spine_spec(
                ResearchSpineSpecRecord(
                    spine_id="spine.cn_stock.default",
                    universe_id="universe.cn.all",
                    calendar="cn_stock",
                    grain="1d",
                    entity_key="instrument_id",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )
            research_catalog.save_dataset_spec(
                ResearchDatasetSpecRecord(
                    dataset_id="research.alpha_report",
                    spine_id="spine.cn_stock.default",
                    derived_ids=("factor.alpha",),
                    join_policy="left_preserving_pit",
                    known_at_policy="sample_time",
                    late_arrival_policy="require_rebuild",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )

            snapshot = facade.build(
                dataset_id="research.alpha_report",
                start="2026-03-10",
                end="2026-03-11",
            )

            report = facade.load_build_report(snapshot)

            assert report == {
                "row_count": 2,
                "spine_row_count": 2,
                "null_counts": {"factor.alpha": 1},
                "resolved_versions": {"factor.alpha": 2},
                "known_at_policy": "sample_time",
                "effective_cutoff": None,
                "source_snapshot_ids": ["market:20260311-001"],
                "builder_version": "unified-derived-research-v1",
            }
            report_path = tmp_path / snapshot.data_path
            assert report_path.parent.joinpath("build_report.json").exists() is True
        finally:
            container.close()


class TestResearchDatasetFacadeExport:
    """Tests for ResearchDatasetFacade.export()."""

    def _make_facade(self) -> tuple[ResearchDatasetFacade, MagicMock]:
        """创建带 mock 的 facade 实例."""
        artifact_service = MagicMock()
        facade = ResearchDatasetFacade(
            metadata_service=MagicMock(),
            research_catalog_service=MagicMock(),
            artifact_reader=MagicMock(),
            research_artifact_service=artifact_service,
        )
        return facade, artifact_service

    def _make_snapshot(
        self,
        *,
        dataset_id: str = "research-test-dataset",
        data_path: str = (
            "derived/research/datasets/research-test-dataset"
            "/snapshots/abc123/data.parquet"
        ),
    ) -> DatasetSnapshot:
        """创建测试用 DatasetSnapshot."""
        return DatasetSnapshot(
            snapshot_id="rds-abc123",
            dataset_id=dataset_id,
            dataset_spec_version=1,
            spine_snapshot_id="rsp-xyz",
            start="2026-03-10",
            end="2026-03-11",
            row_count=2,
            data_path=data_path,
            manifest_hash="hash123",
            known_at_policy=KnownAtPolicy.SAMPLE_TIME,
            effective_cutoff=None,
        )

    def test_export_csv(self, tmp_path: Path) -> None:
        """export() 应该能导出为 CSV 格式."""
        facade, artifact_service = self._make_facade()
        snapshot = self._make_snapshot()
        test_df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "value": [10.0, 20.0],
            }
        )
        artifact_service.read_parquet.return_value = test_df

        csv_path = tmp_path / "output.csv"
        facade.export(snapshot, "csv", csv_path)

        artifact_service.read_parquet.assert_called_once_with(snapshot.data_path)
        assert csv_path.exists()
        result_df = pl.read_csv(csv_path)
        assert result_df.shape == (2, 3)
        assert result_df["instrument_id"].to_list() == [1, 2]

    def test_export_csv_with_hyphens_in_dataset_id(self, tmp_path: Path) -> None:
        """CSV 导出应该正常处理含连字符的 dataset_id."""
        facade, artifact_service = self._make_facade()
        snapshot = self._make_snapshot(dataset_id="my-research-dataset")
        artifact_service.read_parquet.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "value": [100.0],
            }
        )

        csv_path = tmp_path / "output.csv"
        facade.export(snapshot, "csv", csv_path)
        assert csv_path.exists()

    def test_export_sqlite(self, tmp_path: Path) -> None:
        """export() 应该能导出为 SQLite 格式."""
        import sqlite3 as _sqlite3

        facade, artifact_service = self._make_facade()
        snapshot = self._make_snapshot(dataset_id="research-alpha")
        test_df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "factor_alpha": [0.5, 0.8],
            }
        )
        artifact_service.read_parquet.return_value = test_df

        db_path = tmp_path / "output.db"
        facade.export(snapshot, "sqlite", db_path)

        artifact_service.read_parquet.assert_called_once_with(snapshot.data_path)
        assert db_path.exists()
        conn = _sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT * FROM research_alpha ORDER BY instrument_id"
        ).fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[0][0] == 1
        assert rows[0][2] == 0.5
        assert rows[1][0] == 2
        assert rows[1][2] == 0.8

    def test_export_sqlite_table_name_from_dataset_id(self, tmp_path: Path) -> None:
        """SQLite 导出应该将 dataset_id 中的连字符替换为下划线作为表名."""
        import sqlite3 as _sqlite3

        facade, artifact_service = self._make_facade()
        snapshot = self._make_snapshot(dataset_id="my-test-dataset")
        artifact_service.read_parquet.return_value = pl.DataFrame(
            {
                "col_a": [1],
            }
        )

        db_path = tmp_path / "output.db"
        facade.export(snapshot, "sqlite", db_path)

        conn = _sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert ("my_test_dataset",) in tables

    def test_export_sqlite_empty_dataframe(self, tmp_path: Path) -> None:
        """SQLite 导出空 DataFrame 应该不创建表."""
        import sqlite3 as _sqlite3

        facade, artifact_service = self._make_facade()
        snapshot = self._make_snapshot()
        artifact_service.read_parquet.return_value = pl.DataFrame(
            schema={
                "instrument_id": pl.Int64,
                "value": pl.Float64,
            },
        )

        db_path = tmp_path / "output.db"
        facade.export(snapshot, "sqlite", db_path)

        conn = _sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert len(tables) == 0

    def test_export_unsupported_format(self, tmp_path: Path) -> None:
        """export() 应该对不支持的格式抛出 ValueError."""
        facade, _artifact_service = self._make_facade()
        snapshot = self._make_snapshot()

        with pytest.raises(ValueError, match="不支持的导出格式"):
            facade.export(snapshot, "xlsx", tmp_path / "output.xlsx")
