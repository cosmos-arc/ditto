"""
Protocol adapters — bridge concrete infrastructure types to Protocol interfaces.

Composition root responsibility: concrete types live in data/platform/features DI;
application providers only depend on Protocol interfaces.  This module closes the
gap so Dishka can resolve Protocol-typed parameters without structural subtyping.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from collections.abc import Mapping as MappingABC
from contextlib import AbstractContextManager
from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

import polars as pl
from dishka import Provider, Scope, provide
from ditto_application.processes.experiments.r2_live_gate_evidence import (
    FileR2LiveGateEvidenceReader,
    NullR2LiveGateEvidenceReader,
    R2LiveGateEvidenceReader,
    R2LiveGateEvidenceSource,
)
from ditto_application.queries.source import SourceDataPort
from ditto_data.models.ingestion import IngestionResult
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.quality.protocols import (
    ComparisonStoreProtocol,
    FinancialReconcileContextProtocol,
    InstrumentStoreProtocol,
    SecondaryAdjustmentEventsSourceProtocol,
    SecondaryBarsSourceProtocol,
    SecondaryFinancialsSourceProtocol,
)
from ditto_data.services.deps import FundamentalReaders, MarketReaders
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata.instrument import InstrumentService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_accessor import SourceAccessor
from ditto_data.sources.base import SourceFetchError
from ditto_data.sources.fuyao.source import FuyaoDailyKDumpFetcher, FuyaoSource
from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.metadata.instrument import InstrumentReader
from ditto_data.storage.runtime.quality import ComparisonWriter

__all__ = [
    "FinancialReconcileContextProtocol",
    "FundamentalFinancialReconcileContext",
    "FuyaoDailyKDumpFetcher",
    "FuyaoSource",
    "IngestionResult",
    "InstrumentService",
    "MarketReaders",
    "MarketService",
    "MetadataService",
    "SourceFetchError",
    "latest_fuyao_dump",
]
from ditto_features.compile_cache import SQLiteCompileCacheBackend
from ditto_platform.foundation import SQLiteClient, logger

from ditto_apps.r2_live_evidence_source import load_r2_live_gate_source


def latest_fuyao_dump(data_root: Path, kind: str) -> Path | None:
    """Fuyao dumps 目录下指定 kind 的最新快照（YYYYMMDD 文件名字典序 = 时间序）."""
    dump_dir = Path(data_root) / "fuyao" / "dumps" / kind
    if not dump_dir.is_dir():
        return None
    dumps = sorted(dump_dir.glob("*.parquet"))
    return dumps[-1] if dumps else None


class _IngestionCoordinatorLike(Protocol):
    def ingest_date(self, dataset: str, trade_date: str, force: bool = False) -> object:
        """Run one date-level ingestion."""
        ...


class _IngestionBundleLike(Protocol):
    coordinator: _IngestionCoordinatorLike


type _IngestionBundleFactory = Callable[
    ...,
    AbstractContextManager[_IngestionBundleLike],
]


class _R2LiveSourceLoader(Protocol):
    def __call__(
        self,
        *,
        report_path: Path,
        source_manifest: Path,
    ) -> R2LiveGateEvidenceSource | None: ...


def _default_r2_live_source_loader(
    *, report_path: Path, source_manifest: Path
) -> R2LiveGateEvidenceSource | None:
    return load_r2_live_gate_source(
        report_path=report_path,
        source_manifest=source_manifest,
    )


def r2_live_gate_reader_from_environment(
    environment: MappingABC[str, str],
    *,
    source_loader: _R2LiveSourceLoader = _default_r2_live_source_loader,
) -> R2LiveGateEvidenceReader:
    """Resolve one explicit report/manifest pair or return the fail-closed reader."""
    report = environment.get("DITTO_R2_LIVE_REPORT_PATH")
    manifest = environment.get("DITTO_R2_LIVE_SOURCE_MANIFEST_PATH")
    if not report or not manifest:
        return NullR2LiveGateEvidenceReader()
    source = source_loader(
        report_path=Path(report),
        source_manifest=Path(manifest),
    )
    if source is None:
        return NullR2LiveGateEvidenceReader()
    return FileR2LiveGateEvidenceReader(source)


def _ingestion_bundle_factory() -> _IngestionBundleFactory:
    module = import_module("ditto_apps.registry.contexts.ingestion")
    return cast(_IngestionBundleFactory, module.create_ingestion_bundle)


class FuyaoAdjustmentEventsSource:
    """fuyao 复权因子事件辅源（#438）：本地 adjustment-factors dump 最新快照."""

    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root

    def fetch_adjustment_events(self, trade_date: str) -> pl.DataFrame:
        """最新 dump → 目标日事件帧 [ticker, trade_date, 分红/送转/配股字段]."""
        dump = latest_fuyao_dump(self._data_root, "adjustment-factors")
        if dump is None:
            raise RuntimeError(
                "fuyao adjustment-factors dump not found: run 'ditto fuyao "
                "dump-adjustment-factors' before adj_factor reconciliation"
            )
        logger.info(
            "adj_factor reconciliation using fuyao adjustment-factors dump",
            event="reconciliation_events_dump",
            dump=str(dump),
            trade_date=trade_date,
        )
        target = date.fromisoformat(trade_date)
        frame = FuyaoSource.adjustment_factors_frame(dump)
        return frame.filter(pl.col("trade_date") == target)


class FundamentalFinancialReconcileContext:
    """财务对账主源上下文（#473）：黄金集标的的最新有效 vintage 报表行."""

    def __init__(
        self,
        readers: FundamentalReaders,
        instrument_reader: InstrumentReader,
        golden: GoldenDatasetSpec | None,
    ) -> None:
        self._readers = readers
        self._instrument_reader = instrument_reader
        self._golden = golden

    def latest_statements(
        self, dataset: str, as_of: str, tickers: list[str] | None = None
    ) -> pl.DataFrame:
        """黄金集标的 → PIT 最新有效行（黄金集未配置时拒绝，不做全市场展开）."""
        scope = tickers if tickers is not None else self._golden_tickers()
        reader = self._reader_for(dataset)
        rows = [
            frame
            for ticker in scope
            if not (frame := self._statement_frame(reader, ticker, as_of)).is_empty()
        ]
        if not rows:
            return pl.DataFrame()
        return pl.concat(rows)

    def _golden_tickers(self) -> list[str]:
        if not self._golden or not self._golden.is_enabled:
            raise RuntimeError(
                "financial reconciliation requires the golden dataset "
                "(config/default/golden_dataset.yml) to scope instruments"
            )
        return list(self._golden.get_tickers())

    def _reader_for(self, dataset: str) -> SqliteTableReader:
        readers = self._readers
        reader = {
            "income_statement": readers.income_statement,
            "balance_sheet": readers.balance_sheet,
            "cash_flow": readers.cash_flow,
        }.get(dataset)
        if reader is None:
            raise RuntimeError(f"unsupported financial dataset: {dataset}")
        return reader

    def _statement_frame(
        self, reader: SqliteTableReader, ticker: str, as_of: str
    ) -> pl.DataFrame:
        instrument_ids = self._instrument_reader.map_bare_tickers_to_instrument_ids(
            [ticker]
        ).get(ticker, [])
        frames = [
            reader.get_range(instrument_id, as_of_date=date.fromisoformat(as_of))
            for instrument_id in instrument_ids
        ]
        frames = [frame for frame in frames if not frame.is_empty()]
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames).with_columns(ticker=pl.lit(ticker, dtype=pl.String))


class ProtocolAdapterProvider(Provider):
    """Bridges concrete infrastructure types to Protocol interfaces."""

    scope = Scope.APP

    @provide
    def secondary_bars_source_protocol(
        self,
        fuyao_source: FuyaoSource | None,
    ) -> SecondaryBarsSourceProtocol:
        """对账辅源：fuyao（未配置时显式失败，不再回退 TDX）。"""
        if fuyao_source is not None:
            return fuyao_source
        raise RuntimeError(
            "secondary bars source is unconfigured: set FUYAO_API_KEY to enable "
            "cross-source reconciliation"
        )

    @provide
    def secondary_adjustment_events_source_protocol(
        self,
        data_root: Path,
    ) -> SecondaryAdjustmentEventsSourceProtocol:
        """adj_factor 对账辅源：fuyao 本地事件 dump（无 dump 显式失败）。"""
        return FuyaoAdjustmentEventsSource(Path(data_root))

    @provide
    def secondary_financials_source_protocol(
        self,
        fuyao_source: FuyaoSource | None,
    ) -> SecondaryFinancialsSourceProtocol:
        """财务三表对账辅源：fuyao 财务 REST（#473）。"""
        if fuyao_source is not None:
            return fuyao_source
        raise RuntimeError(
            "secondary financials source is unconfigured: set FUYAO_API_KEY to "
            "enable financial reconciliation"
        )

    @provide
    def financial_reconcile_context(
        self,
        fundamental_readers: FundamentalReaders,
        instrument_reader: InstrumentReader,
        golden_dataset: GoldenDatasetSpec | None,
    ) -> FinancialReconcileContextProtocol:
        """财务对账主源上下文：黄金集标的的最新有效 vintage 报表行（#473）。"""
        return FundamentalFinancialReconcileContext(
            fundamental_readers,
            instrument_reader,
            golden_dataset,
        )

    @provide
    def comparison_store_protocol(
        self,
        writer: ComparisonWriter,
    ) -> ComparisonStoreProtocol:
        """ComparisonWriter → ComparisonStoreProtocol."""
        return writer

    @provide
    def instrument_store_protocol(
        self,
        reader: InstrumentReader,
    ) -> InstrumentStoreProtocol:
        """InstrumentReader → InstrumentStoreProtocol."""
        return reader

    @provide
    def compile_cache_backend(
        self,
        client: SQLiteClient,
    ) -> SQLiteCompileCacheBackend:
        """SQLiteClient → SQLiteCompileCacheBackend."""
        return client

    @provide
    def source_data_port(self, accessor: SourceAccessor) -> SourceDataPort:
        """SourceAccessor.tushare → SourceDataPort."""
        return accessor.tushare


class R2LiveGateEvidenceProvider(Provider):
    """Late composition-root override for explicit Task 18 evidence paths."""

    scope = Scope.APP

    @provide
    def r2_live_gate_evidence_reader(self) -> R2LiveGateEvidenceReader:
        """Inject verified live evidence only from Task 18's exact paths."""
        return r2_live_gate_reader_from_environment(os.environ)
