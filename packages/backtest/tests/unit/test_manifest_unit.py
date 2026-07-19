"""RunManifest / RuleRef / RuleRefCollector / serialize_manifest unit tests.

Task 1B — RuleRefs + RunManifest (Phase 4 Part 03).
Phase 0.9 — RunManifest Enrichment (InputRef + data fingerprints).
"""

from __future__ import annotations

from collections.abc import Callable
from inspect import Parameter, signature

import orjson
import pytest
from ditto_backtest.config import EngineConfig
from ditto_backtest.manifest import (
    InputRef,
    RuleRef,
    RuleRefCollector,
    RunManifest,
    RunManifestInputEvidence,
    RunMode,
    build_run_manifest,
    serialize_manifest,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_semantics import (
    DEFAULT_PIT_TIME_COLUMN,
    PIT_POLICY_FAIL_CLOSED,
)
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    TradingRuleSet,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CANONICAL_SPEC_HASH = "a" * 64
_BASE_SPEC_HASH = "b" * 64
_EMPTY_PARAMETER_HASH = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


def _baseline_manifest_identity() -> dict[str, object]:
    return {
        "base_spec_hash": _BASE_SPEC_HASH,
        "parameter_hash": _EMPTY_PARAMETER_HASH,
        "effective_parameters": (),
        "research_snapshot_id": None,
        "research_snapshot_manifest_hash": None,
    }


def _baseline_engine_identity() -> dict[str, object]:
    return _baseline_manifest_identity()


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
        spec_hash=_CANONICAL_SPEC_HASH,
        base_spec_hash=_BASE_SPEC_HASH,
        parameter_hash=_EMPTY_PARAMETER_HASH,
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
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
            spec_hash=_CANONICAL_SPEC_HASH,
            base_spec_hash=_BASE_SPEC_HASH,
            parameter_hash=_EMPTY_PARAMETER_HASH,
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
        )
        assert manifest.input_refs == ()
        assert manifest.parameter_overrides == ()
        assert manifest.rule_refs == ()
        assert manifest.artifacts == ()
        assert manifest.config_hash == ""
        assert manifest.engine_version == ""
        assert manifest.rule_resolution_policy == "as_of_date"
        assert manifest.pit_time_column == DEFAULT_PIT_TIME_COLUMN
        assert manifest.pit_policy == PIT_POLICY_FAIL_CLOSED
        assert manifest.unsafe_time_policy == ""
        assert manifest.knowledge_lag_days == 1

    @pytest.mark.parametrize(
        "field_name",
        [
            "base_spec_hash",
            "parameter_hash",
            "effective_parameters",
            "research_snapshot_id",
            "research_snapshot_manifest_hash",
        ],
    )
    def test_research_identity_fields_are_required(self, field_name: str) -> None:
        manifest_signature = signature(RunManifest)
        assert manifest_signature.parameters[field_name].default is Parameter.empty

    def test_rejects_nonempty_legacy_parameter_overrides(self) -> None:
        with pytest.raises(ValueError, match="parameter_overrides"):
            RunManifest(
                run_id="r",
                strategy_id="s",
                strategy_version="v",
                mode=RunMode.RESEARCH,
                created_at="2026-03-22T10:00:00Z",
                spec_hash=_CANONICAL_SPEC_HASH,
                base_spec_hash=_BASE_SPEC_HASH,
                parameter_hash=_EMPTY_PARAMETER_HASH,
                effective_parameters=(),
                research_snapshot_id=None,
                research_snapshot_manifest_hash=None,
                parameter_overrides=("top_k=3",),
            )

    def test_rejects_noncanonical_research_snapshot_identity(self) -> None:
        with pytest.raises(ValueError, match="research_snapshot_id"):
            RunManifest(
                run_id="r",
                strategy_id="s",
                strategy_version="v",
                mode=RunMode.RESEARCH,
                created_at="2026-03-22T10:00:00Z",
                spec_hash=_CANONICAL_SPEC_HASH,
                base_spec_hash=_BASE_SPEC_HASH,
                parameter_hash=_EMPTY_PARAMETER_HASH,
                effective_parameters=(),
                research_snapshot_id=" snapshot ",
                research_snapshot_manifest_hash="c" * 64,
            )

    @pytest.mark.parametrize(
        ("snapshot_id", "manifest_hash"),
        [("snapshot", None), (None, "c" * 64)],
    )
    def test_rejects_unpaired_research_snapshot_identity(
        self,
        snapshot_id: str | None,
        manifest_hash: str | None,
    ) -> None:
        with pytest.raises(ValueError, match="research_snapshot"):
            RunManifest(
                run_id="r",
                strategy_id="s",
                strategy_version="v",
                mode=RunMode.RESEARCH,
                created_at="2026-03-22T10:00:00Z",
                spec_hash=_CANONICAL_SPEC_HASH,
                base_spec_hash=_BASE_SPEC_HASH,
                parameter_hash=_EMPTY_PARAMETER_HASH,
                effective_parameters=(),
                research_snapshot_id=snapshot_id,
                research_snapshot_manifest_hash=manifest_hash,
            )

    def test_spec_hash_is_required(self) -> None:
        manifest_signature = signature(RunManifest)
        constructor: Callable[..., RunManifest] = RunManifest

        assert manifest_signature.parameters["spec_hash"].default is Parameter.empty
        with pytest.raises(TypeError, match="spec_hash"):
            constructor(
                run_id="r",
                strategy_id="s",
                strategy_version="v",
                mode=RunMode.RESEARCH,
                created_at="2026-03-22T10:00:00Z",
            )

    @pytest.mark.parametrize(
        "invalid_hash",
        [
            pytest.param("", id="empty"),
            pytest.param("a" * 16, id="short"),
            pytest.param("A" * 64, id="uppercase"),
            pytest.param("z" * 64, id="non-hex"),
        ],
    )
    def test_rejects_invalid_spec_hash(self, invalid_hash: str) -> None:
        with pytest.raises(ValueError, match="spec_hash"):
            RunManifest(
                run_id="r",
                strategy_id="s",
                strategy_version="v",
                mode=RunMode.RESEARCH,
                created_at="2026-03-22T10:00:00Z",
                spec_hash=invalid_hash,
                **_baseline_manifest_identity(),
            )


class TestRunManifestInputEvidence:
    """Manifest build input bundle is a frozen, typed transport value."""

    def test_is_frozen(self) -> None:
        evidence = RunManifestInputEvidence(
            input_instruments=set(),
            bar_fingerprints={},
        )

        with pytest.raises(AttributeError):
            evidence.input_instruments = {InstrumentId(1)}  # type: ignore[misc]


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
            parameter_overrides=(),
            rule_refs=(ref1, ref2),
            artifacts=("trade_log.csv",),
            config_hash="hash1",
            engine_version="0.2.0",
            rule_resolution_policy="as_of_date",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
            created_at="2026-03-22T10:00:00Z",
        )

        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)

        assert parsed["run_id"] == "run-001"
        assert parsed["mode"] == "backtest"
        assert parsed["input_refs"] == [1]
        assert parsed["parameter_overrides"] == []
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


# ---------------------------------------------------------------------------
# Phase 0.9: InputRef + RunManifest Enrichment tests
# ---------------------------------------------------------------------------


class TestInputRef:
    """InputRef frozen dataclass — 输入数据引用含数据指纹."""

    def test_frozen(self) -> None:
        """InputRef 不可变."""
        ref = InputRef(
            instrument_id=1,
            data_hash="sha256:abcd1234",
            date_range=("2025-01-01", "2025-12-31"),
            source="parquet://data/bars/1",
        )
        with pytest.raises(AttributeError):
            ref.data_hash = "changed"  # type: ignore[misc]

    def test_all_fields(self) -> None:
        """所有字段正确赋值."""
        ref = InputRef(
            instrument_id=510050,
            data_hash="sha256:deadbeef",
            date_range=("2025-01-01", "2025-06-30"),
            source="parquet://data/bars/510050",
        )
        assert ref.instrument_id == 510050
        assert ref.data_hash == "sha256:deadbeef"
        assert ref.date_range == ("2025-01-01", "2025-06-30")
        assert ref.source == "parquet://data/bars/510050"
        assert ref.source_snapshot_id == ""

    def test_source_snapshot_id(self) -> None:
        """InputRef can capture the source snapshot version used by a run."""
        ref = InputRef(
            instrument_id=510050,
            data_hash="sha256:deadbeef",
            date_range=("2025-01-01", "2025-06-30"),
            source="tushare",
            source_snapshot_id="tushare:stock_daily:20250630",
        )

        assert ref.source_snapshot_id == "tushare:stock_daily:20250630"

    def test_equality(self) -> None:
        """相同字段 → 相等."""
        r1 = InputRef(
            instrument_id=1,
            data_hash="sha256:abc",
            date_range=("2025-01-01", "2025-12-31"),
            source="src",
        )
        r2 = InputRef(
            instrument_id=1,
            data_hash="sha256:abc",
            date_range=("2025-01-01", "2025-12-31"),
            source="src",
        )
        assert r1 == r2

    def test_hash_inequality(self) -> None:
        """不同 data_hash → 不相等."""
        r1 = InputRef(
            instrument_id=1,
            data_hash="sha256:aaa",
            date_range=("2025-01-01", "2025-12-31"),
            source="src",
        )
        r2 = InputRef(
            instrument_id=1,
            data_hash="sha256:bbb",
            date_range=("2025-01-01", "2025-12-31"),
            source="src",
        )
        assert r1 != r2


class TestRunManifestEnrichment:
    """Phase 0.9: RunManifest 新字段（向后兼容）."""

    def test_optional_enrichment_fields_have_defaults(self) -> None:
        """可选 enrichment 字段保留稳定默认值。"""
        manifest = RunManifest(
            run_id="r",
            strategy_id="s",
            strategy_version="v",
            mode=RunMode.RESEARCH,
            created_at="2026-03-22T10:00:00Z",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
        )
        assert manifest.input_ref_details == ()
        assert manifest.universe_hash == ""
        assert manifest.spec_hash == _CANONICAL_SPEC_HASH
        assert manifest.dependency_versions == ()
        assert manifest.random_seed is None
        assert manifest.pit_time_column == DEFAULT_PIT_TIME_COLUMN
        assert manifest.pit_policy == PIT_POLICY_FAIL_CLOSED
        assert manifest.unsafe_time_policy == ""
        assert manifest.knowledge_lag_days == 1

    def test_input_ref_details_accepts_input_refs(self) -> None:
        """input_ref_details 接受 InputRef 元组."""
        refs = (
            InputRef(
                instrument_id=1,
                data_hash="sha256:abc",
                date_range=("2025-01-01", "2025-06-30"),
                source="parquet://data/bars/1",
            ),
            InputRef(
                instrument_id=2,
                data_hash="sha256:def",
                date_range=("2025-01-01", "2025-06-30"),
                source="parquet://data/bars/2",
            ),
        )
        manifest = RunManifest(
            run_id="run-002",
            strategy_id="strat",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
            input_ref_details=refs,
        )
        assert len(manifest.input_ref_details) == 2
        assert manifest.input_ref_details[0].instrument_id == 1
        assert manifest.input_ref_details[1].data_hash == "sha256:def"

    def test_new_hash_fields(self) -> None:
        """universe_hash / spec_hash 可正确赋值."""
        manifest = RunManifest(
            run_id="r",
            strategy_id="s",
            strategy_version="v",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            universe_hash="uni_hash_123",
            spec_hash="b" * 64,
            **_baseline_manifest_identity(),
        )
        assert manifest.universe_hash == "uni_hash_123"
        assert manifest.spec_hash == "b" * 64

    def test_dependency_versions_and_random_seed(self) -> None:
        """dependency_versions / random_seed 可正确赋值."""
        manifest = RunManifest(
            run_id="r",
            strategy_id="s",
            strategy_version="v",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
            dependency_versions=("numpy==2.0", "polars==1.0"),
            random_seed=42,
        )
        assert manifest.dependency_versions == ("numpy==2.0", "polars==1.0")
        assert manifest.random_seed == 42


class TestSerializeManifestEnrichment:
    """Phase 0.9: serialize_manifest 包含新字段."""

    def test_input_ref_details_in_serialized_output(self) -> None:
        """input_ref_details 出现在序列化输出中."""
        ref = InputRef(
            instrument_id=1,
            data_hash="sha256:abc123",
            date_range=("2025-01-01", "2025-12-31"),
            source="parquet://data/bars/1",
        )
        manifest = RunManifest(
            run_id="run-100",
            strategy_id="test",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
            input_ref_details=(ref,),
        )
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)
        assert "input_ref_details" in parsed
        assert len(parsed["input_ref_details"]) == 1
        assert parsed["input_ref_details"][0]["instrument_id"] == 1
        assert parsed["input_ref_details"][0]["data_hash"] == "sha256:abc123"
        assert parsed["input_ref_details"][0]["date_range"] == [
            "2025-01-01",
            "2025-12-31",
        ]
        assert parsed["input_ref_details"][0]["source"] == "parquet://data/bars/1"
        assert parsed["input_ref_details"][0]["source_snapshot_id"] == ""

    def test_new_hash_fields_in_serialized_output(self) -> None:
        """universe_hash / spec_hash 出现在序列化输出中."""
        manifest = RunManifest(
            run_id="run-200",
            strategy_id="test",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            universe_hash="uni_abc",
            spec_hash="d" * 64,
            **_baseline_manifest_identity(),
        )
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)
        assert parsed["universe_hash"] == "uni_abc"
        assert parsed["spec_hash"] == "d" * 64

    def test_dependency_versions_in_serialized_output(self) -> None:
        """dependency_versions 出现在序列化输出中."""
        manifest = RunManifest(
            run_id="run-300",
            strategy_id="test",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
            dependency_versions=("numpy==2.0",),
        )
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)
        assert parsed["dependency_versions"] == ["numpy==2.0"]

    def test_random_seed_in_serialized_output(self) -> None:
        """random_seed 出现在序列化输出中."""
        manifest = RunManifest(
            run_id="run-400",
            strategy_id="test",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
            random_seed=42,
        )
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)
        assert parsed["random_seed"] == 42

    def test_random_seed_none_in_serialized_output(self) -> None:
        """random_seed=None 时序列化为 null."""
        manifest = RunManifest(
            run_id="run-401",
            strategy_id="test",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
        )
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)
        assert parsed["random_seed"] is None

    def test_pit_policy_in_serialized_output(self) -> None:
        """PIT policy fields must be visible in manifest JSON."""
        manifest = RunManifest(
            run_id="run-pit",
            strategy_id="test",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
            knowledge_lag_days=3,
        )
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)

        assert parsed["pit_time_column"] == DEFAULT_PIT_TIME_COLUMN
        assert parsed["pit_policy"] == PIT_POLICY_FAIL_CLOSED
        assert parsed["unsafe_time_policy"] == ""
        assert parsed["knowledge_lag_days"] == 3

    def test_input_ref_details_sorted_by_instrument_id(self) -> None:
        """input_ref_details 按 instrument_id 排序."""
        refs = (
            InputRef(
                instrument_id=3,
                data_hash="sha256:ccc",
                date_range=("2025-01-01", "2025-12-31"),
                source="src3",
            ),
            InputRef(
                instrument_id=1,
                data_hash="sha256:aaa",
                date_range=("2025-01-01", "2025-06-30"),
                source="src1",
            ),
        )
        manifest = RunManifest(
            run_id="run-500",
            strategy_id="test",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
            input_ref_details=refs,
        )
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)
        details = parsed["input_ref_details"]
        assert details[0]["instrument_id"] == 1
        assert details[1]["instrument_id"] == 3

    def test_byte_level_stability_with_enrichment(self) -> None:
        """含新字段时仍保持字节级稳定 (P2)."""
        ref = InputRef(
            instrument_id=1,
            data_hash="sha256:stable",
            date_range=("2025-01-01", "2025-12-31"),
            source="src",
        )
        manifest = RunManifest(
            run_id="run-600",
            strategy_id="stable-test",
            strategy_version="2.0",
            mode=RunMode.BACKTEST,
            created_at="2026-04-11T00:00:00Z",
            input_ref_details=(ref,),
            universe_hash="uni",
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_manifest_identity(),
            dependency_versions=("pkg==1.0",),
            random_seed=123,
        )
        first = serialize_manifest(manifest)
        second = serialize_manifest(manifest)
        assert first == second
        assert first.encode("utf-8") == second.encode("utf-8")

    def test_backward_compatible_serialization(self) -> None:
        """旧字段（input_refs）仍然正确序列化."""
        manifest = _make_manifest()
        result = serialize_manifest(manifest)
        parsed = orjson.loads(result)
        # 旧字段仍存在
        assert parsed["input_refs"] == [1, 2]
        # 可选 enrichment 字段使用默认值，canonical identity 必须保留
        assert parsed["input_ref_details"] == []
        assert parsed["universe_hash"] == ""
        assert parsed["spec_hash"] == _CANONICAL_SPEC_HASH
        assert parsed["dependency_versions"] == []
        assert parsed["random_seed"] is None


class TestCanonicalSpecHashManifest:
    """Manifest 只接收 StrategySpec codec 产生的完整 canonical hash。"""

    def test_legacy_partial_hash_helper_is_not_exported(self) -> None:
        from ditto_backtest import manifest

        assert not hasattr(manifest, "hash_spec")

    @pytest.mark.parametrize(
        "invalid_hash",
        [
            pytest.param("", id="missing"),
            pytest.param("a" * 16, id="truncated"),
            pytest.param("A" * 64, id="uppercase"),
            pytest.param("z" * 64, id="non-hex"),
        ],
    )
    def test_build_manifest_rejects_non_canonical_hash(
        self,
        invalid_hash: str,
    ) -> None:
        config = EngineConfig(
            start_date="2026-01-01",
            end_date="2026-01-31",
            initial_cash=1_000_000.0,
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_engine_identity(),
        )

        with pytest.raises(ValueError, match="spec_hash"):
            build_run_manifest(
                run_id="run-invalid-spec-hash",
                config=config,
                spec_hash=invalid_hash,
                input_evidence=RunManifestInputEvidence(
                    input_instruments=set(),
                    bar_fingerprints={},
                ),
                rule_refs=(),
                random_seed=7,
            )

    def test_build_manifest_preserves_hash_independent_of_audit_run_id(self) -> None:
        config = EngineConfig(
            start_date="2026-01-01",
            end_date="2026-01-31",
            initial_cash=1_000_000.0,
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_engine_identity(),
        )

        first = build_run_manifest(
            run_id="audit-run-one",
            config=config,
            spec_hash=_CANONICAL_SPEC_HASH,
            input_evidence=RunManifestInputEvidence(
                input_instruments=set(),
                bar_fingerprints={},
            ),
            rule_refs=(),
            random_seed=7,
        )
        second = build_run_manifest(
            run_id="audit-run-two",
            config=config,
            spec_hash=_CANONICAL_SPEC_HASH,
            input_evidence=RunManifestInputEvidence(
                input_instruments=set(),
                bar_fingerprints={},
            ),
            rule_refs=(),
            random_seed=7,
        )

        assert first.run_id != second.run_id
        assert first.spec_hash == second.spec_hash == _CANONICAL_SPEC_HASH


class TestBuildRunManifestPitPolicy:
    """build_run_manifest should freeze PIT policy used by the engine."""

    def test_build_run_manifest_records_pit_policy_from_config(self) -> None:
        """Manifest records the engine's PIT policy and configured lag."""
        config = EngineConfig(
            start_date="2026-01-01",
            end_date="2026-01-31",
            initial_cash=1_000_000.0,
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_engine_identity(),
            strategy_id="momentum-etf",
            strategy_version="2026.01",
            rebalance_freq="daily",
            knowledge_lag_days=3,
        )

        manifest = build_run_manifest(
            run_id="run-pit-policy",
            config=config,
            spec_hash=_CANONICAL_SPEC_HASH,
            input_evidence=RunManifestInputEvidence(
                input_instruments=set(),
                bar_fingerprints={},
            ),
            rule_refs=(),
            random_seed=7,
        )

        assert manifest.pit_time_column == DEFAULT_PIT_TIME_COLUMN
        assert manifest.pit_policy == PIT_POLICY_FAIL_CLOSED
        assert manifest.unsafe_time_policy == ""
        assert manifest.knowledge_lag_days == 3


class TestBuildRunManifestSourceSnapshots:
    """build_run_manifest should preserve upstream data snapshot provenance."""

    def test_build_run_manifest_records_source_snapshot_ids(self) -> None:
        """Provider/catalog snapshot IDs should reach InputRef details."""
        config = EngineConfig(
            start_date="2026-03-01",
            end_date="2026-03-01",
            initial_cash=1_000_000.0,
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_engine_identity(),
            strategy_id="momentum-etf",
            strategy_version="2026.03",
            rebalance_freq="daily",
        )
        snapshot_id = "snapshot:tushare:stock_daily:2026-03-01:abc"

        manifest = build_run_manifest(
            run_id="run-source-snapshot",
            config=config,
            spec_hash=_CANONICAL_SPEC_HASH,
            input_evidence=RunManifestInputEvidence(
                input_instruments={InstrumentId(1)},
                bar_fingerprints={InstrumentId(1): [("2026-03-01", 10.2)]},
                source_snapshot_ids={InstrumentId(1): snapshot_id},
            ),
            rule_refs=(),
            random_seed=7,
        )

        assert manifest.input_ref_details[0].source_snapshot_id == snapshot_id

    def test_build_run_manifest_aggregates_multiple_source_snapshot_ids(
        self,
    ) -> None:
        """一个 InputRef 对应多个上游快照时生成稳定聚合 ID."""
        config = EngineConfig(
            start_date="2026-03-01",
            end_date="2026-03-02",
            initial_cash=1_000_000.0,
            spec_hash=_CANONICAL_SPEC_HASH,
            **_baseline_engine_identity(),
            strategy_id="momentum-etf",
            strategy_version="2026.03",
            rebalance_freq="daily",
        )

        manifest = build_run_manifest(
            run_id="run-source-snapshot-set",
            config=config,
            spec_hash=_CANONICAL_SPEC_HASH,
            input_evidence=RunManifestInputEvidence(
                input_instruments={InstrumentId(1)},
                bar_fingerprints={
                    InstrumentId(1): [
                        ("2026-03-01", 10.2),
                        ("2026-03-02", 10.3),
                    ],
                },
                source_snapshot_ids={
                    InstrumentId(1): {
                        "snapshot:tushare:stock_daily:2026-03-01:abc",
                        "snapshot:tushare:stock_daily:2026-03-02:def",
                    },
                },
            ),
            rule_refs=(),
            random_seed=7,
        )

        assert manifest.input_ref_details[0].source_snapshot_id.startswith(
            "snapshot-set:sha256:",
        )
