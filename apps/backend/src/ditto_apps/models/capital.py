"""
Capital 域 API 模型.

包含:
- MarginQuery: 融资融券查询参数模型
- Margin: 融资融券响应模型
- ValuationQuery: 估值指标查询参数模型
- Valuation: 估值指标响应模型
- 转换函数
"""

from __future__ import annotations

from datetime import date
from datetime import date as dt_date
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ditto_apps.models.common import DataCoverageInfo


class MarginQuery(BaseModel):
    """
    融资融券查询参数模型.

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 时间点查询日期

    """

    instrument_id: int = Field(description="标的 ID")
    as_of_date: date = Field(description="时间点查询日期")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class Margin(BaseModel):
    """
    融资融券响应模型.

    Attributes:
        instrument_id: 标的 ID
        trade_date: 交易日期
        margin_buy_balance: 融资余额（元）
        short_sell_balance: 融券余额（元）
        margin_buy_amount: 融资买入额（元，#625 修正语义）
        margin_buy_volume: 融资买入额[元, int 截断废弃别名——原字段名语义
            误标, 保留以走响应字段新增的兼容通道; 移除须走废弃窗口]
        short_sell_volume: 融券卖出量（股/份/手，按标的类型各异）

    """

    instrument_id: int = Field(description="标的 ID")
    trade_date: str = Field(description="交易日期")
    margin_buy_balance: float = Field(description="融资余额")
    short_sell_balance: float = Field(description="融券余额")
    margin_buy_amount: float = Field(description="融资买入额")
    margin_buy_volume: int = Field(
        description="融资买入额[元, int 截断废弃别名, 用 margin_buy_amount]"
    )
    short_sell_volume: int = Field(description="融券卖出量")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def to_margin(row: dict[str, Any]) -> Margin:
    """
    将数据库行转换为 Margin 模型.

    Args:
        row: 数据库行字典，包含 instrument_id, trade_date, margin_buy_balance,
             short_sell_balance, margin_buy_amount, short_sell_volume 等字段

    Returns:
        Margin 模型实例

    """
    amount = float(row["margin_buy_amount"] or 0)
    return Margin(
        instrument_id=int(row["instrument_id"]),
        trade_date=row["trade_date"],
        margin_buy_balance=row["margin_buy_balance"],
        short_sell_balance=row["short_sell_balance"],
        margin_buy_amount=amount,
        margin_buy_volume=int(amount),
        short_sell_volume=int(row["short_sell_volume"] or 0),
    )


def to_margin_list(df: pl.DataFrame) -> list[Margin]:
    """
    将 DataFrame 转换为 Margin 列表.

    Args:
        df: 包含融资融券数据的 DataFrame

    Returns:
        Margin 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Margin] = []
    for row in df.to_dicts():
        result.append(to_margin(row))

    return result


class ValuationQuery(BaseModel):
    """
    估值指标查询参数模型.

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 时间点查询日期

    """

    instrument_id: int = Field(description="标的 ID")
    as_of_date: date = Field(description="时间点查询日期")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class Valuation(BaseModel):
    """
    估值指标响应模型.

    Attributes:
        instrument_id: 标的 ID
        trade_date: 交易日期
        pe_ratio: 市盈率 (可选)
        pb_ratio: 市净率
        ps_ratio: 市销率 (可选)
        dividend_yield: 股息率 (可选)
        market_cap: 市值

    """

    instrument_id: int = Field(description="标的 ID")
    trade_date: str = Field(description="交易日期")
    pe_ratio: float | None = Field(default=None, description="市盈率")
    pb_ratio: float = Field(description="市净率")
    ps_ratio: float | None = Field(default=None, description="市销率")
    dividend_yield: float | None = Field(default=None, description="股息率")
    market_cap: float = Field(description="市值")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def to_valuation(row: dict[str, Any]) -> Valuation:
    """
    将数据库行转换为 Valuation 模型.

    Args:
        row: 数据库行字典，包含 instrument_id, trade_date, pe_ratio, pb_ratio,
             ps_ratio, dividend_yield, market_cap 等字段

    Returns:
        Valuation 模型实例

    """
    return Valuation(
        instrument_id=int(row["instrument_id"]),
        trade_date=row["trade_date"],
        pe_ratio=row.get("pe_ratio"),
        pb_ratio=row.get("pb_ratio") or 0.0,
        ps_ratio=row.get("ps_ratio"),
        dividend_yield=row.get("dividend_yield"),
        market_cap=float(row.get("market_cap") or 0.0),
    )


def to_valuation_list(df: pl.DataFrame) -> list[Valuation]:
    """
    将 DataFrame 转换为 Valuation 列表.

    Args:
        df: 包含估值指标数据的 DataFrame

    Returns:
        Valuation 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Valuation] = []
    for row in df.to_dicts():
        result.append(to_valuation(row))

    return result


def _iso(value: object) -> str:
    """date/str → ISO 字符串（parquet 行 date 对象转 DTO 字符串；必非空列）."""
    if value is None:
        return ""
    if isinstance(value, dt_date):
        return value.isoformat()
    return str(value)


def to_moneyflow_rows(df: pl.DataFrame) -> list[MoneyflowRow]:
    """Moneyflow 帧转画像行（万元/手）."""
    if df.is_empty():
        return []
    return [
        MoneyflowRow(
            trade_date=_iso(row["trade_date"]),
            **{
                col: row.get(col)
                for col in (
                    "buy_sm_amount",
                    "buy_md_amount",
                    "buy_lg_amount",
                    "buy_elg_amount",
                    "sell_sm_amount",
                    "sell_md_amount",
                    "sell_lg_amount",
                    "sell_elg_amount",
                    "net_mf_amount",
                    "net_mf_vol",
                )
            },
        )
        for row in df.to_dicts()
    ]


def to_top_list_rows(df: pl.DataFrame) -> list[TopListRow]:
    """top_list 帧转画像行（事件按 reason 独立）."""
    if df.is_empty():
        return []
    return [
        TopListRow(
            trade_date=_iso(row["trade_date"]),
            reason=str(row["reason"]),
            **{
                col: row.get(col)
                for col in (
                    "close",
                    "pct_change",
                    "turnover_rate",
                    "amount",
                    "l_buy",
                    "l_sell",
                    "l_amount",
                    "net_amount",
                    "net_rate",
                    "amount_rate",
                )
            },
        )
        for row in df.to_dicts()
    ]


def to_top_inst_rows(df: pl.DataFrame) -> list[TopInstRow]:
    """top_inst 帧转画像行（单边 null 保真）."""
    if df.is_empty():
        return []
    return [
        TopInstRow(
            trade_date=_iso(row["trade_date"]),
            reason=str(row["reason"]),
            exalter=str(row["exalter"]),
            **{
                col: row.get(col)
                for col in ("side", "buy", "buy_rate", "sell", "sell_rate", "net_buy")
            },
        )
        for row in df.to_dicts()
    ]


__all__ = [
    "CapitalProfileQuery",
    "CapitalProfileResponse",
    "Margin",
    "MarginBlock",
    "MarginProfileRow",
    "MarginQuery",
    "MoneyflowBlock",
    "MoneyflowRow",
    "TopInstBlock",
    "TopInstRow",
    "TopListBlock",
    "TopListRow",
    "Valuation",
    "ValuationQuery",
    "to_margin",
    "to_margin_list",
    "to_valuation",
    "to_valuation_list",
]


# ---------------------------------------------------------------------------
# 个股资金画像（#658 批次3 首个真实流程）
# ---------------------------------------------------------------------------


_MAX_PROFILE_WINDOW_DAYS = 366


class CapitalProfileQuery(BaseModel):
    """个股资金画像查询参数(必需 moneyflow/top_list/top_inst＋可选两融)."""

    instrument_id: int | None = Field(
        default=None, description="标的 ID(与 ticker/standard_ticker 三选一)"
    )
    ticker: str | None = Field(
        default=None, description="内部代码(与 instrument_id/standard_ticker 三选一)"
    )
    standard_ticker: str | None = Field(
        default=None,
        description="标准代码,如 000001.SZ(与 instrument_id/ticker 三选一)",
    )
    start_date: date = Field(description="窗口起点")
    end_date: date = Field(description="窗口终点")
    allow_experimental_data: bool = Field(
        default=False,
        description="显式允许 experimental 数据集(资金画像四数据集均 experimental)",
    )

    @model_validator(mode="after")
    def _validate_window(self) -> CapitalProfileQuery:
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        if (self.end_date - self.start_date).days > _MAX_PROFILE_WINDOW_DAYS:
            raise ValueError(
                f"profile window must not exceed {_MAX_PROFILE_WINDOW_DAYS} days"
            )
        return self

    model_config = ConfigDict(extra="ignore")


class MoneyflowRow(BaseModel):
    """逐日资金流行(金额万元、量手;#518 口径)."""

    trade_date: str = Field(description="交易日期")
    buy_sm_amount: float | None = Field(default=None, description="小单买入金额(万元)")
    buy_md_amount: float | None = Field(default=None, description="中单买入金额(万元)")
    buy_lg_amount: float | None = Field(default=None, description="大单买入金额(万元)")
    buy_elg_amount: float | None = Field(
        default=None, description="特大单买入金额(万元)"
    )
    sell_sm_amount: float | None = Field(default=None, description="小单卖出金额(万元)")
    sell_md_amount: float | None = Field(default=None, description="中单卖出金额(万元)")
    sell_lg_amount: float | None = Field(default=None, description="大单卖出金额(万元)")
    sell_elg_amount: float | None = Field(
        default=None, description="特大单卖出金额(万元)"
    )
    net_mf_amount: float | None = Field(default=None, description="净流入额(万元)")
    net_mf_vol: float | None = Field(default=None, description="净流入量(手)")

    model_config = ConfigDict(strict=True, extra="ignore")


class TopListRow(BaseModel):
    """龙虎榜个股明细行(金额元;同日多 reason 独立成行)."""

    trade_date: str = Field(description="交易日期")
    reason: str = Field(description="上榜原因")
    close: float | None = Field(default=None, description="收盘价(元)")
    pct_change: float | None = Field(default=None, description="涨跌幅(%)")
    turnover_rate: float | None = Field(default=None, description="换手率(%)")
    amount: float | None = Field(default=None, description="总成交额(元)")
    l_buy: float | None = Field(default=None, description="龙虎榜买入额(元)")
    l_sell: float | None = Field(default=None, description="龙虎榜卖出额(元)")
    l_amount: float | None = Field(default=None, description="龙虎榜成交额(元)")
    net_amount: float | None = Field(default=None, description="龙虎榜净买入额(元)")
    net_rate: float | None = Field(default=None, description="净买入率(%)")
    amount_rate: float | None = Field(default=None, description="成交额占比(%)")

    model_config = ConfigDict(strict=True, extra="ignore")


class TopInstRow(BaseModel):
    """龙虎榜席位明细行(单边 null 保真;席位事件≠机构总仓位)."""

    trade_date: str = Field(description="交易日期")
    reason: str = Field(description="上榜原因")
    exalter: str = Field(description="营业部/席位名称")
    side: str | None = Field(default=None, description="0=买方席位 1=卖方席位")
    buy: float | None = Field(default=None, description="买入金额(元;卖方席位为 null)")
    buy_rate: float | None = Field(default=None, description="买入占比(%)")
    sell: float | None = Field(default=None, description="卖出金额(元;买方席位为 null)")
    sell_rate: float | None = Field(default=None, description="卖出占比(%)")
    net_buy: float | None = Field(default=None, description="净买入(元)")

    model_config = ConfigDict(strict=True, extra="ignore")


class MoneyflowBlock(BaseModel):
    """画像块:逐日资金流(latest_available＝库内现存行,无 PIT 过滤)."""

    rows: list[MoneyflowRow] = Field(default_factory=list)
    read_semantics: str = Field(default="latest_available")
    sources: list[str] = Field(
        default_factory=list, description="行来源(tushare/fuyao 等)"
    )
    latest_trade_date: str | None = Field(
        default=None, description="窗口内实际末端交易日(空窗为 null)"
    )
    data_coverage: DataCoverageInfo | None = None

    model_config = ConfigDict(strict=True, extra="ignore")


class TopListBlock(BaseModel):
    """画像块:龙虎榜事件(无事件＝合法空,不冒充失败)."""

    rows: list[TopListRow] = Field(default_factory=list)
    read_semantics: str = Field(default="latest_available")
    sources: list[str] = Field(default_factory=list, description="行来源")
    latest_trade_date: str | None = Field(default=None)
    data_coverage: DataCoverageInfo | None = None

    model_config = ConfigDict(strict=True, extra="ignore")


class TopInstBlock(BaseModel):
    """画像块:龙虎榜席位(与 top_list 同事件范围)."""

    rows: list[TopInstRow] = Field(default_factory=list)
    read_semantics: str = Field(default="latest_available")
    sources: list[str] = Field(default_factory=list, description="行来源")
    latest_trade_date: str | None = Field(default=None)
    data_coverage: DataCoverageInfo | None = None

    model_config = ConfigDict(strict=True, extra="ignore")


class MarginProfileRow(BaseModel):
    """画像两融行(余额可空:月末披露含 null 余额为真实形态,null 非 0)."""

    trade_date: str = Field(description="交易日期")
    margin_buy_balance: float | None = Field(default=None, description="融资余额(元)")
    short_sell_balance: float | None = Field(default=None, description="融券余额(元)")
    margin_buy_amount: float | None = Field(default=None, description="融资买入额(元)")
    short_sell_volume: float | None = Field(default=None, description="融券卖出量")

    model_config = ConfigDict(strict=True, extra="ignore")


def to_margin_profile_rows(df: pl.DataFrame) -> list[MarginProfileRow]:
    """Margin 帧转画像行(null 原样传播,correctness F1)."""
    if df.is_empty():
        return []
    return [
        MarginProfileRow(
            trade_date=_iso(row["trade_date"]),
            margin_buy_balance=row.get("margin_buy_balance"),
            short_sell_balance=row.get("short_sell_balance"),
            margin_buy_amount=row.get("margin_buy_amount"),
            short_sell_volume=row.get("short_sell_volume"),
        )
        for row in df.to_dicts()
    ]


class MarginBlock(BaseModel):
    """画像块:两融(pit_asof=end_date;迟发数据按 09:15 承诺显示待补)."""

    rows: list[MarginProfileRow] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list, description="行来源")
    read_error: str | None = Field(
        default=None,
        description="可选块读取失败原因(受限展示,其余块不受影响)",
    )
    read_semantics: str = Field(default="pit_asof")
    latest_trade_date: str | None = Field(default=None)
    pending_trade_dates: list[str] = Field(
        default_factory=list,
        description="窗口内已有两融历史但缺失的交易日(迟发待补;无历史=非两融标的不适用)",
    )
    freshness_promise: str = Field(
        default="交易所于下一交易日开市前(约09:15)公布前一交易日两融数据",
        description="披露制度承诺(新鲜度承诺,非 PIT 能力)",
    )
    data_coverage: DataCoverageInfo | None = None

    model_config = ConfigDict(strict=True, extra="ignore")


class CapitalProfileResponse(BaseModel):
    """个股资金画像响应(四数据集同标的同窗口联看)."""

    instrument_id: int = Field(description="标的 ID")
    window: dict[str, str] = Field(description="查询窗口 {start, end}")
    moneyflow: MoneyflowBlock = Field(description="逐日资金流(必需)")
    top_list: TopListBlock = Field(description="龙虎榜事件(必需)")
    top_inst: TopInstBlock = Field(description="龙虎榜席位(必需)")
    margin_trading: MarginBlock = Field(description="两融(可选,带待补语义)")

    model_config = ConfigDict(strict=True, extra="ignore")
