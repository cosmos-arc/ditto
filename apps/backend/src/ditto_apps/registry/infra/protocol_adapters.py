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
from ditto_data.quality.protocols import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    SecondaryAdjustmentEventsSourceProtocol,
    SecondaryBarsSourceProtocol,
)
from ditto_data.services.deps import MarketReaders
from ditto_data.services.market_service import MarketService
from ditto_data.services.source_accessor import SourceAccessor
from ditto_data.sources.fuyao.source import FuyaoSource
from ditto_data.storage.metadata.instrument import InstrumentReader
from ditto_data.storage.runtime.quality import ComparisonWriter

__all__ = ["FuyaoSource", "MarketReaders", "MarketService"]
from ditto_features.compile_cache import SQLiteCompileCacheBackend
from ditto_platform.foundation import SQLiteClient

from ditto_apps.r2_live_evidence_source import load_r2_live_gate_source


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

    def __init__(self, dump_dir: Path) -> None:
        self._dump_dir = dump_dir

    def fetch_adjustment_events(self, trade_date: str) -> pl.DataFrame:
        """最新 dump → 目标日事件帧 [ticker, trade_date, 分红/送转/配股字段]."""
        dump = self._latest_dump()
        if dump is None:
            raise RuntimeError(
                "fuyao adjustment-factors dump not found: run 'ditto fuyao "
                "dump-adjustment-factors' before adj_factor reconciliation"
            )
        target = date.fromisoformat(trade_date)
        frame = FuyaoSource.adjustment_factors_frame(dump)
        return frame.filter(pl.col("trade_date") == target)

    def _latest_dump(self) -> Path | None:
        """YYYYMMDD.parquet 文件名字典序 = 时间序，取最新."""
        if not self._dump_dir.is_dir():
            return None
        dumps = sorted(self._dump_dir.glob("*.parquet"))
        return dumps[-1] if dumps else None


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
        return FuyaoAdjustmentEventsSource(
            Path(data_root) / "fuyao" / "dumps" / "adjustment-factors"
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
