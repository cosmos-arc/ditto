"""
InstrumentRuleProvider -- 三层规则组装层 (R6).

从 PIT Store 查询 TradingRuleRecord / FeeScheduleRecord / DefinitionRecord，
由调用方完成 Record → Core 模型的转换。

V1: 内存实现，后续接入真实 Data 存储后替换。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_kernel.identity import InstrumentId as _InstrumentId

from ditto_data.storage.metadata.fee_schedule_reader import (
    FeeScheduleReader,
    FeeScheduleRecord,
)
from ditto_data.storage.metadata.fee_schedule_writer import FeeScheduleWriter
from ditto_data.storage.metadata.trading_rule_reader import (
    TradingRuleReader,
    TradingRuleRecord,
)
from ditto_data.storage.metadata.trading_rule_writer import TradingRuleWriter

InstrumentId = _InstrumentId

__all__ = ["DefinitionRecord", "InstrumentRuleProvider"]


@dataclass(frozen=True)
class DefinitionRecord:
    """
    标的静态定义（Data Record，由调用方转换为 Core InstrumentDefinition）.

    Attributes:
        instrument_id: 标的 ID.
        asset_class: 资产类别 (stock / etf / index / future / ...).
        exchange: 交易所 (XSHE / XSHG / XBSE).
        currency: 货币 (CNY).
        tick_size: 最小价格变动.
        lot_size: 最小手数 (A股=100).
        multiplier: 合约乘数 (股票/ETF=1).
        board_segment: 板块 (main / gem / star / bse).
        lifecycle_state: 生命周期 (normal / st / st_star / delisting / ipo).

    """

    instrument_id: InstrumentId
    asset_class: str
    exchange: str
    currency: str
    tick_size: float
    lot_size: int
    multiplier: float
    board_segment: str
    lifecycle_state: str


# 三层规则元组类型
InstrumentRules = tuple[DefinitionRecord, TradingRuleRecord, FeeScheduleRecord]


class InstrumentRuleProvider:
    """
    三层规则查询（返回 Record，由调用方转换为 Core 模型）。

    V1: 内存实现。后续从 Data metadata service 读取。

    Attributes:
        _definitions: instrument_id -> dict 映射（V1 内存）。
        _trading_rule_reader: PIT 版本化交易规则 Reader。
        _fee_schedule_reader: PIT 版本化费率 Reader。
        _trading_rule_writer: PIT Writer（与 Reader 共享 backing store）。
        _fee_schedule_writer: PIT Writer（与 Reader 共享 backing store）。

    """

    def __init__(
        self,
        trading_rule_reader: TradingRuleReader | None = None,
        fee_schedule_reader: FeeScheduleReader | None = None,
    ) -> None:
        self._definitions: dict[InstrumentId, DefinitionRecord] = {}
        # 创建共享 backing store 的 Reader/Writer 对
        if trading_rule_reader is not None:
            self._trading_rule_reader = trading_rule_reader
            self._trading_rule_store = trading_rule_reader.backing_store
        else:
            self._trading_rule_store: list[TradingRuleRecord] = []
            self._trading_rule_reader = TradingRuleReader(
                backing_store=self._trading_rule_store,
            )
        if fee_schedule_reader is not None:
            self._fee_schedule_reader = fee_schedule_reader
            self._fee_schedule_store = fee_schedule_reader.backing_store
        else:
            self._fee_schedule_store: list[FeeScheduleRecord] = []
            self._fee_schedule_reader = FeeScheduleReader(
                backing_store=self._fee_schedule_store,
            )

    # ── 加载方法（V1 测试用，生产环境从存储读取）──

    def load_definition(self, definition: DefinitionRecord) -> None:
        """加载单个标的定义."""
        self._definitions[definition.instrument_id] = definition

    def load_trading_rules(self, records: list[TradingRuleRecord]) -> None:
        """加载交易规则记录列表."""
        writer = TradingRuleWriter(backing_store=self._trading_rule_store)
        for rec in records:
            writer.write(rec)

    def load_fee_schedules(self, records: list[FeeScheduleRecord]) -> None:
        """加载费率记录列表."""
        writer = FeeScheduleWriter(backing_store=self._fee_schedule_store)
        for rec in records:
            writer.write(rec)

    # ── 查询方法 ──

    def get_definition(self, instrument_id: InstrumentId) -> DefinitionRecord | None:
        """获取标的静态定义，不存在返回 None."""
        return self._definitions.get(instrument_id)

    def get_trading_rule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> TradingRuleRecord | None:
        """PIT 查询交易规则，不存在返回 None."""
        return self._trading_rule_reader.get(instrument_id, as_of_date)

    def get_fee_schedule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> FeeScheduleRecord | None:
        """PIT 查询费率，不存在返回 None."""
        return self._fee_schedule_reader.get(instrument_id, as_of_date)

    def get_rules(
        self,
        as_of_date: str,
        instrument_ids: list[InstrumentId],
    ) -> dict[InstrumentId, InstrumentRules]:
        """
        批量获取三层规则（返回 Record，由调用方转换为 Core 模型）.

        Args:
            as_of_date: 查询时间点 (YYYY-MM-DD).
            instrument_ids: 标的 ID 列表.

        Returns:
            {instrument_id: (DefinitionRecord, TradingRuleRecord, FeeScheduleRecord)}

        Raises:
            ValueError: 某个标的缺少规则数据.

        """
        result: dict[InstrumentId, InstrumentRules] = {}
        for iid in instrument_ids:
            defn = self.get_definition(iid)
            trading_rule = self.get_trading_rule(iid, as_of_date)
            fee = self.get_fee_schedule(iid, as_of_date)
            if defn is None:
                raise ValueError(f"InstrumentDefinition not found: {iid}")
            if trading_rule is None:
                msg = f"TradingRuleRecord not found for {iid} @ {as_of_date}"
                raise ValueError(msg)
            if fee is None:
                msg = f"FeeScheduleRecord not found for {iid} @ {as_of_date}"
                raise ValueError(msg)
            result[iid] = (defn, trading_rule, fee)
        return result
