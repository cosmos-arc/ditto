"""
Futures (期货) 域 API 模型（#658 批次4c）.

包含:
- FuturesBar: 期货合约日线响应模型
- FuturesContract: 期货合约身份响应模型
- FuturesBarsQuery: 日线查询参数模型
- FuturesBarsResponse / FuturesContractsResponse: 携带 read_semantics+coverage
- to_futures_bar_list / to_futures_contract_list: 批量转换函数

null 保真：首日无 pre_settle、停牌日无 OHLC 等以 null 透出，不填 0。
"""

from __future__ import annotations

from typing import Self

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ditto_apps.models._date_helpers import DateField, format_date, format_float
from ditto_apps.models.common import DataCoverageInfo, ReadSemantics

__all__ = [
    "FuturesBar",
    "FuturesBarsQuery",
    "FuturesBarsResponse",
    "FuturesContract",
    "FuturesContractsResponse",
    "to_futures_bar_list",
    "to_futures_contract_list",
]


class FuturesBarsQuery(BaseModel):
    """
    期货日线查询参数模型.

    Attributes:
        source_tickers: 合约代码列表 (可选, ts_code 形态如 ["RB2410.SHF"];
            缺省=全部合约; 空列表拒绝——非缺省选择不得静默全量)
        start_date: 开始日期
        end_date: 结束日期
        limit: 窗口内最新 N 行, 默认 1000, 范围 1-10000
        allow_experimental_data: 显式允许 experimental 数据集

    """

    source_tickers: list[str] | None = Field(
        default=None, description="合约代码列表 (ts_code 形态, 如 RB2410.SHF)"
    )
    start_date: DateField = Field(default=None, description="开始日期")
    end_date: DateField = Field(default=None, description="结束日期")
    limit: int = Field(
        default=1000, ge=1, le=10000, description="窗口内最新 N 行(按交易日截断)"
    )
    allow_experimental_data: bool = Field(
        default=False,
        description="显式允许 experimental 数据集进入研究态查询",
    )

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_query(self) -> Self:
        """倒置窗口拒绝 + 空合约列表拒绝(非缺省选择不得静默全量)."""
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            msg = (
                f"start_date ({self.start_date}) cannot be greater than "
                f"end_date ({self.end_date})"
            )
            raise ValueError(msg)
        if self.source_tickers is not None and not self.source_tickers:
            msg = "source_tickers must be non-empty when provided (omit for all)"
            raise ValueError(msg)
        return self


class FuturesBar(BaseModel):
    """
    期货合约日线响应模型（amount 万元）.

    Attributes:
        source_ticker: 合约代码 (ts_code 形态, 如 RB2410.SHF)
        trade_date: 交易日期 (YYYY-MM-DD, 中国交易日历)
        open: 开盘价 (可选; 停牌/无成交日 null)
        high: 最高价 (可选)
        low: 最低价 (可选)
        close: 收盘价 (可选)
        settle: 结算价 (可选)
        pre_settle: 昨结算价 (可选; 上市首日 null)
        volume: 成交量 (手)
        amount: 成交额 (万元)
        open_interest: 持仓量 (手)

    """

    source_ticker: str = Field(description="合约代码 (ts_code 形态)")
    trade_date: str = Field(description="交易日期")
    open: float | None = Field(default=None, description="开盘价")
    high: float | None = Field(default=None, description="最高价")
    low: float | None = Field(default=None, description="最低价")
    close: float | None = Field(default=None, description="收盘价")
    settle: float | None = Field(default=None, description="结算价")
    pre_settle: float | None = Field(default=None, description="昨结算价")
    volume: float | None = Field(default=None, description="成交量 (手)")
    amount: float | None = Field(default=None, description="成交额 (万元)")
    open_interest: float | None = Field(default=None, description="持仓量 (手)")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class FuturesContract(BaseModel):
    """
    期货合约身份响应模型（与日线同范围，含已到期合约）.

    Attributes:
        source_ticker: 合约代码 (ts_code 形态)
        symbol: 合约简称 (如 RB2410)
        exchange: 交易所 (SHFE/CZCE/DCE/INE/CFFEX/GFEX)
        fut_code: 品种代码 (如 RB)
        multiplier: 合约乘数
        list_date: 上市日期 (源端声明)
        delist_date: 到期日期 (源端声明; 可选)
        source: 来源 (如 tushare)
        knowledge_date: 快照摄取日

    """

    source_ticker: str = Field(description="合约代码 (ts_code 形态)")
    symbol: str = Field(description="合约简称")
    exchange: str = Field(description="交易所")
    fut_code: str = Field(description="品种代码")
    multiplier: float | None = Field(default=None, description="合约乘数")
    list_date: str = Field(description="上市日期")
    delist_date: str | None = Field(default=None, description="到期日期")
    source: str = Field(description="来源")
    knowledge_date: str = Field(description="快照摄取日")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class FuturesBarsResponse(BaseModel):
    """
    期货日线响应模型（语义+知界随行，DisclosureRowsResponse 同构）.

    Attributes:
        bars: 期货日线列表（同日多版本已收敛至最新 knowledge_date）
        read_semantics: 读取时间语义
        data_coverage: 数据集覆盖限制 (可选)

    """

    bars: list[FuturesBar] = Field(description="期货日线列表")
    read_semantics: ReadSemantics = Field(description="读取时间语义")
    data_coverage: DataCoverageInfo | None = Field(
        default=None, description="数据集覆盖限制"
    )

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class FuturesContractsResponse(BaseModel):
    """
    期货合约身份响应模型（语义+知界随行）.

    Attributes:
        contracts: 合约身份列表（与日线同范围，含已到期合约）
        read_semantics: 读取时间语义
        data_coverage: 数据集覆盖限制 (可选)

    """

    contracts: list[FuturesContract] = Field(description="合约身份列表")
    read_semantics: ReadSemantics = Field(description="读取时间语义")
    data_coverage: DataCoverageInfo | None = Field(
        default=None, description="数据集覆盖限制"
    )

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def _optional_float(value: object) -> float | None:
    """Polars 行值 → float | None（null 保真，不填 0）."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    converted = format_float(float(value))
    return None if converted is None else float(converted)


def to_futures_bar_list(df: pl.DataFrame) -> list[FuturesBar]:
    """期货日线帧 → FuturesBar 列表（null 保真）."""
    if df.is_empty():
        return []
    return [
        FuturesBar(
            source_ticker=row["source_ticker"],
            trade_date=format_date(row["trade_date"]) or "",
            open=_optional_float(row.get("open")),
            high=_optional_float(row.get("high")),
            low=_optional_float(row.get("low")),
            close=_optional_float(row.get("close")),
            settle=_optional_float(row.get("settle")),
            pre_settle=_optional_float(row.get("pre_settle")),
            volume=_optional_float(row.get("volume")),
            amount=_optional_float(row.get("amount")),
            open_interest=_optional_float(row.get("open_interest")),
        )
        for row in df.to_dicts()
    ]


def to_futures_contract_list(df: pl.DataFrame) -> list[FuturesContract]:
    """合约身份帧 → FuturesContract 列表（delist/multiplier null 保真）."""
    if df.is_empty():
        return []
    return [
        FuturesContract(
            source_ticker=row["source_ticker"],
            symbol=row["symbol"],
            exchange=row["exchange"],
            fut_code=row["fut_code"],
            multiplier=_optional_float(row.get("multiplier")),
            list_date=format_date(row["list_date"]) or "",
            delist_date=(
                format_date(row["delist_date"])
                if row.get("delist_date") is not None
                else None
            ),
            source=row.get("source") or "",
            knowledge_date=format_date(row.get("knowledge_date")) or "",
        )
        for row in df.to_dicts()
    ]
