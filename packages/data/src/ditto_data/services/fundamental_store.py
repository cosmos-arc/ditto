"""Fundamental domain store with dedicated get/save methods."""

from __future__ import annotations

from datetime import date
from hashlib import sha256

import orjson
import polars as pl
from ditto_platform.foundation import OnDuplicate, logger

from ditto_data.models.metadata import FundReportEvidence
from ditto_data.services.deps import FundamentalReaders, FundamentalWriters
from ditto_data.storage.fundamental.fund_portfolio.identity import FundIdentityStore


class FundamentalStore:
    """
    Fundamental domain unified service.

    Thin wrapper with dependency injection using CQRS pattern.
    Delegates read operations to Readers and write operations to Writers.

    跨年分片与同年分区写入锁统一收口在 ParquetDatasetWriter.write
    （审计 #684 批B #7/#14）。
    """

    def __init__(
        self,
        read_ports: FundamentalReaders,
        write_ports: FundamentalWriters,
        fund_identities: FundIdentityStore | None = None,
    ) -> None:
        """
        Initialize FundamentalStore with CQRS Readers/Writers.

        Args:
            read_ports: Fundamental 域读取依赖（包含所有 Reader）.
            write_ports: Fundamental 域写入依赖（包含所有 Writer）.
            fund_identities: 独立的公募持有人身份存储.

        """
        self._read_ports = read_ports
        self._write_ports = write_ports
        self._fund_identities = fund_identities

        logger.debug(
            "FundamentalStore initialized with CQRS Readers/Writers",
            event="fundamental_store_init_complete",
        )

    # get_* - Single record queries (PIT)

    def register_fund_holders(self, frame: pl.DataFrame) -> None:
        """Register fund_basic identities without adding tradable securities."""
        if self._fund_identities is None:
            raise ValueError("fund holder identity store not configured")
        self._fund_identities.register(frame)

    def list_fund_holders(self) -> list[str]:
        """List all observed holders, including OTC and inactive funds."""
        if self._fund_identities is None:
            raise ValueError("fund holder identity store not configured")
        return self._fund_identities.list_codes()

    def require_fund_holders(self, codes: list[str]) -> None:
        """Reject missing holder identities without filtering any holdings."""
        if self._fund_identities is None:
            raise ValueError("fund holder identity store not configured")
        self._fund_identities.require(codes)

    def get_fund_portfolio(
        self,
        source_ticker: str,
        start: str,
        end: str,
        as_of: str | None = None,
    ) -> pl.DataFrame:
        """Read disclosures with only exact, explicitly verified report bindings."""
        frame = self._read_fund_portfolio(source_ticker, start, end, as_of)
        if frame.is_empty():
            return frame
        if self._fund_identities is None:
            raise ValueError("fund holder identity store not configured")
        reports = self._fund_identities.reports(source_ticker)
        groups: list[pl.DataFrame] = []
        for group in frame.partition_by(["report_date", "knowledge_date"]):
            checksum = fund_holdings_checksum(group)
            matched = [
                report
                for report in reports
                if report.holdings_sha256 == checksum
                and report.report_date == group["report_date"][0]
                and report.announcement_date == group["knowledge_date"][0]
            ]
            types = {report.report_type for report in matched}
            groups.append(
                group.with_columns(
                    pl.lit(next(iter(types)) if len(types) == 1 else "unknown").alias(
                        "report_type"
                    ),
                    pl.lit("disclosed_subset").alias("holding_scope"),
                    pl.lit(checksum).alias("holdings_sha256"),
                    pl.lit(
                        matched[0].revision_of if len(matched) == 1 else None,
                        dtype=pl.String,
                    ).alias("revision_of"),
                    pl.lit(
                        orjson.dumps(
                            [item.model_dump(mode="json") for item in matched]
                        ).decode()
                    ).alias("report_evidence"),
                )
            )
        return pl.concat(groups).sort(
            ["report_date", "knowledge_date", "holding_symbol"]
        )

    def register_fund_report(
        self, evidence: FundReportEvidence, document: bytes
    ) -> None:
        """Attach a reviewed document only to its exact local disclosure values."""
        frame = self._read_fund_portfolio(
            evidence.source_ticker,
            evidence.report_date.isoformat(),
            evidence.report_date.isoformat(),
            evidence.announcement_date.isoformat(),
        ).filter(pl.col("knowledge_date") == evidence.announcement_date)
        if (
            frame.is_empty()
            or fund_holdings_checksum(frame) != evidence.holdings_sha256
        ):
            raise ValueError("fund report holdings checksum mismatch")
        if self._fund_identities is None:
            raise ValueError("fund holder identity store not configured")
        self._fund_identities.register_report(evidence, document)

    def _read_fund_portfolio(
        self, source_ticker: str, start: str, end: str, as_of: str | None
    ) -> pl.DataFrame:
        """Read original rows before adding any report interpretation."""
        self.require_fund_holders([source_ticker])
        reader = self._read_ports.fund_portfolio
        if reader is None:
            raise ValueError("fund_portfolio reader not configured")
        filters = [pl.col("source_ticker") == source_ticker]
        if as_of is not None:
            filters.append(pl.col("knowledge_date") <= date.fromisoformat(as_of))
        return reader.read(start_date=start, end_date=end, filters=filters)

    def get_balance_sheet(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get balance sheet for instrument on date (PIT query)."""
        df = self._read_ports.balance_sheet.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_income_statement(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get income statement for instrument on date (PIT query)."""
        df = self._read_ports.income_statement.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_cash_flow(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get cash flow for instrument on date (PIT query)."""
        df = self._read_ports.cash_flow.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_dividend(self, instrument_id: int, as_of_date: date) -> pl.DataFrame | None:
        """Get dividend data for instrument on date (PIT query)."""
        df = self._read_ports.dividend.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    # list_* - Multi record queries

    def get_fina_indicator(
        self,
        instrument_id: int,
        start: str,
        end: str,
        as_of: str | None = None,
    ) -> pl.DataFrame:
        """
        逐标的财务指标窗口读（report_date 窗口；118 列透传）.

        knowledge_date=公告日 ann_date;as_of 给定时按 knowledge_date<=as_of
        收敛到最新公告版本（修订选版）。
        """
        reader = self._read_ports.fina_indicator
        if reader is None:
            raise ValueError("fina_indicator reader not configured")
        frame = reader.read(
            instrument_ids=[instrument_id],
            start_date=start,
            end_date=end,
            filters=(
                [pl.col("knowledge_date") <= pl.lit(as_of).str.to_date()]
                if as_of
                else None
            ),
        )
        if frame.is_empty():
            return frame
        if as_of:
            # pit_asof 词表:同 (instrument, report_date) 收敛到最新可见
            # knowledge 版本(修订选版,#628)。
            frame = frame.sort("knowledge_date").unique(
                subset=["instrument_id", "report_date"], keep="last"
            )
        return frame.sort(["report_date", "knowledge_date"])

    def get_earnings_express(
        self, source_ticker: str, start: str, end: str
    ) -> pl.DataFrame:
        """
        逐标的业绩快报窗口读（ann_date 窗口=公告事件;金额元）.

        平日 0 行=无公告正常;audit_status 透出不伪称已审计。
        instrument_column=source_ticker（该库以 ticker 为仪器键过滤）。
        """
        reader = self._read_ports.earnings_express
        if reader is None:
            raise ValueError("earnings_express reader not configured")
        # ParquetDatasetReader 的 instrument 过滤恒作用于 instrument_id 列,
        # 该库仪器键是 source_ticker——经 filters 显式过滤。
        frame = reader.read(
            start_date=start,
            end_date=end,
            filters=[pl.col("source_ticker") == source_ticker],
        )
        return frame if frame.is_empty() else frame.sort("ann_date")

    def get_earnings_forecast(
        self, source_ticker: str, start: str, end: str
    ) -> pl.DataFrame:
        """逐标的业绩预告窗口读（ann_date 窗口;净利润上下界万元）."""
        reader = self._read_ports.earnings_forecast
        if reader is None:
            raise ValueError("earnings_forecast reader not configured")
        frame = reader.read(
            start_date=start,
            end_date=end,
            filters=[pl.col("source_ticker") == source_ticker],
        )
        return frame if frame.is_empty() else frame.sort(["ann_date", "report_date"])

    def list_corporate_actions(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """List corporate actions for instrument in date range (with optional PIT)."""
        return self._read_ports.corporate_actions.query(
            instrument_id, start_date, end_date, as_of_date
        )

    # save_* - Write methods

    def save_balance_sheet(self, df: pl.DataFrame) -> int:
        """Save balance sheet data."""
        return self._write_ports.balance_sheet.write(df)

    def save_income_statement(self, df: pl.DataFrame) -> int:
        """Save income statement data."""
        return self._write_ports.income_statement.write(df)

    def save_cash_flow(self, df: pl.DataFrame) -> int:
        """Save cash flow data."""
        return self._write_ports.cash_flow.write(df)

    def save_dividend(self, df: pl.DataFrame) -> int:
        """Save dividend data."""
        return self._write_ports.dividend.write(df)

    def save_corporate_actions(self, df: pl.DataFrame) -> int:
        """Save corporate actions data."""
        return self._write_ports.corporate_actions.write(df)

    # #434 业绩预告/快报：parquet 公告事件写入（无公告时刻，采集日即知识日；
    # 与 sqlite 写路径共享单活摄取不变量，写入锁由 writer 层统一提供）。

    def save_earnings_forecast(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save earnings-forecast announcement rows (net-profit bounds in 万元)."""
        writer = self._write_ports.earnings_forecast
        if writer is None:
            raise ValueError("earnings_forecast writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_earnings_express(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save earnings-express announcement rows (amounts in 元)."""
        writer = self._write_ports.earnings_express
        if writer is None:
            raise ValueError("earnings_express writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_fina_indicator(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """
        Save official financial-indicator rows (#521, 118 列透传).

        行按 report_date 年分片落各自的年分区（correctness review #3）：
        摄取日年与报告期年跨年时（8 季度超集常态），单一摄取年分区会让
        按报告期年的范围读漏行。分片由 ParquetDatasetWriter 统一处理。
        """
        writer = self._write_ports.fina_indicator
        if writer is None:
            raise ValueError("fina_indicator writer not configured")
        if df.is_empty():
            return 0
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_fund_portfolio(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """
        Save fund quarterly holding rows (#522, 公告日驱动).

        同 fina_indicator：按 report_date 年分片写（correctness review #3），
        分片由 ParquetDatasetWriter 统一处理。
        """
        writer = self._write_ports.fund_portfolio
        if writer is None:
            raise ValueError("fund_portfolio writer not configured")
        if df.is_empty():
            return 0
        self.require_fund_holders(df["source_ticker"].unique().to_list())
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated


def fund_holdings_checksum(frame: pl.DataFrame) -> str:
    """Bind evidence to values, nulls and disclosure identity, excluding trading IDs."""
    columns = sorted(set(frame.columns) - {"instrument_id", "source"})
    rows = frame.select(columns).sort(columns).to_dicts()
    return sha256(orjson.dumps(rows, option=orjson.OPT_SORT_KEYS)).hexdigest()
