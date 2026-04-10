"""RunManifest / RuleRef / RuleRefCollector / serialize_manifest unit tests.

Task 1B — RuleRefs + RunManifest (Phase 4 Part 03).
"""

from __future__ import annotations

import orjson
import pytest
from ditto_engine.backtest.manifest import (
    RuleRef,
    RuleRefCollector,
    RunManifest,
    RunMode,
    serialize_manifest,
)
from ditto_engine.execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    TradingRuleSet,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_definition(
    instrument_id: int = 1,
    tick_size: float = 0.001,
    lot_size: int = 100,
) -> InstrumentDefinition:
    return InstrumentDefinition(
        instrument_id=instrument_id,
        asset_class="etf",
        exchange="XSHE",
        currency="CNY",
        tick_size=tick_size,
        lot_size=lot_size,
        multiplier=1.0,
        board_segment="main",
        lifecycle_state="normal",
    )


def _make_trading_rule(
    instrument_id: int = 1,
    as_of_date: str = "2025-01-01",
    settlement_cycle: int = 1,
) -> TradingRuleSet:
    return TradingRuleSet(
        instrument_id=instrument_id,
        as_of_date=as_of_date,
        settlement_cycle=settlement_cycle,
        fund_settlement_cycle=1,
        price_limit_pct=0.10,
        order_types_supported=("limit", "market"),
        call_auction_sessions=("open", "close"),
    )


def _make_fee_schedule(
    instrument_id: int = 1,
    as_of_date: str = "2025-01-01",
    commission_rate: float = 0.0003,
) -> FeeSchedule:
    return FeeSchedule(
        instrument_id=instrument_id,
        as_of_date=as_of_date,
        commission_rate=commission_rate,
        min_commission=5.0,
        stamp_duty_rate=0.0,
        transfer_fee_rate=0.00001,
    )


def _make_rules(
    instrument_id: int = 1,
    trading_rule_as_of: str = "2025-01-01",
    fee_as_of: str = "2025-01-01",
    tick_size: float = 0.001,
) -> InstrumentRules:
    return (
        _make_definition(instrument_id=instrument_id, tick_size=tick_size),
        _make_trading_rule(instrument_id=instrument_id, as_of_date=trading_rule_as_of),
        _make_fee_schedule(instrument_id=instrument_id, as_of_date=fee_as_of),
    )


def _make_manifest(
    rule_refs: tuple[RuleRef, ...] | None = None,
) -> RunManifest:
    return RunManifest(
        run_id="run-001",
        strategy_id="momentum-etf",
        strategy_version="1.0.0",
        mode=RunMode.BACKTEST,
        input_refs=(1, 2),
        parameter_overrides=(),
        rule_refs=rule_refs or (),
        artifacts=(),
        config_hash="abc123",
        engine_version="0.1.0",
        rule_resolution_policy="as_of_date",
        created_at="2026-03-22T10:00:00Z",
    )


# ---------------------------------------------------------------------------
# Task 1B.1: RunMode / RuleRef / RunManifest frozen dataclass tests
# ---------------------------------------------------------------------------


class TestRunMode:
    """RunMode StrEnum has 4 values."""

    def test_values(self) -> None:
        assert RunMode.RESEARCH == "research"
        assert RunMode.RECOMMENDATION == "recommendation"
        assert RunMode.BACKTEST == "backtest"
        assert RunMode.LIVE == "live"

    def test_member_count(self) -> None:
        assert len(RunMode) == 4


class TestRuleRefFrozen:
    """RuleRef is frozen — attribute assignment raises FrozenInstanceError."""

    def test_frozen(self) -> None:
        ref = RuleRef(
            instrument_id=1,
            definition_version="a1b2c3d4",
            trading_rule_as_of="2025-01-01",
            fee_schedule_as_of="2025-01-01",
            trading_rule_effective_to="",
            fee_schedule_effective_to="",
        )
        with pytest.raises(AttributeError):
            ref.instrument_id = 2  # type: ignore[misc]

    def test_equality(self) -> None:
        r1 = RuleRef(
            instrument_id=1,
            definition_version="a1b2c3d4",
            trading_rule_as_of="2025-01-01",
            fee_schedule_as_of="2025-01-01",
            trading_rule_effective_to="",
            fee_schedule_effective_to="",
        )
        r2 = RuleRef(
            instrument_id=1,
            definition_version="a1b2c3d4",
            trading_rule_as_of="2025-01-01",
            fee_schedule_as_of="2025-01-01",
            trading_rule_effective_to="",
            fee_schedule_effective_to="",
        )
        assert r1 == r2


class TestRunManifestFrozen:
    """RunManifest is frozen — attribute assignment raises FrozenInstanceError."""

    def test_frozen(self) -> None:
        manifest = _make_manifest()
        with pytest.raises(AttributeError):
            manifest.run_id = "run-002"  # type: ignore[misc]

    def test_defaults(self) -> None:
        manifest = RunManifest(
            run_id="r",
            strategy_id="s",
            strategy_version="v",
            mode=RunMode.RESEARCH,
            created_at="2026-03-22T10:00:00Z",
        )
        assert manifest.input_refs == ()
        assert manifest.parameter_overrides == ()
        assert manifest.rule_refs == ()
        assert manifest.artifacts == ()
        assert manifest.config_hash == ""
        assert manifest.engine_version == ""
        assert manifest.rule_resolution_policy == "as_of_date"


# ---------------------------------------------------------------------------
# Task 1B.2: RuleRefCollector tests
# ---------------------------------------------------------------------------


class TestRuleRefCollectorBasic:
    """RuleRefCollector collects rule references from rules dicts."""

    def test_empty_start(self) -> None:
        collector = RuleRefCollector()
        assert collector.rule_refs == ()

    def test_single_observe(self) -> None:
        collector = RuleRefCollector()
        rules: dict[int, InstrumentRules] = {
            1: _make_rules(1),
        }
        collector.observe("2026-03-01", rules)
        assert len(collector.rule_refs) == 1

    def test_two_instruments_same_version(self) -> None:
        """Two instruments with same definition/timing produce 2 refs."""
        collector = RuleRefCollector()
        rules: dict[int, InstrumentRules] = {
            1: _make_rules(1),
            2: _make_rules(2),
        }
        collector.observe("2026-03-01", rules)
        assert len(collector.rule_refs) == 2

    def test_duplicate_key_not_overwritten(self) -> None:
        """F3: same key observed again → first version kept."""
        collector = RuleRefCollector()

        rules_day1: dict[int, InstrumentRules] = {
            1: _make_rules(1, trading_rule_as_of="2025-01-01"),
        }
        rules_day2: dict[int, InstrumentRules] = {
            1: _make_rules(
                1,
                trading_rule_as_of="2025-01-01",  # same key
            ),
        }
        collector.observe("2026-03-01", rules_day1)
        first_refs = list(collector.rule_refs)
        collector.observe("2026-03-02", rules_day2)
        second_refs = list(collector.rule_refs)

        # Same count — no overwrite
        assert len(second_refs) == len(first_refs)
        # Same object — first kept
        assert second_refs[0] is first_refs[0]


class TestRuleRefCollectorCrossRuleChangeDay:
    """Cross rule change boundary — versions should NOT be overwritten (F3)."""

    def test_cross_rule_change_not_overwritten(self) -> None:
        """Instrument gets a rule change mid-backtest.
        Both versions should be preserved."""
        collector = RuleRefCollector()

        # Day 1: settlement_cycle=1, fee_as_of=2025-01-01
        rules_v1: dict[int, InstrumentRules] = {
            1: (
                _make_definition(1, tick_size=0.001),
                _make_trading_rule(1, as_of_date="2025-01-01", settlement_cycle=1),
                _make_fee_schedule(1, as_of_date="2025-01-01"),
            ),
        }
        # Day 2: settlement_cycle=1, fee_as_of=2025-06-15 (fee changed)
        rules_v2: dict[int, InstrumentRules] = {
            1: (
                _make_definition(1, tick_size=0.001),
                _make_trading_rule(1, as_of_date="2025-01-01", settlement_cycle=1),
                _make_fee_schedule(1, as_of_date="2025-06-15"),
            ),
        }

        collector.observe("2026-03-01", rules_v1)
        collector.observe("2026-03-02", rules_v2)

        refs = collector.rule_refs
        assert len(refs) == 2

        # First ref has fee_schedule_as_of = 2025-01-01
        fee_as_ofs = {r.fee_schedule_as_of for r in refs}
        assert "2025-01-01" in fee_as_ofs
        assert "2025-06-15" in fee_as_ofs

    def test_definition_change_creates_new_ref(self) -> None:
        """If definition changes (different tick_size), new ref is added."""
        collector = RuleRefCollector()

        rules_v1: dict[int, InstrumentRules] = {
            1: _make_rules(1, tick_size=0.001),
        }
        rules_v2: dict[int, InstrumentRules] = {
            1: _make_rules(1, tick_size=0.01),
        }

        collector.observe("2026-03-01", rules_v1)
        collector.observe("2026-03-02", rules_v2)

        refs = collector.rule_refs
        assert len(refs) == 2

        defn_versions = {r.definition_version for r in refs}
        assert len(defn_versions) == 2

    def test_observe_with_none_rules_noop(self) -> None:
        """observe(None) should be a no-op."""
        collector = RuleRefCollector()
        collector.observe("2026-03-01", None)  # type: ignore[arg-type]
        assert collector.rule_refs == ()

    def test_observe_with_empty_dict_noop(self) -> None:
        """observe({}) should be a no-op."""
        collector = RuleRefCollector()
        collector.observe("2026-03-01", {})
        assert collector.rule_refs == ()


# ---------------------------------------------------------------------------
# Task 1B.3: serialize_manifest tests
# ---------------------------------------------------------------------------


class TestSerializeManifest:
    """Canonical JSON serialization — byte-level stability (P2)."""

    def test_empty_manifest_serializable(self) -> None:
        manifest = _make_manifest()
        result = serialize_manifest(manifest)
        assert isinstance(result, str)
        parsed = orjson.loads(result)
        assert parsed["run_id"] == "run-001"

    def test_byte_level_stability(self) -> None:
        """Same manifest → identical output on second call (P2)."""
        manifest = _make_manifest(
            rule_refs=(
                RuleRef(
                    instrument_id=1,
                    definition_version="a1b2c3d4",
                    trading_rule_as_of="2025-01-01",
                    fee_schedule_as_of="2025-01-01",
                    trading_rule_effective_to="",
                    fee_schedule_effective_to="",
                ),
            ),
        )
        first = serialize_manifest(manifest)
        second = serialize_manifest(manifest)
        assert first == second
        # Also check byte-level (encode to bytes)
        assert first.encode("utf-8") == second.encode("utf-8")

    def test_keys_sorted(self) -> None:
        """JSON keys are sorted (OPT_SORT_KEYS)."""
        manifest = _make_manifest()
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_rule_refs_sorted_stably(self) -> None:
        """rule_refs sorted by (instrument_id, definition_version,
        trading_rule_as_of, fee_schedule_as_of)."""
        manifest = _make_manifest(
            rule_refs=(
                RuleRef(
                    instrument_id=2,
                    definition_version="z9",
                    trading_rule_as_of="2025-06-01",
                    fee_schedule_as_of="2025-06-01",
                    trading_rule_effective_to="",
                    fee_schedule_effective_to="",
                ),
                RuleRef(
                    instrument_id=1,
                    definition_version="a1",
                    trading_rule_as_of="2025-01-01",
                    fee_schedule_as_of="2025-01-01",
                    trading_rule_effective_to="",
                    fee_schedule_effective_to="",
                ),
            ),
        )
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)
        refs = parsed["rule_refs"]
        # ETF-001 before ETF-002
        assert refs[0]["instrument_id"] == 1
        assert refs[1]["instrument_id"] == 2

    def test_time_field_rfc3339(self) -> None:
        """Time fields are RFC3339 UTC format."""
        manifest = _make_manifest()
        result = serialize_manifest(manifest)
        assert "2026-03-22T10:00:00Z" in result

    def test_manifest_with_multiple_refs_roundtrip(self) -> None:
        """Serialize and deserialize preserves all fields."""
        ref1 = RuleRef(
            instrument_id=1,
            definition_version="a1b2c3d4",
            trading_rule_as_of="2025-01-01",
            fee_schedule_as_of="2025-01-01",
            trading_rule_effective_to="",
            fee_schedule_effective_to="",
        )
        ref2 = RuleRef(
            instrument_id=2,
            definition_version="e5f6g7h8",
            trading_rule_as_of="2025-06-15",
            fee_schedule_as_of="2025-06-15",
            trading_rule_effective_to="2025-12-31",
            fee_schedule_effective_to="2025-12-31",
        )
        manifest = RunManifest(
            run_id="run-001",
            strategy_id="strat",
            strategy_version="2.0",
            mode=RunMode.BACKTEST,
            input_refs=(1,),
            parameter_overrides=("lookback=20",),
            rule_refs=(ref1, ref2),
            artifacts=("trade_log.csv",),
            config_hash="hash1",
            engine_version="0.2.0",
            rule_resolution_policy="as_of_date",
            created_at="2026-03-22T10:00:00Z",
        )

        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)

        assert parsed["run_id"] == "run-001"
        assert parsed["mode"] == "backtest"
        assert parsed["input_refs"] == [1]
        assert parsed["parameter_overrides"] == ["lookback=20"]
        assert parsed["artifacts"] == ["trade_log.csv"]
        assert len(parsed["rule_refs"]) == 2
        assert parsed["rule_refs"][1]["trading_rule_effective_to"] == "2025-12-31"


# ---------------------------------------------------------------------------
# Task 1B.4/1B.5: Integration smoke tests
# ---------------------------------------------------------------------------


class TestCollectorToManifestIntegration:
    """End-to-end: Collector → RuleRefs → Manifest → serialize."""

    def test_collector_refs_into_manifest(self) -> None:
        """RuleRefCollector.rule_refs can be passed directly to RunManifest."""
        collector = RuleRefCollector()
        rules: dict[int, InstrumentRules] = {
            1: _make_rules(1),
        }
        collector.observe("2026-03-01", rules)

        manifest = _make_manifest(rule_refs=collector.rule_refs)
        assert len(manifest.rule_refs) == 1
        assert manifest.rule_refs[0].instrument_id == 1

        # Should serialize cleanly
        result = serialize_manifest(manifest)
        assert '"instrument_id": 1' in result

    def test_collector_end_to_end_across_days(self) -> None:
        """Multi-day backtest: collector accumulates refs across rule changes."""
        collector = RuleRefCollector()

        # Day 1: instrument 1 with rule v1
        rules_day1: dict[int, InstrumentRules] = {
            1: _make_rules(
                1,
                trading_rule_as_of="2025-01-01",
                fee_as_of="2025-01-01",
            ),
        }
        collector.observe("2026-03-01", rules_day1)

        # Day 2: instrument 1 fee changes, instrument 2 appears
        rules_day2: dict[int, InstrumentRules] = {
            1: _make_rules(
                1,
                trading_rule_as_of="2025-01-01",
                fee_as_of="2025-06-15",
            ),
            2: _make_rules(
                2,
                trading_rule_as_of="2025-03-01",
                fee_as_of="2025-03-01",
            ),
        }
        collector.observe("2026-03-02", rules_day2)

        manifest = _make_manifest(rule_refs=collector.rule_refs)
        assert len(manifest.rule_refs) == 3

        # Serialize and verify stability
        first = serialize_manifest(manifest)
        second = serialize_manifest(manifest)
        assert first == second
