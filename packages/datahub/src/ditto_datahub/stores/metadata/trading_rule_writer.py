"""TradingRuleWriter -- PIT 版本化交易规则写入."""

from __future__ import annotations

from ditto_datahub.stores.metadata._pit_base import PITRecordWriter
from ditto_datahub.stores.metadata.trading_rule_reader import TradingRuleRecord

__all__ = ["TradingRuleWriter"]


class TradingRuleWriter(PITRecordWriter[TradingRuleRecord]):
    """交易规则 Writer. V1 内存实现."""
