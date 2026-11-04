"""Capital domain store with dedicated query/write methods."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import FileLockManager, OnDuplicate, logger

from ditto_data.services.deps import CapitalReaders, CapitalWriters
from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class CapitalStore:
    """
    Capital domain unified store.

    Thin wrapper around Reader/Writer components with dependency injection.
    Delegates all operations to the underlying readers and writers.
    """

    def __init__(
        self,
        read_ports: CapitalReaders,
        write_ports: CapitalWriters,
        file_lock: FileLockManager | None = None,
    ) -> None:
        """
        Initialize CapitalStore.

        Args:
            read_ports: Capital domain read ports (all readers).
            write_ports: Capital domain write ports (all writers).
            file_lock: 文件锁（可选；parquet 车道并发写防护）.

        """
        self._read_ports = read_ports
        self._write_ports = write_ports
        self._file_lock = file_lock

        logger.debug(
            "CapitalStore initialized",
            event="capital_store_init_complete",
        )

    # Query methods (get_*)

    def get_margin_trading(self, instrument_id: int, as_of_date: date) -> pl.DataFrame:
        """
        Query margin trading data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with margin trading data.

        """
        return self._read_ports.margin_trading.get(instrument_id, as_of_date)

    def get_pledge_ratio(self, instrument_id: int, as_of_date: date) -> pl.DataFrame:
        """
        Query pledge ratio data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with pledge ratio data.

        """
        return self._read_ports.pledge_ratio.get(instrument_id, as_of_date)

    def get_valuation_metrics(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame:
        """
        Query valuation metrics data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with valuation metrics data.

        """
        return self._read_ports.valuation_metrics.get(instrument_id, as_of_date)

    def get_index_composition(self, index_id: str, as_of_date: date) -> pl.DataFrame:
        """
        Query index composition data for an index.

        Args:
            index_id: The index ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with index composition data.

        """
        return self._read_ports.index_composition.get(index_id, as_of_date)

    # Write methods (save_*)

    def save_margin_trading(
        self,
        df: pl.DataFrame,
        on_duplicate: OnDuplicate = OnDuplicate.KEEP_FIRST,
    ) -> int:
        """
        Save margin trading data.

        Args:
            df: DataFrame with margin trading data to save.
            on_duplicate: 冲突策略（KEEP_FIRST 忽略冲突行；KEEP_LAST
                同主键后写覆盖——force 重取的值修正收敛依赖它）.

        Returns:
            Number of records written.

        """
        return self._write_ports.margin_trading.write(df, on_duplicate=on_duplicate)

    def save_pledge_ratio(self, df: pl.DataFrame) -> int:
        """
        Save pledge ratio data.

        Args:
            df: DataFrame with pledge ratio data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.pledge_ratio.write(df)

    def save_valuation_metrics(self, df: pl.DataFrame) -> int:
        """
        Save valuation metrics data.

        Args:
            df: DataFrame with valuation metrics data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.valuation_metrics.write(df)

    def save_index_composition(self, df: pl.DataFrame) -> int:
        """
        Save index composition data.

        Args:
            df: DataFrame with index composition data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.index_composition.write(df)

    def save_index_valuation(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save index daily valuation rows (market cap in 元, shares in 股)."""
        writer = self._write_ports.index_valuation
        if writer is None:
            raise ValueError("index_valuation writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_index_weight(self, df: pl.DataFrame) -> int:
        """Save canonical effective-dated index weights."""
        return self._write_ports.index_composition.write(df)

    # ── #518/#519/#520/#523 日频资金面/席位/北向/筹码（parquet 追加观察）──

    def save_moneyflow(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save moneyflow rows（金额万元/量手）."""
        writer = self._write_ports.moneyflow
        if writer is None:
            raise ValueError("moneyflow writer not configured")
        # backfill --parallel 并发写同年分区的丢失更新防护（#517-523 评审）
        if self._file_lock is not None:
            with self._file_lock.acquire(f"moneyflow_write_{year}", timeout=60.0):
                result = writer.write(df, year, on_duplicate=on_duplicate)
        else:
            result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_cyq_perf(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save daily chip performance rows（价格元/winner_rate %）."""
        writer = self._write_ports.cyq_perf
        if writer is None:
            raise ValueError("cyq_perf writer not configured")
        # backfill --parallel 并发写同年分区的丢失更新防护（#517-523 评审）
        if self._file_lock is not None:
            with self._file_lock.acquire(f"cyq_perf_write_{year}", timeout=60.0):
                result = writer.write(df, year, on_duplicate=on_duplicate)
        else:
            result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_hk_hold(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save northbound holding rows（vol 股/ratio %）."""
        writer = self._write_ports.hk_hold
        if writer is None:
            raise ValueError("hk_hold writer not configured")
        # backfill --parallel 并发写同年分区的丢失更新防护（#517-523 评审）
        if self._file_lock is not None:
            with self._file_lock.acquire(f"hk_hold_write_{year}", timeout=60.0):
                result = writer.write(df, year, on_duplicate=on_duplicate)
        else:
            result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_hsgt_top10(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save HSGT top-10 rows（金额元；改制后买/卖/净为 null）."""
        writer = self._write_ports.hsgt_top10
        if writer is None:
            raise ValueError("hsgt_top10 writer not configured")
        # backfill --parallel 并发写同年分区的丢失更新防护（#517-523 评审）
        if self._file_lock is not None:
            with self._file_lock.acquire(f"hsgt_top10_write_{year}", timeout=60.0):
                result = writer.write(df, year, on_duplicate=on_duplicate)
        else:
            result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_top_list(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save dragon-tiger stock rows（金额元，reason 进主键）."""
        writer = self._write_ports.top_list
        if writer is None:
            raise ValueError("top_list writer not configured")
        # backfill --parallel 并发写同年分区的丢失更新防护（#517-523 评审）
        if self._file_lock is not None:
            with self._file_lock.acquire(f"top_list_write_{year}", timeout=60.0):
                result = writer.write(df, year, on_duplicate=on_duplicate)
        else:
            result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_top_inst(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save dragon-tiger seat rows（金额元，exalter+side 进主键）."""
        writer = self._write_ports.top_inst
        if writer is None:
            raise ValueError("top_inst writer not configured")
        # backfill --parallel 并发写同年分区的丢失更新防护（#517-523 评审）
        if self._file_lock is not None:
            with self._file_lock.acquire(f"top_inst_write_{year}", timeout=60.0):
                result = writer.write(df, year, on_duplicate=on_duplicate)
        else:
            result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_top10_holders(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """
        Save top-10 holder rows（hold_amount 股/比率 %，#627）.

        行按 report_date 年分片落各自的年分区（correctness review #627 F1，
        同 fina_indicator/fund_portfolio 的 #3 先例）：年报/Q4 行报告期与
        公告年跨年时，单一摄取年分区会让按报告期年的范围读漏行。
        """
        return self._write_disclosure_frame_by_report_year(
            self._write_ports.top10_holders,
            "top10_holders",
            df,
            on_duplicate,
        )

    def save_top10_floatholders(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save top-10 float holder rows（#627，分片语义同 save_top10_holders）."""
        return self._write_disclosure_frame_by_report_year(
            self._write_ports.top10_floatholders,
            "top10_floatholders",
            df,
            on_duplicate,
        )

    def _write_disclosure_frame_by_report_year(
        self,
        writer: ParquetDatasetWriter | None,
        dataset: str,
        df: pl.DataFrame,
        on_duplicate: OnDuplicate,
    ) -> int:
        """披露锚帧按 report_date 年分片写入对应年分区（含同年文件锁）."""
        if writer is None:
            raise ValueError(f"{dataset} writer not configured")
        if df.is_empty():
            return 0
        written = 0
        for report_year in sorted(
            {date_value.year for date_value in df["report_date"].to_list()}
        ):
            part = df.filter(pl.col("report_date").dt.year() == report_year)
            if self._file_lock is not None:
                # backfill --parallel 并发写同年分区的丢失更新防护
                with self._file_lock.acquire(
                    f"{dataset}_write_{report_year}", timeout=60.0
                ):
                    result = writer.write(part, report_year, on_duplicate=on_duplicate)
            else:
                result = writer.write(part, report_year, on_duplicate=on_duplicate)
            written += result.added + result.updated
        return written

    def get_moneyflows(self, start: str, end: str) -> pl.DataFrame:
        """Read market-wide moneyflow rows（L3 巡检用）."""
        reader = self._read_ports.moneyflow
        if reader is None:
            raise ValueError("moneyflow reader not configured")
        return reader.read(start_date=start, end_date=end)

    def get_moneyflow(self, instrument_id: int, start: str, end: str) -> pl.DataFrame:
        """
        逐标的资金流窗口读（万元/手；#658 批次3 画像链）.

        knowledge_date=摄取日（非源发布日），晚发布重取/滑窗 force 重取
        （B1 生产机制）产生同 (instrument_id, trade_date) 多版本；
        latest_available 收敛到最新 knowledge_date（#628 词表；#667）。
        """
        reader = self._read_ports.moneyflow
        if reader is None:
            raise ValueError("moneyflow reader not configured")
        frame = reader.read(
            instrument_ids=[instrument_id], start_date=start, end_date=end
        )
        if frame.is_empty():
            return frame
        return (
            frame.sort("knowledge_date")
            .unique(subset=["instrument_id", "trade_date"], keep="last")
            .sort("trade_date")
        )

    def get_top_list(self, instrument_id: int, start: str, end: str) -> pl.DataFrame:
        """逐标的龙虎榜窗口读（金额元；事件按 reason 独立成行）."""
        reader = self._read_ports.top_list
        if reader is None:
            raise ValueError("top_list reader not configured")
        frame = reader.read(
            instrument_ids=[instrument_id], start_date=start, end_date=end
        )
        return frame if frame.is_empty() else frame.sort(["trade_date", "reason"])

    def get_top_inst(self, instrument_id: int, start: str, end: str) -> pl.DataFrame:
        """逐标的龙虎榜席位窗口读（单边 null 保真；席位≠总仓位）."""
        reader = self._read_ports.top_inst
        if reader is None:
            raise ValueError("top_inst reader not configured")
        frame = reader.read(
            instrument_ids=[instrument_id], start_date=start, end_date=end
        )
        return (
            frame
            if frame.is_empty()
            else frame.sort(["trade_date", "reason", "side", "exalter"])
        )

    def get_margin_trading_range(
        self,
        instrument_id: int,
        start: str,
        end: str,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """逐标的两融窗口读（PIT 可选；修订收敛到 knowledge 最新版本）."""
        return self._read_ports.margin_trading.get_range(
            instrument_id,
            start_date=date.fromisoformat(start) if start else None,
            end_date=date.fromisoformat(end) if end else None,
            as_of_date=as_of_date,
        )

    def get_cyq_perfs(self, start: str, end: str) -> pl.DataFrame:
        """Read market-wide chip performance rows（L3 巡检用）."""
        reader = self._read_ports.cyq_perf
        if reader is None:
            raise ValueError("cyq_perf reader not configured")
        return reader.read(start_date=start, end_date=end)

    # ── #658 批次4b 消费接线：北向双库/持仓双榜读取 ──────────────────────

    def get_hk_hold(self, instrument_id: int, start: str, end: str) -> pl.DataFrame:
        """
        逐标的北向持股窗口读（vol 股/ratio %）.

        知识日分段 2024-08-19（日频制度段=次交易日；季度段=账本观察日），
        2024-08-19 后非季末无行＝制度性缺席不是缺口。
        """
        reader = self._read_ports.hk_hold
        if reader is None:
            raise ValueError("hk_hold reader not configured")
        frame = reader.read(
            instrument_ids=[instrument_id], start_date=start, end_date=end
        )
        return frame if frame.is_empty() else frame.sort("trade_date")

    def get_hsgt_top10s(
        self, start: str, end: str, market_type: str | None = None
    ) -> pl.DataFrame:
        """
        市场级沪深港通十大成交窗口读（每日 20 行事件型）.

        2024-08-19 改制后 buy/sell/net_amount 官方停披——null 保留不填零。
        """
        reader = self._read_ports.hsgt_top10
        if reader is None:
            raise ValueError("hsgt_top10 reader not configured")
        filters = [pl.col("market_type") == market_type] if market_type else None
        frame = reader.read(start_date=start, end_date=end, filters=filters)
        return (
            frame
            if frame.is_empty()
            else frame.sort(["trade_date", "market_type", "rank"])
        )

    def get_top10_holders(
        self, instrument_id: int, start: str, end: str
    ) -> pl.DataFrame:
        """
        逐标的前十大股东窗口读（报告期粒度;公告日=knowledge_date 版本行）.

        窗口过滤 report_date;名单跌出≠清仓,两榜语义独立不互推。
        """
        reader = self._read_ports.top10_holders
        if reader is None:
            raise ValueError("top10_holders reader not configured")
        frame = reader.read(
            instrument_ids=[instrument_id], start_date=start, end_date=end
        )
        return (
            frame
            if frame.is_empty()
            else frame.sort(["report_date", "knowledge_date", "holder_name"])
        )

    def get_top10_floatholders(
        self, instrument_id: int, start: str, end: str
    ) -> pl.DataFrame:
        """逐标的前十大流通股东窗口读（独立流通股榜口径）."""
        reader = self._read_ports.top10_floatholders
        if reader is None:
            raise ValueError("top10_floatholders reader not configured")
        frame = reader.read(
            instrument_ids=[instrument_id], start_date=start, end_date=end
        )
        return (
            frame
            if frame.is_empty()
            else frame.sort(["report_date", "knowledge_date", "holder_name"])
        )

    # ── #658 批次4c 消费接线：指数估值读取 ─────────────────────────────

    def get_index_valuation(
        self, instrument_id: int, start: str, end: str
    ) -> pl.DataFrame:
        """
        逐指数估值窗口读（total_mv/float_mv 元，pe/pe_ttm/pb 倍数）.

        单位合同与个股 daily_basic 不同：市值单位元、股本单位股（doc_id=128）。
        knowledge_date=摄取日（非源发布日），重拉产生同日多版本；latest_available
        收敛到最新 knowledge_date（#628 词表）。
        """
        reader = self._read_ports.index_valuation
        if reader is None:
            raise ValueError("index_valuation reader not configured")
        frame = reader.read(
            instrument_ids=[instrument_id], start_date=start, end_date=end
        )
        if frame.is_empty():
            return frame
        return (
            frame.sort("knowledge_date")
            .unique(subset=["instrument_id", "trade_date"], keep="last")
            .sort("trade_date")
        )
