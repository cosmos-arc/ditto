"""
InstrumentDefinition / TradingRuleSet / FeeSchedule — 三层规则数据对象 (R6).

- InstrumentDefinition: 静态资产属性（很少变化）
- TradingRuleSet: 可变交易规则（PIT 版本化，effective_from / effective_to）
- FeeSchedule: 可变费用结构（PIT 版本化）
- InstrumentRules: 三层规则元组类型别名
- InstrumentRuleProvider: Protocol + InMemoryRuleProvider
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

__all__ = [
    "FeeSchedule",
    "InMemoryRuleProvider",
    "InstrumentDefinition",
    "InstrumentRuleProvider",
    "InstrumentRules",
    "RulesGetter",
    "TradingRuleSet",
    "default_price_limit_pct",
]


@dataclass(frozen=True)
class InstrumentDefinition:
    """
    资产的静态定义 — 很少变化，不按日期生效。

    Attributes:
        instrument_id: 标的 ID
        asset_class: 资产类别 (stock / etf / index / future / ...)
        exchange: 交易所 (XSHE / XSHG / XBSE)
        currency: 货币 (CNY)
        tick_size: 最小价格变动
        lot_size: 最小手数 (A股=100)
        multiplier: 合约乘数 (股票/ETF=1)
        board_segment: 板块 (main / gem / star / bse)
        lifecycle_state: 生命周期 (normal / st / st_star / delisting / ipo)
        ipo_date: 上市日期 (YYYY-MM-DD)，None 表示未知
        delisting_date: 退市日期 (YYYY-MM-DD)，None 表示未退市

    """

    instrument_id: str
    asset_class: str
    exchange: str
    currency: str
    tick_size: float
    lot_size: int
    multiplier: float
    board_segment: str
    lifecycle_state: str
    ipo_date: str | None = None
    delisting_date: str | None = None


@dataclass(frozen=True)
class TradingRuleSet:
    """
    某个标的在某个时间点的交易规则 — 按日期生效，可回放。

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 规则生效日期 (YYYY-MM-DD)
        settlement_cycle: T+N 的 N（1=次日可卖, 0=当日可卖）
        fund_settlement_cycle: 资金交收 T+N
        price_limit_pct: 涨跌停限制 (None=无限制，如新股前5日)
        order_types_supported: 支持的订单类型
        call_auction_sessions: 集合竞价时段

    """

    instrument_id: str
    as_of_date: str
    settlement_cycle: int
    fund_settlement_cycle: int
    price_limit_pct: float | None
    order_types_supported: tuple[str, ...]
    call_auction_sessions: tuple[str, ...]


@dataclass(frozen=True)
class FeeSchedule:
    """
    某个标的在某个时间点的费用结构 — 按日期生效。

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 生效日期 (YYYY-MM-DD)
        commission_rate: 佣金费率
        min_commission: 最低佣金 (A股=5元)
        stamp_duty_rate: 印花税率 (ETF=0, 股票=0.0005 卖出)
        transfer_fee_rate: 过户费率 (ETF=0, 股票=0.00001)

    """

    instrument_id: str
    as_of_date: str
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float


# ---------------------------------------------------------------------------
# Type Aliases
# ---------------------------------------------------------------------------

type InstrumentRules = tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]
"""三层规则元组 — (定义, 交易规则, 费用结构)。"""

type RulesGetter = Callable[[str, str], InstrumentRules]
"""规则获取函数 — (instrument_id, trade_date) → InstrumentRules。"""


# ---------------------------------------------------------------------------
# Lifecycle → Price Limit Mapping
# ---------------------------------------------------------------------------


def default_price_limit_pct(
    lifecycle_state: str,
    board_segment: str,
) -> float | None:
    """
    根据 lifecycle_state 和 board_segment 计算默认涨跌停幅度。

    - ST / ST_STAR: 5%
    - 退市整理期 (delisting): 10%
    - 主板 (main / bse): 10%
    - 创业板 (gem) / 科创板 (star): 20%
    - IPO 前五日 (ipo): None (无涨跌停)

    """
    if lifecycle_state in ("st", "st_star"):
        return 0.05
    if lifecycle_state == "delisting":
        return 0.10
    if lifecycle_state == "ipo":
        return None
    if board_segment in ("gem", "star"):
        return 0.20
    return 0.10


# ---------------------------------------------------------------------------
# InstrumentRuleProvider Protocol
# ---------------------------------------------------------------------------


class InstrumentRuleProvider(Protocol):
    """
    三层规则查询 Protocol — Core 层接口，无 I/O。

    Core 层定义 Protocol + InMemoryRuleProvider 内存实现，
    DataHub 层实现 PIT 版本（InstrumentRuleProvider → Record 转换）。

    """

    def get_definition(
        self,
        instrument_id: str,
    ) -> InstrumentDefinition | None:
        """获取标的静态定义，不存在返回 None。"""
        ...

    def get_trading_rule(
        self,
        instrument_id: str,
        as_of_date: str,
    ) -> TradingRuleSet | None:
        """PIT 查询交易规则，不存在返回 None。"""
        ...

    def get_fee_schedule(
        self,
        instrument_id: str,
        as_of_date: str,
    ) -> FeeSchedule | None:
        """PIT 查询费率，不存在返回 None。"""
        ...

    def get_rules(
        self,
        as_of_date: str,
        instrument_ids: list[str],
    ) -> dict[str, InstrumentRules]:
        """批量获取三层规则。缺失规则返回空 dict（不 raise）。"""
        ...


# ---------------------------------------------------------------------------
# InMemoryRuleProvider
# ---------------------------------------------------------------------------


class InMemoryRuleProvider:
    """
    内存版规则提供者 — 用于单元测试和集成测试。

    构造时传入 definitions / trading_rules / fee_schedules dict。
    trading_rules 和 fee_schedules 支持多版本（按 as_of_date PIT 查询）。
    """

    def __init__(
        self,
        definitions: dict[str, InstrumentDefinition] | None = None,
        trading_rules: dict[str, list[TradingRuleSet]] | None = None,
        fee_schedules: dict[str, list[FeeSchedule]] | None = None,
    ) -> None:
        self._definitions = definitions or {}
        self._trading_rules = trading_rules or {}
        self._fee_schedules = fee_schedules or {}

    # -- query methods -------------------------------------------------------

    def get_definition(
        self,
        instrument_id: str,
    ) -> InstrumentDefinition | None:
        """获取标的静态定义，不存在返回 None。"""
        return self._definitions.get(instrument_id)

    def get_trading_rule(
        self,
        instrument_id: str,
        as_of_date: str,
    ) -> TradingRuleSet | None:
        """PIT 查询交易规则，不存在返回 None。"""
        return self._find_pit(self._trading_rules, instrument_id, as_of_date)

    def get_fee_schedule(
        self,
        instrument_id: str,
        as_of_date: str,
    ) -> FeeSchedule | None:
        """PIT 查询费率，不存在返回 None。"""
        return self._find_pit(self._fee_schedules, instrument_id, as_of_date)

    def get_rules(
        self,
        as_of_date: str,
        instrument_ids: list[str],
    ) -> dict[str, InstrumentRules]:
        """批量获取三层规则。缺失规则返回空 dict（不 raise）。"""
        result: dict[str, InstrumentRules] = {}
        for iid in instrument_ids:
            defn = self.get_definition(iid)
            rule = self.get_trading_rule(iid, as_of_date)
            fee = self.get_fee_schedule(iid, as_of_date)
            if defn is not None and rule is not None and fee is not None:
                result[iid] = (defn, rule, fee)
        return result

    # -- internal -----------------------------------------------------------

    @staticmethod
    def _find_pit[T](
        store: dict[str, list[T]],
        instrument_id: str,
        as_of_date: str,
    ) -> T | None:
        """
        按 effective_from <= as_of_date 查找最新版本。

        effective_to 语义遵循 PIT 规范：effective_to > as_of_date 包含。
        """
        records = store.get(instrument_id)
        if not records:
            return None

        candidates: list[T] = []
        for rec in records:
            ef = getattr(rec, "as_of_date", None)
            if ef is not None and ef <= as_of_date:
                candidates.append(rec)

        if not candidates:
            return None

        # 按 as_of_date 降序取最新
        candidates.sort(key=lambda r: getattr(r, "as_of_date", ""), reverse=True)
        return candidates[0]
