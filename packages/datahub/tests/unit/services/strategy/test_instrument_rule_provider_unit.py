"""Tests for InstrumentRuleProvider — 三层规则组装."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from ditto_datahub.services.strategy.instrument_rule_provider import (
    DefinitionRecord,
    InstrumentRuleProvider,
)
from ditto_datahub.stores.metadata.fee_schedule_reader import (
    FeeScheduleReader,
    FeeScheduleRecord,
)
from ditto_datahub.stores.metadata.trading_rule_reader import (
    TradingRuleReader,
    TradingRuleRecord,
)

_DEF_DEFAULTS: dict[str, object] = {
    "instrument_id": "159915.SZ",
    "asset_class": "etf",
    "exchange": "XSHE",
    "currency": "CNY",
    "tick_size": 0.001,
    "lot_size": 100,
    "multiplier": 1.0,
    "board_segment": "main",
    "lifecycle_state": "normal",
}

_RULE_DEFAULTS: dict[str, object] = {
    "instrument_id": "159915.SZ",
    "as_of_date": "2026-01-01",
    "settlement_cycle": 1,
    "fund_settlement_cycle": 1,
    "price_limit_pct": 0.10,
    "order_types_supported": ("market", "limit"),
    "call_auction_sessions": ("open", "close"),
    "effective_from": "2026-01-01",
    "effective_to": None,
}

_FEE_DEFAULTS: dict[str, object] = {
    "instrument_id": "159915.SZ",
    "as_of_date": "2026-01-01",
    "commission_rate": 0.0003,
    "min_commission": 5.0,
    "stamp_duty_rate": 0.0,
    "transfer_fee_rate": 0.0,
    "effective_from": "2026-01-01",
    "effective_to": None,
}


def _make_def(**overrides: object) -> DefinitionRecord:
    return DefinitionRecord(**{**_DEF_DEFAULTS, **overrides})


def _make_rule(**overrides: object) -> TradingRuleRecord:
    return TradingRuleRecord(**{**_RULE_DEFAULTS, **overrides})


def _make_fee(**overrides: object) -> FeeScheduleRecord:
    return FeeScheduleRecord(**{**_FEE_DEFAULTS, **overrides})


class TestDefinitionRecord:
    def test_create_record(self) -> None:
        record = _make_def(instrument_id="159915.SZ")
        assert record.instrument_id == "159915.SZ"
        assert record.lot_size == 100

    def test_record_is_frozen(self) -> None:
        record = _make_def()
        with pytest.raises(FrozenInstanceError):
            record.lot_size = 200  # type: ignore[misc]


class TestInstrumentRuleProvider:
    def test_get_definition(self) -> None:
        provider = InstrumentRuleProvider()
        provider.load_definition(_make_def(instrument_id="159915.SZ"))
        defn = provider.get_definition("159915.SZ")
        assert defn is not None
        assert defn.lot_size == 100

    def test_get_definition_not_found(self) -> None:
        provider = InstrumentRuleProvider()
        assert provider.get_definition("NONEXISTENT") is None

    def test_get_trading_rule(self) -> None:
        provider = InstrumentRuleProvider()
        provider.load_trading_rules([_make_rule()])
        rule = provider.get_trading_rule("159915.SZ", "2026-01-15")
        assert isinstance(rule, TradingRuleRecord)
        assert rule.settlement_cycle == 1

    def test_get_fee_schedule(self) -> None:
        provider = InstrumentRuleProvider()
        provider.load_fee_schedules([_make_fee()])
        fee = provider.get_fee_schedule("159915.SZ", "2026-01-15")
        assert isinstance(fee, FeeScheduleRecord)
        assert fee.commission_rate == pytest.approx(0.0003)

    def test_get_rules_batch(self) -> None:
        provider = InstrumentRuleProvider()
        provider.load_definition(_make_def(instrument_id="159915.SZ"))
        provider.load_definition(_make_def(instrument_id="510300.SH"))
        provider.load_trading_rules(
            [
                _make_rule(instrument_id="159915.SZ"),
                _make_rule(instrument_id="510300.SH"),
            ]
        )
        provider.load_fee_schedules(
            [
                _make_fee(instrument_id="159915.SZ"),
                _make_fee(instrument_id="510300.SH"),
            ]
        )

        rules = provider.get_rules("2026-01-15", ["159915.SZ", "510300.SH"])
        assert len(rules) == 2
        assert "159915.SZ" in rules
        assert "510300.SH" in rules

        defn, trading_rule, fee = rules["159915.SZ"]
        assert defn.lot_size == 100
        assert trading_rule.settlement_cycle == 1
        assert fee.commission_rate == pytest.approx(0.0003)

    def test_get_rules_missing_definition_raises(self) -> None:
        """get_rules 缺少 DefinitionRecord 时抛出 ValueError."""
        provider = InstrumentRuleProvider()
        provider.load_trading_rules([_make_rule()])
        provider.load_fee_schedules([_make_fee()])
        with pytest.raises(ValueError, match="InstrumentDefinition not found"):
            provider.get_rules("2026-01-15", ["159915.SZ"])

    def test_get_rules_missing_trading_rule_raises(self) -> None:
        """get_rules 缺少 TradingRuleRecord 时抛出 ValueError."""
        provider = InstrumentRuleProvider()
        provider.load_definition(_make_def())
        provider.load_fee_schedules([_make_fee()])
        with pytest.raises(ValueError, match="TradingRuleRecord not found"):
            provider.get_rules("2026-01-15", ["159915.SZ"])

    def test_get_rules_missing_fee_schedule_raises(self) -> None:
        """get_rules 缺少 FeeScheduleRecord 时抛出 ValueError."""
        provider = InstrumentRuleProvider()
        provider.load_definition(_make_def())
        provider.load_trading_rules([_make_rule()])
        with pytest.raises(ValueError, match="FeeScheduleRecord not found"):
            provider.get_rules("2026-01-15", ["159915.SZ"])

    def test_dependency_injection(self) -> None:
        """验证构造函数支持注入自定义 Reader."""
        trading_reader = TradingRuleReader()
        fee_reader = FeeScheduleReader()
        provider = InstrumentRuleProvider(
            trading_rule_reader=trading_reader,
            fee_schedule_reader=fee_reader,
        )
        assert provider._trading_rule_reader is trading_reader
        assert provider._fee_schedule_reader is fee_reader

    def test_get_rules_empty_list_returns_empty(self) -> None:
        """get_rules 传入空列表应返回空字典."""
        provider = InstrumentRuleProvider()
        assert provider.get_rules("2026-01-15", []) == {}
