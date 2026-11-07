"""Fundamental query facade — 封装 fundamental 数据端口，隐藏内部端口类型."""

from __future__ import annotations

from datetime import date
from typing import Protocol

import polars as pl
from ditto_data.catalog.snapshot_completion import completed_snapshots
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader

from ditto_application.exceptions import AppQueryError
from ditto_application.queries._maturity_gate import assert_query_datasets_allowed

__all__ = ["FundamentalDataPort", "FundamentalQueryFacade"]

_BALANCE_SHEET_DATASET = "balance_sheet"
_INCOME_STATEMENT_DATASET = "income_statement"
_CASH_FLOW_DATASET = "cash_flow"
_DIVIDEND_DATASET = "dividend"
_CORPORATE_ACTIONS_DATASET = "corporate_actions"
_FINA_INDICATOR_DATASET = "fina_indicator"
_EARNINGS_EXPRESS_DATASET = "earnings_express"
_EARNINGS_FORECAST_DATASET = "earnings_forecast"


class FundamentalDataPort(Protocol):
    """窄 Protocol：FundamentalQueryFacade 所需的 fundamental 数据获取能力."""

    def get_fund_portfolio(
        self,
        source_ticker: str,
        start: str,
        end: str,
        as_of: str | None = None,
    ) -> pl.DataFrame:
        """Read fund disclosure observations without inferring report types."""
        ...

    def get_balance_sheet(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        """查询资产负债表."""
        ...

    def get_income_statement(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        """查询利润表."""
        ...

    def get_cash_flow(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        """查询现金流量表."""
        ...

    def get_dividend(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        """查询股息数据."""
        ...

    def list_corporate_actions(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """查询公司行动数据."""
        ...

    def get_fina_indicator(
        self,
        instrument_id: int,
        start: str,
        end: str,
        as_of: str | None = None,
    ) -> pl.DataFrame:
        """逐标的财务指标窗口读."""
        ...

    def get_earnings_express(
        self, source_ticker: str, start: str, end: str
    ) -> pl.DataFrame:
        """逐标的业绩快报窗口读."""
        ...

    def get_earnings_forecast(
        self, source_ticker: str, start: str, end: str
    ) -> pl.DataFrame:
        """逐标的业绩预告窗口读."""
        ...


class FundamentalQueryFacade:
    """
    Fundamental 域查询 facade.

    通过 FundamentalDataPort Protocol 获取 fundamental 数据，
    对外只暴露原始参数和 pl.DataFrame 返回值。
    """

    def __init__(
        self,
        fundamental_store: FundamentalDataPort,
        snapshots: ProviderSnapshotReader | None = None,
        lifecycle: PartitionLifecycleReader | None = None,
    ) -> None:
        self._service = fundamental_store
        self._snapshots = snapshots
        self._lifecycle = lifecycle

    def list_fund_portfolio_observations(
        self, source_ticker: str
    ) -> list[dict[str, object]]:
        """List completed source evidence, without claiming a frozen canonical read."""
        if self._snapshots is None or self._lifecycle is None:
            return []
        snapshots = [
            snapshot
            for snapshot in self._snapshots.list_snapshots(dataset_id="fund_portfolio")
            if dict(snapshot.response_metadata).get("source_ticker")
            in {None, source_ticker}
        ]
        return [
            {
                "snapshot_id": snapshot.snapshot_id,
                "source": snapshot.source,
                "request_start": snapshot.request_start,
                "request_end": snapshot.request_end,
                "observed_at": self._snapshots.get_observed_at(snapshot.snapshot_id),
                "rows": snapshot.row_count,
                "payload_retained": snapshot.payload_retained,
                "checksum": snapshot.checksum,
                "scope": "fund"
                if dict(snapshot.response_metadata).get("source_ticker")
                else "market",
                "source_ticker": dict(snapshot.response_metadata).get("source_ticker"),
            }
            for snapshot in completed_snapshots(snapshots, self._lifecycle)
        ]

    def get_balance_sheet(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """
        查询资产负债表.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            资产负债表 DataFrame，无数据返回 None

        """
        self._assert_dataset_allowed(
            _BALANCE_SHEET_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_balance_sheet(instrument_id, as_of_date)

    def get_income_statement(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """
        查询利润表.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            利润表 DataFrame，无数据返回 None

        """
        self._assert_dataset_allowed(
            _INCOME_STATEMENT_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_income_statement(instrument_id, as_of_date)

    def get_cash_flow(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """
        查询现金流量表.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            现金流量表 DataFrame，无数据返回 None

        """
        self._assert_dataset_allowed(
            _CASH_FLOW_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_cash_flow(instrument_id, as_of_date)

    def get_dividend(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """
        查询股息数据.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            股息 DataFrame，无数据返回 None

        """
        self._assert_dataset_allowed(
            _DIVIDEND_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_dividend(instrument_id, as_of_date)

    def list_corporate_actions(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
        as_of_date: date | None = None,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """
        查询公司行动数据.

        Args:
            instrument_id: 标的 ID
            start_date: 开始日期
            end_date: 结束日期
            as_of_date: PIT 查询日期（可选）
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            公司行动 DataFrame

        """
        self._assert_dataset_allowed(
            _CORPORATE_ACTIONS_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.list_corporate_actions(
            instrument_id, start_date, end_date, as_of_date
        )

    def _assert_dataset_allowed(
        self,
        dataset_id: str,
        *,
        allow_experimental_data: bool,
    ) -> None:
        assert_query_datasets_allowed(
            (dataset_id,),
            allow_experimental_data=allow_experimental_data,
            context=f"fundamental query {dataset_id}",
        )

    def get_fund_portfolio(
        self,
        source_ticker: str,
        start: str,
        end: str,
        as_of: str | None = None,
        *,
        require_complete: bool = False,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """Observe disclosed stocks; dates do not establish a complete portfolio."""
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise AppQueryError("fund portfolio start must not exceed end")
        if require_complete:
            raise AppQueryError("fund_portfolio report completeness is unverified")
        self._assert_dataset_allowed(
            "fund_portfolio", allow_experimental_data=allow_experimental_data
        )
        return self._service.get_fund_portfolio(source_ticker, start, end, as_of)

    # ── #658 批次4b 消费接线：披露帧窗口读 ─────────────────────────────

    def get_fina_indicator(
        self,
        instrument_id: int,
        start: str,
        end: str,
        as_of: str | None = None,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """逐标的财务指标窗口读(report_date 窗口;as_of 选版收敛修订)."""
        self._assert_dataset_allowed(
            _FINA_INDICATOR_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_fina_indicator(instrument_id, start, end, as_of)

    def get_earnings_express(
        self,
        source_ticker: str,
        start: str,
        end: str,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """逐标的业绩快报窗口读(ann_date 公告事件;金额元;ticker 键)."""
        self._assert_dataset_allowed(
            _EARNINGS_EXPRESS_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_earnings_express(source_ticker, start, end)

    def get_earnings_forecast(
        self,
        source_ticker: str,
        start: str,
        end: str,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """逐标的业绩预告窗口读(ann_date 公告事件;净利润万元;ticker 键)."""
        self._assert_dataset_allowed(
            _EARNINGS_FORECAST_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_earnings_forecast(source_ticker, start, end)
