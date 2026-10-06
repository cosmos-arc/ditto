"""Data 层 - Capital Domain Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_platform.foundation import ParquetStore, SQLiteClient

from ditto_data.config.data_store import DataStoreSettings
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from ditto_data.storage.base.sqlite_table_writer import SqliteTableWriter
from ditto_data.storage.capital.cyq_perf import CyqPerfReader, CyqPerfWriter
from ditto_data.storage.capital.hk_hold import HkHoldReader, HkHoldWriter
from ditto_data.storage.capital.hsgt_top10 import HsgtTop10Reader, HsgtTop10Writer
from ditto_data.storage.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_data.storage.capital.index_valuation import (
    IndexValuationReader,
    IndexValuationWriter,
)
from ditto_data.storage.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_data.storage.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)
from ditto_data.storage.capital.moneyflow import MoneyflowReader, MoneyflowWriter
from ditto_data.storage.capital.pledge.pledge_ratio_reader import (
    PledgeRatioReader,
)
from ditto_data.storage.capital.pledge.pledge_ratio_writer import (
    PledgeRatioWriter,
)
from ditto_data.storage.capital.specs import (
    INDEX_COMPOSITION_SPEC,
    MARGIN_TRADING_SPEC,
    PLEDGE_RATIO_SPEC,
    VALUATION_METRICS_SPEC,
)
from ditto_data.storage.capital.top_inst import TopInstReader, TopInstWriter
from ditto_data.storage.capital.top_list import TopListReader, TopListWriter
from ditto_data.storage.capital.valuation.valuation_metrics_reader import (
    ValuationMetricsReader,
)
from ditto_data.storage.capital.valuation.valuation_metrics_writer import (
    ValuationMetricsWriter,
)

__all__ = ["CapitalProvider"]


class CapitalProvider(Provider):
    """Capital Domain Provider - 融资融券、质押、估值、指数成分."""

    scope = Scope.APP

    @provide
    def index_composition_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> IndexCompositionReader:
        """IndexComposition reader (MetadataService/UniverseService 直接依赖)."""
        return IndexCompositionReader(INDEX_COMPOSITION_SPEC, sqlite_client)

    @provide
    def capital_readers(
        self,
        sqlite_client: SQLiteClient,
        settings: DataStoreSettings,
    ) -> CapitalReaders:
        """Capital 域读取依赖聚合。"""
        return CapitalReaders(
            margin_trading=MarginTradingReader(MARGIN_TRADING_SPEC, sqlite_client),
            pledge_ratio=PledgeRatioReader(PLEDGE_RATIO_SPEC, sqlite_client),
            valuation_metrics=ValuationMetricsReader(
                VALUATION_METRICS_SPEC,
                sqlite_client,
            ),
            index_composition=IndexCompositionReader(
                INDEX_COMPOSITION_SPEC,
                sqlite_client,
            ),
            index_valuation=IndexValuationReader(
                _index_valuation_parquet_store(settings)
            ),
            moneyflow=MoneyflowReader(_moneyflow_parquet_store(settings)),
            cyq_perf=CyqPerfReader(_cyq_perf_parquet_store(settings)),
            hk_hold=HkHoldReader(_hk_hold_parquet_store(settings)),
            hsgt_top10=HsgtTop10Reader(_hsgt_top10_parquet_store(settings)),
            top_list=TopListReader(_top_list_parquet_store(settings)),
            top_inst=TopInstReader(_top_inst_parquet_store(settings)),
        )

    @provide
    def capital_writers(
        self,
        sqlite_client: SQLiteClient,
        settings: DataStoreSettings,
    ) -> CapitalWriters:
        """Capital 域写入依赖聚合。"""
        return CapitalWriters(
            margin_trading=MarginTradingWriter(MARGIN_TRADING_SPEC, sqlite_client),
            pledge_ratio=PledgeRatioWriter(PLEDGE_RATIO_SPEC, sqlite_client),
            valuation_metrics=ValuationMetricsWriter(
                VALUATION_METRICS_SPEC,
                sqlite_client,
            ),
            index_composition=SqliteTableWriter(
                INDEX_COMPOSITION_SPEC,
                sqlite_client,
            ),
            index_valuation=IndexValuationWriter(
                _index_valuation_parquet_store(settings)
            ),
            moneyflow=MoneyflowWriter(_moneyflow_parquet_store(settings)),
            cyq_perf=CyqPerfWriter(_cyq_perf_parquet_store(settings)),
            hk_hold=HkHoldWriter(_hk_hold_parquet_store(settings)),
            hsgt_top10=HsgtTop10Writer(_hsgt_top10_parquet_store(settings)),
            top_list=TopListWriter(_top_list_parquet_store(settings)),
            top_inst=TopInstWriter(_top_inst_parquet_store(settings)),
        )

    @provide
    def capital_store(
        self,
        capital_read_ports: CapitalReaders,
        capital_write_ports: CapitalWriters,
    ) -> CapitalStore:
        """Capital domain unified store."""
        return CapitalStore(
            read_ports=capital_read_ports,
            write_ports=capital_write_ports,
        )


def _index_valuation_parquet_store(settings: DataStoreSettings) -> ParquetStore:
    """指数估值行按 (instrument_id, trade_date, knowledge_date) 幂等."""
    return ParquetStore(
        settings.data_root,
        key_columns=("instrument_id", "trade_date", "knowledge_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )


def _daily_factor_parquet_store(
    settings: DataStoreSettings,
    key_columns: tuple[str, ...],
) -> ParquetStore:
    """日频资金面帧 Parquet store（键形参数化，date_column=trade_date）."""
    return ParquetStore(
        settings.data_root,
        key_columns=key_columns,
        date_column="trade_date",
        instrument_column="instrument_id",
    )


def _moneyflow_parquet_store(settings: DataStoreSettings) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings, ("instrument_id", "trade_date", "knowledge_date")
    )


def _cyq_perf_parquet_store(settings: DataStoreSettings) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings, ("instrument_id", "trade_date", "knowledge_date")
    )


def _hk_hold_parquet_store(settings: DataStoreSettings) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings, ("instrument_id", "trade_date", "knowledge_date")
    )


def _hsgt_top10_parquet_store(settings: DataStoreSettings) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings, ("instrument_id", "trade_date", "market_type", "knowledge_date")
    )


def _top_list_parquet_store(settings: DataStoreSettings) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings, ("instrument_id", "trade_date", "reason", "knowledge_date")
    )


def _top_inst_parquet_store(settings: DataStoreSettings) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings,
        ("instrument_id", "trade_date", "exalter", "side", "reason", "knowledge_date"),
    )
