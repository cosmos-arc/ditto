"""
MarketWriteService - Market 域写入服务。

提供市场行情数据的写入接口，包括 K线、复权因子和股票状态。
"""

from datetime import date
from typing import Literal

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced
from ditto_infra.foundation.concurrency import FileLockManager

from ditto_data.ingestion.late_arrival import check_late_arrival
from ditto_data.models import OnDuplicate
from ditto_data.models.ingestion import (
    DataLateArrivalPolicy,
    LateArrivalCheckResult,
)
from ditto_data.services.ports import MarketWritePorts
from ditto_data.storage.market.commodity.bars import CommodityBarsWriter
from ditto_data.storage.market.etf.bars import EtfBarsWriter
from ditto_data.storage.market.fx.bars import FxBarsWriter
from ditto_data.storage.market.index.bars import IndexBarsWriter
from ditto_data.storage.market.stock.bars import StockBarsWriter

type _BarsWriter = (
    StockBarsWriter
    | EtfBarsWriter
    | IndexBarsWriter
    | FxBarsWriter
    | CommodityBarsWriter
)


class MarketWriteService:
    """Market 域写入服务."""

    def __init__(
        self,
        write_ports: MarketWritePorts,
        file_lock: FileLockManager,
    ) -> None:
        """
        初始化 MarketWriteService.

        Args:
            write_ports: Market 域写入端口（包含所有 Writer）.
            file_lock: 文件锁管理器（用于并发写入保护）.

        """
        self._write_ports = write_ports
        self._file_lock = file_lock

    @staticmethod
    def _to_storage_columns(df: pl.DataFrame) -> pl.DataFrame:
        """归一化列名到存储层约定。"""
        return df

    @staticmethod
    def _map_on_duplicate(on_duplicate: OnDuplicate) -> OnDuplicate:
        """归一化 OnDuplicate 枚举."""
        return on_duplicate

    @traced("market.save_bars")
    def save_bars(
        self,
        dataset: Literal[
            "stock_daily", "etf_daily", "index_daily", "fx_daily", "commodity_daily"
        ],
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """
        保存K线数据.

        Args:
            dataset: 数据集类型（stock_daily, etf_daily, index_daily,
                fx_daily, commodity_daily）.
            df: K线数据 DataFrame.
            year: 年份.
            on_duplicate: 重复数据处理策略.

        Returns:
            写入的记录数.

        """
        logger.info(
            "Writing bars data",
            event="market_write_bars_start",
            dataset=dataset,
            year=year,
            row_count=len(df),
        )

        on_duplicate_enum = self._map_on_duplicate(on_duplicate)
        storage_df = self._to_storage_columns(df)

        # 使用文件锁保护并发写入
        lock_name = f"bars_write_{dataset}_{year}"
        with self._file_lock.acquire(lock_name, timeout=60.0):
            writer = self._get_bars_writer(dataset)
            write_result = writer.write(
                storage_df,
                year,
                on_duplicate=on_duplicate_enum,
            )

        rows_written = write_result.added + write_result.updated

        logger.info(
            "Bars data written",
            event="market_write_bars_complete",
            dataset=dataset,
            year=year,
            rows_written=rows_written,
        )

        # 记录指标
        Metrics.data_records.add(
            len(storage_df),
            {"dataset": dataset, "operation": "write"},
        )

        return rows_written

    def _get_bars_writer(
        self,
        dataset: str,
    ) -> _BarsWriter:
        """
        获取指定数据集的 K线写入器.

        Args:
            dataset: 数据集名称.

        Returns:
            对应的 Writer 实例.

        Raises:
            ValueError: 数据集不支持或 Writer 未配置.

        """
        _REQUIRED_WRITERS = {
            "stock_daily": self._write_ports.stock_bars,
            "etf_daily": self._write_ports.etf_bars,
        }
        _OPTIONAL_WRITERS = {
            "index_daily": self._write_ports.index_bars,
            "fx_daily": self._write_ports.fx_bars,
            "commodity_daily": self._write_ports.commodity_bars,
        }

        if dataset in _REQUIRED_WRITERS:
            return _REQUIRED_WRITERS[dataset]

        if dataset in _OPTIONAL_WRITERS:
            writer = _OPTIONAL_WRITERS[dataset]
            if writer is None:
                raise ValueError(f"{dataset} writer not configured")
            return writer

        raise ValueError(f"Unsupported dataset: {dataset}")

    @traced("market.save_adj_factor")
    def save_adj_factor(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """
        保存复权因子数据（股票）.

        Args:
            df: 复权因子数据 DataFrame.
            year: 年份.
            on_duplicate: 重复数据处理策略.

        Returns:
            写入的记录数.

        """
        logger.info(
            "Writing adjustment factor data",
            event="market_write_adj_factor_start",
            dataset="adj_factor",
            year=year,
            row_count=len(df),
        )

        on_duplicate_enum = self._map_on_duplicate(on_duplicate)
        storage_df = self._to_storage_columns(df)

        # 使用文件锁保护并发写入
        lock_name = f"adj_factor_write_adj_factor_{year}"
        with self._file_lock.acquire(lock_name, timeout=60.0):
            write_result = self._write_ports.stock_adj.write(
                storage_df,
                year,
                on_duplicate=on_duplicate_enum,
            )

        rows_written = write_result.added + write_result.updated

        logger.info(
            "Adjustment factor data written",
            event="market_write_adj_factor_complete",
            dataset="adj_factor",
            year=year,
            rows_written=rows_written,
        )

        # 记录指标
        Metrics.data_records.add(
            len(storage_df),
            {"dataset": "adj_factor", "operation": "write"},
        )

        return rows_written

    @traced("market.save_stock_status")
    def save_stock_status(
        self,
        df: pl.DataFrame,
        year: int,
    ) -> int:
        """
        保存股票状态数据.

        Args:
            df: 股票状态数据 DataFrame.
            year: 年份.

        Returns:
            写入的记录数.

        """
        logger.info(
            "Writing stock status data",
            event="market_write_stock_status_start",
            dataset="stock_status",
            year=year,
            row_count=len(df),
        )

        lock_name = f"stock_status_write_{year}"
        storage_df = self._to_storage_columns(df)

        with self._file_lock.acquire(lock_name, timeout=60.0):
            self._write_ports.stock_status.write(storage_df, year)

        rows_written = len(storage_df)

        logger.info(
            "Stock status data written",
            event="market_write_stock_status_complete",
            year=year,
            rows_written=rows_written,
        )

        Metrics.data_records.add(
            rows_written,
            {"dataset": "stock_status", "operation": "write"},
        )

        return rows_written

    @staticmethod
    def check_late_arrival_on_write(
        *,
        knowledge_date: date,
        trade_date: date,
        policy: DataLateArrivalPolicy,
        max_delay_days: int = 999_999,
    ) -> LateArrivalCheckResult:
        """
        检查写入数据的延迟到达策略.

        供调用方在 save_bars / save_adj_factor 等写入方法之前调用，
        以检查数据的 knowledge_date 是否晚于 trade_date。

        Args:
            knowledge_date: 数据可知日期.
            trade_date: 数据所属交易日期.
            policy: 延迟到达策略.
            max_delay_days: REJECT 策略下允许的最大延迟天数.

        Returns:
            检查结果.

        Raises:
            LateArrivalRejectedError: 当策略为 REJECT 且延迟超过阈值时.

        """
        return check_late_arrival(
            knowledge_date=knowledge_date,
            trade_date=trade_date,
            policy=policy,
            max_delay_days=max_delay_days,
        )
