"""
InstrumentDefinition / TradingRuleSet / FeeSchedule — 三层规则数据对象 (R6).

值对象和 Protocol 已迁移至 ditto_kernel.trading，本模块 re-export 并保留
InMemoryRuleProvider（测试工具，超出 kernel 薄实现 30 行限制）。
"""

from __future__ import annotations

from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRuleProvider,
    InstrumentRules,
    RulesGetter,
    TradingRuleSet,
    default_price_limit_pct,
)

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


# ---------------------------------------------------------------------------
# InMemoryRuleProvider — 测试工具，保留在 execution 层
# ---------------------------------------------------------------------------


class InMemoryRuleProvider:
    """
    内存版规则提供者 — 用于单元测试和集成测试。

    构造时传入 definitions / trading_rules / fee_schedules dict。
    trading_rules 和 fee_schedules 支持多版本（按 as_of_date PIT 查询）。
    """

    def __init__(
        self,
        definitions: dict[InstrumentId, InstrumentDefinition] | None = None,
        trading_rules: dict[InstrumentId, list[TradingRuleSet]] | None = None,
        fee_schedules: dict[InstrumentId, list[FeeSchedule]] | None = None,
    ) -> None:
        self._definitions = definitions or {}
        self._trading_rules = trading_rules or {}
        self._fee_schedules = fee_schedules or {}

    # -- query methods -------------------------------------------------------

    def get_definition(
        self,
        instrument_id: InstrumentId,
    ) -> InstrumentDefinition | None:
        """获取标的静态定义，不存在返回 None。"""
        return self._definitions.get(instrument_id)

    def get_trading_rule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> TradingRuleSet | None:
        """PIT 查询交易规则，不存在返回 None。"""
        return self._find_pit(self._trading_rules, instrument_id, as_of_date)

    def get_fee_schedule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> FeeSchedule | None:
        """PIT 查询费率，不存在返回 None。"""
        return self._find_pit(self._fee_schedules, instrument_id, as_of_date)

    def get_rules(
        self,
        as_of_date: str,
        instrument_ids: list[InstrumentId],
    ) -> dict[InstrumentId, InstrumentRules]:
        """批量获取三层规则。缺失规则返回空 dict（不 raise）。"""
        result: dict[InstrumentId, InstrumentRules] = {}
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
        store: dict[InstrumentId, list[T]],
        instrument_id: InstrumentId,
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
            if ef is None or ef > as_of_date:
                continue
            et = getattr(rec, "effective_to", None)
            if et is not None and et <= as_of_date:
                continue
            candidates.append(rec)

        if not candidates:
            return None

        # 按 as_of_date 降序取最新
        candidates.sort(key=lambda r: getattr(r, "as_of_date", ""), reverse=True)
        return candidates[0]
