"""Tests for InstrumentDefinition / TradingRuleSet / FeeSchedule (R6 三层分离).

Part 07: InstrumentRuleProvider Protocol + InMemoryRuleProvider.
Part 08: default_price_limit_pct lifecycle mapping.
"""

from dataclasses import FrozenInstanceError, dataclass

import pytest
from ditto_execution.rules import InMemoryRuleProvider
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRuleProvider,
    TradingRuleSet,
    default_price_limit_pct,
)

# ---------------------------------------------------------------------------
# Shared fixture data — avoids repeating identical construction 3x each.
# ---------------------------------------------------------------------------

ETF_DEFINITION = InstrumentDefinition(
    instrument_id=1,
    asset_class="etf",
    exchange="XSHE",
    currency="CNY",
    tick_size=0.001,
    lot_size=100,
    multiplier=1.0,
    board_segment="main",
    lifecycle_state="normal",
)

STOCK_DEFINITION = InstrumentDefinition(
    instrument_id=2,
    asset_class="stock",
    exchange="XSHG",
    currency="CNY",
    tick_size=0.01,
    lot_size=100,
    multiplier=1.0,
    board_segment="main",
    lifecycle_state="normal",
)

TRADING_RULE = TradingRuleSet(
    instrument_id=1,
    as_of_date="2026-01-01",
    settlement_cycle=1,
    fund_settlement_cycle=1,
    price_limit_pct=0.10,
    order_types_supported=("market", "limit"),
    call_auction_sessions=("open", "close"),
)

ETF_FEE = FeeSchedule(
    instrument_id=1,
    as_of_date="2026-01-01",
    commission_rate=0.0003,
    min_commission=5.0,
    stamp_duty_rate=0.0,
    transfer_fee_rate=0.0,
)


class TestInstrumentDefinition:
    def test_create_etf_definition(self) -> None:
        assert ETF_DEFINITION.asset_class == "etf"
        assert ETF_DEFINITION.lot_size == 100
        assert ETF_DEFINITION.tick_size == 0.001

    def test_create_stock_definition(self) -> None:
        assert STOCK_DEFINITION.asset_class == "stock"
        assert STOCK_DEFINITION.tick_size == 0.01

    def test_is_frozen(self) -> None:
        with pytest.raises(FrozenInstanceError):
            ETF_DEFINITION.lot_size = 1  # type: ignore[misc]

    def test_st_lifecycle(self) -> None:
        defn = InstrumentDefinition(
            instrument_id=3,
            asset_class="stock",
            exchange="XSHG",
            currency="CNY",
            tick_size=0.01,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="st",
        )
        assert defn.lifecycle_state == "st"

    def test_new_fields_default_to_none(self) -> None:
        """ipo_date / delisting_date 默认为 None（向后兼容）。"""
        defn = InstrumentDefinition(
            instrument_id=2,
            asset_class="stock",
            exchange="XSHG",
            currency="CNY",
            tick_size=0.01,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        )
        assert defn.ipo_date is None
        assert defn.delisting_date is None

    def test_new_fields_with_values(self) -> None:
        """可显式传入 ipo_date / delisting_date。"""
        defn = InstrumentDefinition(
            instrument_id=2,
            asset_class="stock",
            exchange="XSHG",
            currency="CNY",
            tick_size=0.01,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
            ipo_date="2020-01-15",
            delisting_date="2026-06-30",
        )
        assert defn.ipo_date == "2020-01-15"
        assert defn.delisting_date == "2026-06-30"

    def test_ipo_date_only(self) -> None:
        """只传 ipo_date 时 delisting_date 保持 None。"""
        defn = InstrumentDefinition(
            instrument_id=1,
            asset_class="etf",
            exchange="XSHE",
            currency="CNY",
            tick_size=0.001,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
            ipo_date="2012-03-26",
        )
        assert defn.ipo_date == "2012-03-26"
        assert defn.delisting_date is None


class TestTradingRuleSet:
    def test_create_with_pit_fields(self) -> None:
        assert TRADING_RULE.settlement_cycle == 1
        assert TRADING_RULE.price_limit_pct == 0.10

    def test_no_price_limit(self) -> None:
        rule = TradingRuleSet(
            instrument_id=4,
            as_of_date="2026-01-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=None,
            order_types_supported=("market", "limit"),
            call_auction_sessions=("open", "close"),
        )
        assert rule.price_limit_pct is None

    def test_is_frozen(self) -> None:
        with pytest.raises(FrozenInstanceError):
            TRADING_RULE.settlement_cycle = 0  # type: ignore[misc]


class TestFeeSchedule:
    def test_create_etf_fee(self) -> None:
        assert ETF_FEE.stamp_duty_rate == 0.0

    def test_create_stock_fee(self) -> None:
        fee = FeeSchedule(
            instrument_id=2,
            as_of_date="2026-01-01",
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
        )
        assert fee.stamp_duty_rate == 0.0005
        assert fee.transfer_fee_rate == 0.00001

    def test_is_frozen(self) -> None:
        with pytest.raises(FrozenInstanceError):
            ETF_FEE.commission_rate = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# InstrumentRuleProvider Protocol
# ---------------------------------------------------------------------------


class TestInstrumentRuleProviderProtocol:
    """Protocol 定义验证。"""

    def test_protocol_has_required_methods(self) -> None:
        """Protocol 定义了四个核心查询方法。"""
        methods = [m for m in dir(InstrumentRuleProvider) if not m.startswith("_")]
        assert "get_definition" in methods
        assert "get_trading_rule" in methods
        assert "get_fee_schedule" in methods
        assert "get_rules" in methods

    def test_in_memory_satisfies_protocol(self) -> None:
        """InMemoryRuleProvider 满足 InstrumentRuleProvider Protocol。"""
        InMemoryRuleProvider()


# ---------------------------------------------------------------------------
# InMemoryRuleProvider — 基本查询
# ---------------------------------------------------------------------------


class TestInMemoryRuleProviderBasic:
    """InMemoryRuleProvider 基本 dict 查询。"""

    def test_get_definition_found(self) -> None:
        provider = InMemoryRuleProvider(definitions={100: ETF_DEFINITION})
        result = provider.get_definition(100)
        assert result is not None
        assert result.instrument_id == 1

    def test_get_definition_not_found(self) -> None:
        provider = InMemoryRuleProvider()
        assert provider.get_definition(999) is None

    def test_get_trading_rule_found(self) -> None:
        provider = InMemoryRuleProvider(
            trading_rules={1: [TRADING_RULE]},
        )
        result = provider.get_trading_rule(1, "2026-01-05")
        assert result is not None
        assert result.settlement_cycle == 1

    def test_get_trading_rule_not_found(self) -> None:
        provider = InMemoryRuleProvider()
        assert provider.get_trading_rule(999, "2026-01-05") is None

    def test_get_fee_schedule_found(self) -> None:
        provider = InMemoryRuleProvider(
            fee_schedules={1: [ETF_FEE]},
        )
        result = provider.get_fee_schedule(1, "2026-01-05")
        assert result is not None
        assert result.commission_rate == 0.0003

    def test_get_fee_schedule_not_found(self) -> None:
        provider = InMemoryRuleProvider()
        assert provider.get_fee_schedule(999, "2026-01-05") is None


# ---------------------------------------------------------------------------
# InMemoryRuleProvider — get_rules 批量查询
# ---------------------------------------------------------------------------


class TestInMemoryRuleProviderGetRules:
    """get_rules 批量查询。"""

    def test_get_rules_all_found(self) -> None:
        provider = InMemoryRuleProvider(
            definitions={100: ETF_DEFINITION},
            trading_rules={100: [TRADING_RULE]},
            fee_schedules={100: [ETF_FEE]},
        )
        result = provider.get_rules("2026-01-05", [100])
        assert 100 in result
        defn, rule, fee = result[100]
        assert defn.instrument_id == 1
        assert rule.settlement_cycle == 1
        assert fee.commission_rate == 0.0003

    def test_get_rules_missing_definition_skipped(self) -> None:
        """缺少 definition 的标的不出现在结果中。"""
        provider = InMemoryRuleProvider(
            definitions={},
            trading_rules={100: [TRADING_RULE]},
            fee_schedules={100: [ETF_FEE]},
        )
        result = provider.get_rules("2026-01-05", [100])
        assert 100 not in result

    def test_get_rules_missing_rule_skipped(self) -> None:
        """缺少 trading_rule 的标的不出现在结果中。"""
        provider = InMemoryRuleProvider(
            definitions={100: ETF_DEFINITION},
            trading_rules={},
            fee_schedules={100: [ETF_FEE]},
        )
        result = provider.get_rules("2026-01-05", [100])
        assert 100 not in result

    def test_get_rules_empty_ids(self) -> None:
        provider = InMemoryRuleProvider()
        result = provider.get_rules("2026-01-05", [])
        assert result == {}


# ---------------------------------------------------------------------------
# InMemoryRuleProvider — PIT 版本选择
# ---------------------------------------------------------------------------


class TestInMemoryRuleProviderPIT:
    """PIT 版本选择 — 按 as_of_date 查找最新生效版本。"""

    def test_pit_selects_latest_before_date(self) -> None:
        """as_of_date 选择 <= 该日期的最新版本。"""
        rule_v1 = TradingRuleSet(
            instrument_id=100,
            as_of_date="2026-01-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market",),
            call_auction_sessions=("open",),
        )
        rule_v2 = TradingRuleSet(
            instrument_id=100,
            as_of_date="2026-03-01",
            settlement_cycle=0,  # T+0
            fund_settlement_cycle=0,
            price_limit_pct=0.10,
            order_types_supported=("market",),
            call_auction_sessions=("open",),
        )
        provider = InMemoryRuleProvider(
            trading_rules={100: [rule_v1, rule_v2]},
        )
        # as_of_date = 2026-02-01 → 应选择 v1 (2026-01-01)
        result = provider.get_trading_rule(100, "2026-02-01")
        assert result is not None
        assert result.settlement_cycle == 1

        # as_of_date = 2026-03-15 → 应选择 v2 (2026-03-01)
        result = provider.get_trading_rule(100, "2026-03-15")
        assert result is not None
        assert result.settlement_cycle == 0

    def test_pit_no_version_before_date(self) -> None:
        """as_of_date 早于所有版本 → 返回 None。"""
        rule = TradingRuleSet(
            instrument_id=100,
            as_of_date="2026-03-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market",),
            call_auction_sessions=("open",),
        )
        provider = InMemoryRuleProvider(
            trading_rules={100: [rule]},
        )
        result = provider.get_trading_rule(100, "2026-01-01")
        assert result is None

    def test_pit_fee_schedule_multi_version(self) -> None:
        """FeeSchedule 多版本 PIT 选择。"""
        fee_v1 = FeeSchedule(
            instrument_id=100,
            as_of_date="2026-01-01",
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
        )
        fee_v2 = FeeSchedule(
            instrument_id=100,
            as_of_date="2026-06-01",
            commission_rate=0.0002,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
        )
        provider = InMemoryRuleProvider(
            fee_schedules={100: [fee_v1, fee_v2]},
        )
        result = provider.get_fee_schedule(100, "2026-04-01")
        assert result is not None
        assert result.commission_rate == 0.0003

        result = provider.get_fee_schedule(100, "2026-07-01")
        assert result is not None
        assert result.commission_rate == 0.0002

    def test_pit_boundary_exclusive(self) -> None:
        """as_of_date = as_of_date of record → 包含该记录。"""
        rule = TradingRuleSet(
            instrument_id=100,
            as_of_date="2026-03-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market",),
            call_auction_sessions=("open",),
        )
        provider = InMemoryRuleProvider(
            trading_rules={100: [rule]},
        )
        # as_of_date 恰好等于记录的 as_of_date → 包含
        result = provider.get_trading_rule(100, "2026-03-01")
        assert result is not None


# ---------------------------------------------------------------------------
# _find_pit — effective_to 可选过滤（前向兼容）
# ---------------------------------------------------------------------------

_RULE_ID: InstrumentId = 100  # type: ignore[assignment]


@dataclass(frozen=True)
class _RuleWithExpiry:
    """测试辅助：带 effective_to 的规则记录。"""

    instrument_id: int
    as_of_date: str
    effective_to: str | None = None
    value: str = ""


class TestFindPitEffectiveTo:
    """_find_pit — effective_to 可选过滤。"""

    def test_effective_to_excludes_expired(self) -> None:
        """effective_to <= as_of_date 的记录应被排除。"""
        expired = _RuleWithExpiry(
            instrument_id=100,
            as_of_date="2026-01-01",
            effective_to="2026-03-01",
            value="expired",
        )
        active = _RuleWithExpiry(
            instrument_id=100,
            as_of_date="2026-02-01",
            effective_to="2026-06-01",
            value="active",
        )
        store: dict[InstrumentId, list[_RuleWithExpiry]] = {100: [expired, active]}
        result = InMemoryRuleProvider._find_pit(store, _RULE_ID, "2026-04-01")
        assert result is not None
        assert result.value == "active"

    def test_effective_to_none_always_included(self) -> None:
        """effective_to is None → 永不过期。"""
        record = _RuleWithExpiry(
            instrument_id=100,
            as_of_date="2026-01-01",
            effective_to=None,
            value="no_expiry",
        )
        store: dict[InstrumentId, list[_RuleWithExpiry]] = {100: [record]}
        result = InMemoryRuleProvider._find_pit(store, _RULE_ID, "2026-12-31")
        assert result is not None
        assert result.value == "no_expiry"

    def test_effective_to_boundary_expired(self) -> None:
        """effective_to == as_of_date → 已过期（必须严格 > 才包含）。"""
        record = _RuleWithExpiry(
            instrument_id=100,
            as_of_date="2026-01-01",
            effective_to="2026-04-01",
            value="boundary",
        )
        store: dict[InstrumentId, list[_RuleWithExpiry]] = {100: [record]}
        result = InMemoryRuleProvider._find_pit(store, _RULE_ID, "2026-04-01")
        assert result is None

    def test_no_effective_to_field_backward_compat(self) -> None:
        """没有 effective_to 属性 → getattr 回退 None，永不过期。"""
        record = TradingRuleSet(
            instrument_id=100,
            as_of_date="2026-01-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market",),
            call_auction_sessions=("open",),
        )
        store: dict[InstrumentId, list[TradingRuleSet]] = {100: [record]}
        result = InMemoryRuleProvider._find_pit(store, _RULE_ID, "2026-12-31")
        assert result is not None


# ---------------------------------------------------------------------------
# default_price_limit_pct — Lifecycle → Price Limit Mapping
# ---------------------------------------------------------------------------


class TestDefaultPriceLimitPct:
    """lifecycle_state + board_segment → price_limit_pct 映射。"""

    def test_normal_main_board(self) -> None:
        """主板正常股票涨跌停 10%。"""
        assert default_price_limit_pct("normal", "main") == 0.10

    def test_normal_bse(self) -> None:
        """北交所正常股票涨跌停 10%。"""
        assert default_price_limit_pct("normal", "bse") == 0.10

    def test_st_five_pct(self) -> None:
        """ST 股票涨跌停 5%。"""
        assert default_price_limit_pct("st", "main") == 0.05

    def test_st_star_five_pct(self) -> None:
        """*ST 股票涨跌停 5%。"""
        assert default_price_limit_pct("st_star", "main") == 0.05

    def test_gem_twenty_pct(self) -> None:
        """创业板涨跌停 20%。"""
        assert default_price_limit_pct("normal", "gem") == 0.20

    def test_star_twenty_pct(self) -> None:
        """科创板涨跌停 20%。"""
        assert default_price_limit_pct("normal", "star") == 0.20

    def test_st_gem_five_pct(self) -> None:
        """创业板 ST 仍为 5%（lifecycle 优先于 board_segment）。"""
        assert default_price_limit_pct("st", "gem") == 0.05

    def test_ipo_no_limit(self) -> None:
        """IPO 前五日无涨跌停限制。"""
        assert default_price_limit_pct("ipo", "main") is None

    def test_delisting_main_board(self) -> None:
        """退市整理期主板仍为 10%。"""
        assert default_price_limit_pct("delisting", "main") == 0.10

    def test_delisting_gem_ten_pct(self) -> None:
        """退市整理期创业板统一为 10%（lifecycle 优先于 board_segment）。"""
        assert default_price_limit_pct("delisting", "gem") == 0.10

    def test_delisting_star_ten_pct(self) -> None:
        """退市整理期科创板统一为 10%（lifecycle 优先于 board_segment）。"""
        assert default_price_limit_pct("delisting", "star") == 0.10

    def test_ipo_no_limit_on_gem(self) -> None:
        """创业板 IPO 前五日同样无涨跌停限制。"""
        assert default_price_limit_pct("ipo", "gem") is None
