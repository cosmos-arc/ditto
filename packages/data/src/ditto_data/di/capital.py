"""Data 层 - Capital Domain Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_platform.foundation import FileLockManager, ParquetStore, SQLiteClient

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
from ditto_data.storage.capital.top10_floatholders import (
    Top10FloatholdersReader,
    Top10FloatholdersWriter,
)
from ditto_data.storage.capital.top10_holders import (
    Top10HoldersReader,
    Top10HoldersWriter,
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
            margin_trading=MarginTradingReader(
                MARGIN_TRADING_SPEC, sqlite_client, settings.data_root
            ),
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
            top10_holders=Top10HoldersReader(_top10_parquet_store(settings)),
            top10_floatholders=Top10FloatholdersReader(_top10_parquet_store(settings)),
        )

    @provide
    def capital_writers(
        self,
        sqlite_client: SQLiteClient,
        settings: DataStoreSettings,
        file_lock_manager: FileLockManager,
    ) -> CapitalWriters:
        """Capital 域写入依赖聚合（parquet 车道写入锁经 store 下发）。"""
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
                _index_valuation_parquet_store(settings, file_lock=file_lock_manager)
            ),
            moneyflow=MoneyflowWriter(
                _moneyflow_parquet_store(settings, file_lock=file_lock_manager)
            ),
            cyq_perf=CyqPerfWriter(
                _cyq_perf_parquet_store(settings, file_lock=file_lock_manager)
            ),
            hk_hold=HkHoldWriter(
                _hk_hold_parquet_store(settings, file_lock=file_lock_manager)
            ),
            hsgt_top10=HsgtTop10Writer(
                _hsgt_top10_parquet_store(settings, file_lock=file_lock_manager)
            ),
            top_list=TopListWriter(
                _top_list_parquet_store(settings, file_lock=file_lock_manager)
            ),
            top_inst=TopInstWriter(
                _top_inst_parquet_store(settings, file_lock=file_lock_manager)
            ),
            top10_holders=Top10HoldersWriter(
                _top10_parquet_store(settings, file_lock=file_lock_manager)
            ),
            top10_floatholders=Top10FloatholdersWriter(
                _top10_parquet_store(settings, file_lock=file_lock_manager)
            ),
        )

    @provide
    def capital_store(
        self,
        capital_read_ports: CapitalReaders,
        capital_write_ports: CapitalWriters,
    ) -> CapitalStore:
        """Capital domain unified store（写入锁已下沉 ParquetDatasetWriter）."""
        return CapitalStore(
            read_ports=capital_read_ports,
            write_ports=capital_write_ports,
        )


def _index_valuation_parquet_store(
    settings: DataStoreSettings, *, file_lock: FileLockManager | None = None
) -> ParquetStore:
    """指数估值行按 (instrument_id, trade_date, knowledge_date) 幂等."""
    return ParquetStore(
        settings.data_root,
        key_columns=("instrument_id", "trade_date", "knowledge_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
        file_lock=file_lock,
    )


def _daily_factor_parquet_store(
    settings: DataStoreSettings,
    key_columns: tuple[str, ...],
    *,
    file_lock: FileLockManager | None = None,
) -> ParquetStore:
    """日频资金面帧 Parquet store（键形参数化，date_column=trade_date）."""
    return ParquetStore(
        settings.data_root,
        key_columns=key_columns,
        date_column="trade_date",
        instrument_column="instrument_id",
        file_lock=file_lock,
    )


def _moneyflow_parquet_store(
    settings: DataStoreSettings, *, file_lock: FileLockManager | None = None
) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings,
        ("instrument_id", "trade_date", "knowledge_date"),
        file_lock=file_lock,
    )


def _cyq_perf_parquet_store(
    settings: DataStoreSettings, *, file_lock: FileLockManager | None = None
) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings,
        ("instrument_id", "trade_date", "knowledge_date"),
        file_lock=file_lock,
    )


def _hk_hold_parquet_store(
    settings: DataStoreSettings, *, file_lock: FileLockManager | None = None
) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings,
        ("instrument_id", "trade_date", "knowledge_date"),
        file_lock=file_lock,
    )


def _hsgt_top10_parquet_store(
    settings: DataStoreSettings, *, file_lock: FileLockManager | None = None
) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings,
        ("instrument_id", "trade_date", "market_type", "knowledge_date"),
        file_lock=file_lock,
    )


def _top_list_parquet_store(
    settings: DataStoreSettings, *, file_lock: FileLockManager | None = None
) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings,
        ("instrument_id", "trade_date", "reason", "knowledge_date"),
        file_lock=file_lock,
    )


def _top_inst_parquet_store(
    settings: DataStoreSettings, *, file_lock: FileLockManager | None = None
) -> ParquetStore:
    return _daily_factor_parquet_store(
        settings,
        ("instrument_id", "trade_date", "exalter", "side", "reason", "knowledge_date"),
        file_lock=file_lock,
    )


def _top10_parquet_store(
    settings: DataStoreSettings, *, file_lock: FileLockManager | None = None
) -> ParquetStore:
    """
    前十股东两榜共用存储配置.

    行以 (标的, 报告期, 公告日, 持有人名) 为自然键；榜单目录由
    reader/writer 构造参数区分（#627）。
    """
    return ParquetStore(
        settings.data_root,
        key_columns=(
            "instrument_id",
            "report_date",
            "knowledge_date",
            "holder_name",
        ),
        date_column="report_date",
        instrument_column="instrument_id",
        file_lock=file_lock,
    )
