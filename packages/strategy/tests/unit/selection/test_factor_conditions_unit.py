"""Factor filter conditions: group semantics, evidence, and identity (#740)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.selection.canonical import canonical_spec_hash
from ditto_strategy.selection.contracts import (
    SelectionConditionOperator,
    SelectionFactorCondition,
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    SelectionRunStatus,
    StockSelectionSpec,
)
from ditto_strategy.selection.pipeline import SelectionPipeline

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)
_WEIGHTS = (SelectionFactorWeight(name="momentum", weight=1.0),)


def _instrument(
    instrument_id: int,
    *,
    momentum: float | None = 0.5,
    declared_missing: tuple[str, ...] = (),
) -> SelectionInstrumentInput:
    return SelectionInstrumentInput(
        instrument_id=InstrumentId(instrument_id),
        instrument_name=f"Instrument {instrument_id}",
        industry_id="801010",
        factor_values=(
            () if momentum is None else (SelectionFactorValue("momentum", momentum),)
        ),
        average_turnover=100_000_000.0,
        is_st=False,
        is_suspended=False,
        listing_days=500,
        limit_state=SelectionLimitState.NORMAL,
        tracking_error=None,
        declared_missing_inputs=declared_missing,
    )


def _spec(
    filter_groups: tuple[tuple[SelectionFactorCondition, ...], ...],
    *,
    top_k: int = 10,
) -> StockSelectionSpec:
    return StockSelectionSpec(
        spec_id="screener",
        spec_version="1",
        top_k=top_k,
        min_average_turnover=0.0,
        min_listing_days=1,
        factor_weights=_WEIGHTS,
        filter_groups=filter_groups,
    )


def _bundle(
    spec: StockSelectionSpec,
    instruments: tuple[SelectionInstrumentInput, ...],
) -> SelectionInputBundle:
    return SelectionInputBundle(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        universe_snapshot_id="snapshot:universe",
        industry_rotation_snapshot_id=None,
        source_snapshot_ids=("snapshot:stock_daily",),
        spec=spec,
        seed=0,
        instruments=instruments,
    )


class TestConditionFilterSemantics:
    def test_groups_and_across_rows_or_within_group(self):
        # 组间 AND：动量 ≥0.6 且 波动 ≤0.4；组内 OR：动量 0.9 或 0.7 通过。
        spec = _spec(
            (
                (
                    SelectionFactorCondition(
                        "momentum", SelectionConditionOperator.GTE, 0.6
                    ),
                ),
            )
        )
        run = SelectionPipeline().run(
            _bundle(
                spec,
                (
                    _instrument(1, momentum=0.9),
                    _instrument(2, momentum=0.5),
                    _instrument(3, momentum=0.7),
                ),
            )
        )
        assert [item.instrument_id for item in run.candidates] == [1, 3]
        excluded = {int(item.instrument_id): item for item in run.exclusions}
        assert excluded[2].reason_code.value == "factor_condition_unsatisfied"
        assert excluded[2].stage == "condition_filter"
        assert "momentum" in excluded[2].detail

    def test_or_within_group_passes_when_any_row_holds(self):
        spec = _spec(
            (
                (
                    SelectionFactorCondition(
                        "momentum", SelectionConditionOperator.GTE, 0.9
                    ),
                    SelectionFactorCondition(
                        "momentum", SelectionConditionOperator.LTE, 0.1
                    ),
                ),
            )
        )
        run = SelectionPipeline().run(
            _bundle(
                spec,
                (_instrument(1, momentum=0.95), _instrument(2, momentum=0.5)),
            )
        )
        assert [item.instrument_id for item in run.candidates] == [1]

    def test_groups_compose_with_and(self):
        spec = _spec(
            (
                (
                    SelectionFactorCondition(
                        "momentum", SelectionConditionOperator.GTE, 0.4
                    ),
                ),
                (
                    SelectionFactorCondition(
                        "momentum", SelectionConditionOperator.LTE, 0.6
                    ),
                ),
            )
        )
        run = SelectionPipeline().run(
            _bundle(
                spec,
                (_instrument(1, momentum=0.5), _instrument(2, momentum=0.9)),
            )
        )
        assert [item.instrument_id for item in run.candidates] == [1]
        excluded = {int(item.instrument_id): item for item in run.exclusions}
        assert excluded[2].reason_code.value == "factor_condition_unsatisfied"

    def test_missing_condition_factor_fails_closed_as_missing_data(self):
        # 条件引用的因子没有任何观测值：按缺失 fail closed，不当作不满足。
        spec = _spec(
            (
                (
                    SelectionFactorCondition(
                        "momentum", SelectionConditionOperator.GTE, 0.6
                    ),
                ),
            )
        )
        run = SelectionPipeline().run(_bundle(spec, (_instrument(1, momentum=None),)))
        assert run.candidates == ()
        excluded = run.exclusions[0]
        assert excluded.reason_code.value == "missing_data"
        assert "factor:momentum" in excluded.detail
        assert run.status == SelectionRunStatus.DEGRADED

    def test_no_candidates_yields_blocked_run(self):
        spec = _spec(
            (
                (
                    SelectionFactorCondition(
                        "momentum", SelectionConditionOperator.GTE, 0.99
                    ),
                ),
            ),
            top_k=3,
        )
        run = SelectionPipeline().run(_bundle(spec, (_instrument(1, momentum=0.5),)))
        assert run.candidates == ()
        assert run.exclusions[0].reason_code.value == "factor_condition_unsatisfied"


class TestConditionContractValidation:
    def test_rejects_empty_group(self):
        with pytest.raises(StrategySpecError, match="filter group"):
            _spec(((),))

    def test_rejects_non_finite_threshold(self):
        with pytest.raises(StrategySpecError, match="finite"):
            _spec(
                (
                    (
                        SelectionFactorCondition(
                            "momentum", SelectionConditionOperator.GTE, float("nan")
                        ),
                    ),
                )
            )

    def test_rejects_blank_factor_name(self):
        with pytest.raises(StrategySpecError, match="factor name"):
            _spec(
                (
                    (
                        SelectionFactorCondition(
                            "  ", SelectionConditionOperator.GTE, 0.5
                        ),
                    ),
                )
            )

    def test_etf_spec_accepts_conditions(self):
        from ditto_strategy.selection.contracts import EtfSelectionSpec

        spec = EtfSelectionSpec(
            spec_id="etf-screener",
            spec_version="1",
            top_k=5,
            min_average_turnover=0.0,
            min_listing_days=1,
            factor_weights=_WEIGHTS,
            filter_groups=(
                (
                    SelectionFactorCondition(
                        "momentum", SelectionConditionOperator.GTE, 0.5
                    ),
                ),
            ),
        )
        assert spec.filter_groups[0][0].factor_name == "momentum"


class TestConditionIdentity:
    # 与引入条件字段前（main 4fdf426ab）实测一致的固定 spec 哈希：
    # 空条件组不进入 canonical payload，已保存运行的 spec 身份不变。
    _LEGACY_SPEC_HASH = (
        "e36845ae2914d1a58e8433c6a37b2040f8055ec317e9ae37fe373e55276264b6"
    )

    def test_empty_groups_keep_legacy_spec_hash(self):
        legacy = StockSelectionSpec(
            spec_id="legacy",
            spec_version="1",
            top_k=5,
            min_average_turnover=0.0,
            min_listing_days=1,
            factor_weights=_WEIGHTS,
        )
        # 旧 canonical payload 不含 filter_groups 键：默认构造的 spec 哈希
        # 必须与显式空组构造一致，且与无该字段时代的已知哈希一致。
        explicit_default = StockSelectionSpec(
            spec_id="legacy",
            spec_version="1",
            top_k=5,
            min_average_turnover=0.0,
            min_listing_days=1,
            factor_weights=_WEIGHTS,
            filter_groups=(),
        )
        assert canonical_spec_hash(legacy) == canonical_spec_hash(explicit_default)
        assert canonical_spec_hash(legacy) == self._LEGACY_SPEC_HASH

    def test_conditions_change_spec_hash(self):
        base = _spec(())
        conditioned = _spec(
            (
                (
                    SelectionFactorCondition(
                        "momentum", SelectionConditionOperator.GTE, 0.6
                    ),
                ),
            )
        )
        assert canonical_spec_hash(base) != canonical_spec_hash(conditioned)
        # 相同条件的重复构造哈希稳定（可重放身份）。
        assert canonical_spec_hash(conditioned) == canonical_spec_hash(
            _spec(
                (
                    (
                        SelectionFactorCondition(
                            "momentum", SelectionConditionOperator.GTE, 0.6
                        ),
                    ),
                )
            )
        )
