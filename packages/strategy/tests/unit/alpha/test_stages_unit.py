"""Tests for built-in Pipeline stages.

Covers Universe, Signal, Scoring, Filtering, Selection, TrendFilter,
RiskLockFilter DecisionStage implementations with AAA test pattern.
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_strategy.alpha.builtins.filtering import (
    FilterCondition,
    FilteringStage,
    RiskLockFilter,
    TrendFilterStage,
)
from ditto_strategy.alpha.builtins.scoring import (
    FactorScoreColumnBinding,
    ScoringMethod,
    ScoringStage,
)
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.builtins.signal import SignalStage
from ditto_strategy.alpha.builtins.universe import UniverseStage
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceCollector
from ditto_strategy.errors import StrategySpecError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


@pytest.fixture
def sample_instruments() -> pl.DataFrame:
    """3-row DecisionFrame with instrument_id only."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
        }
    )


@pytest.fixture
def sample_instruments_with_signal() -> pl.DataFrame:
    """3-row DecisionFrame with instrument_id and momentum signal."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
            "momentum": [0.85, 0.62, 0.41],
        }
    )


@pytest.fixture
def sample_instruments_with_score() -> pl.DataFrame:
    """3-row DecisionFrame with instrument_id and score."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
            "score": [0.9, 0.7, 0.3],
        }
    )


# ---------------------------------------------------------------------------
# UniverseStage
# ---------------------------------------------------------------------------


class TestUniverseStage:
    def test_empty_whitelist_returns_empty_frame(
        self,
        sample_instruments: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """空白名单应返回空 frame。"""
        stage = UniverseStage(instrument_ids=frozenset())
        result = stage.process(sample_instruments, empty_context)
        assert result.is_empty()

    def test_all_instruments_in_whitelist(
        self,
        sample_instruments: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """白名单包含所有标的时应原样返回。"""
        ids = frozenset({1, 2, 3})
        stage = UniverseStage(instrument_ids=ids)
        result = stage.process(sample_instruments, empty_context)
        assert result.shape == (3, 1)
        assert set(result["instrument_id"].to_list()) == ids

    def test_partial_match_keeps_matching(
        self,
        sample_instruments: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """白名单只包含部分标的时，应保留匹配的行。"""
        ids = frozenset({1, 2})
        stage = UniverseStage(instrument_ids=ids)
        result = stage.process(sample_instruments, empty_context)
        assert result.shape == (2, 1)
        assert set(result["instrument_id"].to_list()) == ids

    def test_missing_column_raises_error(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """缺少 instrument_id 时应由 validate_frame 抛出 StrategySpecError。"""
        stage = UniverseStage(instrument_ids=frozenset({1}))
        bad_frame = pl.DataFrame({"name": ["a", "b"]})
        with pytest.raises(StrategySpecError, match="missing required columns"):
            stage.process(bad_frame, empty_context)


# ---------------------------------------------------------------------------
# SignalStage
# ---------------------------------------------------------------------------


class TestSignalStage:
    def test_rename_source_column(
        self,
        sample_instruments_with_signal: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """指定 source_column 时，应重命名为 signal_column。"""
        stage = SignalStage(signal_column="signal_value", source_column="momentum")
        result = stage.process(sample_instruments_with_signal, empty_context)
        assert "signal_value" in result.columns
        assert "momentum" in result.columns
        assert result["signal_value"].to_list() == [0.85, 0.62, 0.41]

    def test_signal_column_already_exists(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """source_column=None 且 signal_column 已在 frame 中时，原样返回。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "signal_value": [0.5],
            }
        )
        stage = SignalStage(signal_column="signal_value", source_column=None)
        result = stage.process(frame, empty_context)
        assert result.shape == (1, 2)
        assert result["signal_value"][0] == 0.5

    def test_no_source_no_signal_fills_null(
        self,
        sample_instruments: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """source_column=None 且 signal_column 不存在时，填充 null 列。"""
        stage = SignalStage(signal_column="signal_value", source_column=None)
        result = stage.process(sample_instruments, empty_context)
        assert "signal_value" in result.columns
        assert result["signal_value"].null_count() == 3

    def test_empty_frame_no_error(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """空 frame 不应报错。"""
        empty_frame = pl.DataFrame(
            {"instrument_id": []},
            schema={"instrument_id": pl.Int64},
        )
        stage = SignalStage(signal_column="signal_value", source_column=None)
        result = stage.process(empty_frame, empty_context)
        assert result.is_empty()
        assert "signal_value" in result.columns


# ---------------------------------------------------------------------------
# ScoringStage
# ---------------------------------------------------------------------------


class TestScoringStage:
    @pytest.mark.parametrize(
        ("ascending", "expected_scores", "expected_top"),
        [
            pytest.param(
                False,
                {"LOW": 1.0 / 3.0, "MID": 2.0 / 3.0, "HIGH": 1.0},
                "HIGH",
                id="larger-signal-is-better",
            ),
            pytest.param(
                True,
                {"LOW": 1.0, "MID": 2.0 / 3.0, "HIGH": 1.0 / 3.0},
                "LOW",
                id="smaller-signal-is-better",
            ),
        ],
    )
    def test_rank_direction_drives_expected_selector_top_k(
        self,
        empty_context: StrategyContext,
        ascending: bool,
        expected_scores: dict[str, float],
        expected_top: str,
    ) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": ["LOW", "MID", "HIGH"],
                "signal_value": [10.0, 20.0, 30.0],
            }
        )

        scored = ScoringStage(
            method=ScoringMethod.RANK,
            ascending=ascending,
        ).process(frame, empty_context)
        selected = SelectionStage(top_k=1).process(scored, empty_context)

        assert dict(
            scored.select("instrument_id", "score").iter_rows()
        ) == pytest.approx(expected_scores)
        assert selected["instrument_id"].to_list() == [expected_top]

    def test_zscore_honors_smaller_signal_is_better(
        self,
        empty_context: StrategyContext,
    ) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": ["LOW", "MID", "HIGH"],
                "signal_value": [10.0, 20.0, 30.0],
            }
        )

        result = ScoringStage(
            method=ScoringMethod.ZSCORE,
            ascending=True,
        ).process(frame, empty_context)
        scores = dict(result.select("instrument_id", "score").iter_rows())

        assert scores["LOW"] > scores["MID"] > scores["HIGH"]

    def test_raw_factor_evidence_is_exact_and_adds_to_final_score(
        self,
        empty_context: StrategyContext,
    ) -> None:
        collector = SelectionEvidenceCollector()
        collector.begin_rebalance("2026-07-22")
        bindings = (
            FactorScoreColumnBinding(
                factor_id="quality",
                raw_column="factor_0",
                processed_column="factor_0",
                normalized_column="rank_factor_0",
                weight=0.6,
            ),
            FactorScoreColumnBinding(
                factor_id="value",
                raw_column="factor_1",
                processed_column="factor_1",
                normalized_column="rank_factor_1",
                weight=0.4,
            ),
        )
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "factor_0": [10.0, 20.0],
                "rank_factor_0": [0.5, 1.0],
                "factor_1": [30.0, 40.0],
                "rank_factor_1": [1.0, 0.5],
                "signal_value": [0.7, 0.8],
            }
        )

        result = ScoringStage(
            method=ScoringMethod.RAW,
            output_column="final_score",
            factor_bindings=bindings,
            evidence_sink=collector,
        ).process(frame, empty_context)
        collector.commit_rebalance()
        contributions = collector.snapshot().factor_contributions

        assert result["final_score"].to_list() == [0.7, 0.8]
        assert [
            (
                event.instrument_id,
                event.factor_name,
                event.raw_value,
                event.processed_value,
                event.normalized_value,
                event.weight,
                event.contribution,
                event.factor_signal_score,
            )
            for event in contributions
        ] == [
            (1, "quality", 10.0, 10.0, 0.5, 0.6, 0.3, 0.7),
            (2, "quality", 20.0, 20.0, 1.0, 0.6, 0.6, 0.8),
            (1, "value", 30.0, 30.0, 1.0, 0.4, 0.4, 0.7),
            (2, "value", 40.0, 40.0, 0.5, 0.4, 0.2, 0.8),
        ]
        for instrument_id, score in result.select(
            "instrument_id", "final_score"
        ).iter_rows():
            assert sum(
                event.contribution or 0.0
                for event in contributions
                if event.instrument_id == instrument_id
            ) == pytest.approx(score)

    @pytest.mark.parametrize("method", [ScoringMethod.RANK, ScoringMethod.ZSCORE])
    def test_non_additive_scoring_rejects_factor_evidence(
        self,
        method: ScoringMethod,
    ) -> None:
        collector = SelectionEvidenceCollector()

        with pytest.raises(StrategySpecError) as exc_info:
            ScoringStage(
                method=method,
                factor_bindings=(
                    FactorScoreColumnBinding(
                        factor_id="quality",
                        raw_column="factor_0",
                        processed_column="factor_0",
                        normalized_column="rank_factor_0",
                        weight=1.0,
                    ),
                ),
                evidence_sink=collector,
            )

        assert exc_info.value.details["reason"] == (
            "non_additive_factor_evidence_scoring"
        )

    @pytest.mark.parametrize(
        ("weights", "signal_values", "expected_contributions"),
        [
            pytest.param((1.0, 0.0), [0.5, 1.0], [0.5, 1.0, 0.0, 0.0], id="one-zero"),
            pytest.param((0.0, 0.0), [0.0, 0.0], [0.0, 0.0, 0.0, 0.0], id="all-zero"),
        ],
    )
    def test_zero_weight_null_factor_emits_explicit_zero_contribution(
        self,
        empty_context: StrategyContext,
        weights: tuple[float, float],
        signal_values: list[float],
        expected_contributions: list[float],
    ) -> None:
        collector = SelectionEvidenceCollector()
        collector.begin_rebalance("2026-07-22")
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "factor_0": [10.0, 20.0],
                "rank_factor_0": [0.5, 1.0],
                "factor_1": [None, None],
                "rank_factor_1": [None, None],
                "signal_value": signal_values,
            }
        )
        bindings = tuple(
            FactorScoreColumnBinding(
                factor_id=f"factor-{index}",
                raw_column=f"factor_{index}",
                processed_column=f"factor_{index}",
                normalized_column=f"rank_factor_{index}",
                weight=weight,
            )
            for index, weight in enumerate(weights)
        )

        ScoringStage(
            method=ScoringMethod.RAW,
            factor_bindings=bindings,
            evidence_sink=collector,
        ).process(frame, empty_context)
        collector.commit_rebalance()

        assert [
            event.contribution for event in collector.snapshot().factor_contributions
        ] == expected_contributions

    def test_non_finite_factor_evidence_is_recorded_as_missing(
        self,
        empty_context: StrategyContext,
    ) -> None:
        collector = SelectionEvidenceCollector()
        collector.begin_rebalance("2026-07-22")
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "factor_0": [float("nan")],
                "rank_factor_0": [float("inf")],
                "signal_value": [float("-inf")],
            }
        )

        ScoringStage(
            method=ScoringMethod.RAW,
            factor_bindings=(
                FactorScoreColumnBinding(
                    factor_id="value",
                    raw_column="factor_0",
                    processed_column="factor_0",
                    normalized_column="rank_factor_0",
                    weight=1.0,
                ),
            ),
            evidence_sink=collector,
        ).process(frame, empty_context)
        collector.commit_rebalance()

        event = collector.snapshot().factor_contributions[0]
        assert event.raw_value is None
        assert event.processed_value is None
        assert event.normalized_value is None
        assert event.contribution is None
        assert event.factor_signal_score is None

    def test_raw_mode(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """RAW 模式：score = signal_value 直接复制。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "signal_value": [0.85, 0.62],
            }
        )
        stage = ScoringStage(method=ScoringMethod.RAW, output_column="score")
        result = stage.process(frame, empty_context)
        assert result["score"].to_list() == [0.85, 0.62]

    def test_rank_mode(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """RANK 模式：score = rank / count (百分位排名)。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "signal_value": [10.0, 30.0, 20.0],
            }
        )
        stage = ScoringStage(method=ScoringMethod.RANK, output_column="score")
        result = stage.process(frame, empty_context)
        scores = result["score"].sort().to_list()
        # descending=True by default: C(20)=1/3, B(30)=2/3, A(10)=3/3
        assert scores[0] == pytest.approx(1.0 / 3.0)
        assert scores[1] == pytest.approx(2.0 / 3.0)
        assert scores[2] == pytest.approx(3.0 / 3.0)

    def test_zscore_mode(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """ZSCORE 模式：score = (value - mean) / std。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "signal_value": [1.0, 2.0, 3.0],
            }
        )
        stage = ScoringStage(method=ScoringMethod.ZSCORE, output_column="score")
        result = stage.process(frame, empty_context)
        scores = result["score"].sort().to_list()
        mean = 2.0
        std = 1.0
        assert scores[0] == pytest.approx((1.0 - mean) / std)
        assert scores[1] == pytest.approx((2.0 - mean) / std)
        assert scores[2] == pytest.approx((3.0 - mean) / std)

    def test_ascending_reverses_rank(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """ascending=True 时 rank 方向反转（小值排名靠前得分高）。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "signal_value": [10.0, 30.0, 20.0],
            }
        )
        stage = ScoringStage(
            method=ScoringMethod.RANK,
            ascending=True,
            output_column="score",
        )
        result = stage.process(frame, empty_context)
        scores = result["score"].sort().to_list()
        # ascending=True: A(10)=3/3, C(20)=2/3, B(30)=1/3
        assert scores[0] == pytest.approx(1.0 / 3.0)
        assert scores[1] == pytest.approx(2.0 / 3.0)
        assert scores[2] == pytest.approx(3.0 / 3.0)

    def test_null_signal_produces_null_score(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """signal_value 中包含 null 时，对应 score 应为 null。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "signal_value": [1.0, None, 3.0],
            }
        )
        stage = ScoringStage(method=ScoringMethod.RANK, output_column="score")
        result = stage.process(frame, empty_context)
        assert result["score"][1] is None

    def test_all_null_all_null_scores(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """全部 signal_value 为 null 时，全部 score 应为 null。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "signal_value": [None, None],
            }
        )
        stage = ScoringStage(method=ScoringMethod.RANK, output_column="score")
        result = stage.process(frame, empty_context)
        assert result["score"].null_count() == 2

    def test_missing_input_column_fills_null(
        self,
        sample_instruments: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """input_column 不存在时，填充 null。"""
        stage = ScoringStage(
            method=ScoringMethod.RANK,
            output_column="score",
            input_column="signal_value",
        )
        result = stage.process(sample_instruments, empty_context)
        assert "score" in result.columns
        assert result["score"].null_count() == 3

    def test_zscore_std_zero_returns_zero(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """ZSCORE 模式下 std=0（所有值相同）时，score 应为 0。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "signal_value": [5.0, 5.0, 5.0],
            }
        )
        stage = ScoringStage(method=ScoringMethod.ZSCORE, output_column="score")
        result = stage.process(frame, empty_context)
        assert result["score"].to_list() == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# FilteringStage
# ---------------------------------------------------------------------------


class TestFilteringStage:
    def test_no_conditions_returns_unchanged(
        self,
        sample_instruments_with_signal: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """无过滤条件时原样返回。"""
        stage = FilteringStage(conditions=())
        result = stage.process(sample_instruments_with_signal, empty_context)
        assert result.shape == (3, 2)

    def test_single_condition_filters(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """单条过滤条件应正确过滤。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12, 13],
                "score": [0.9, 0.5, 0.3, 0.7],
            }
        )
        stage = FilteringStage(
            conditions=(
                FilterCondition(
                    name="min_score",
                    column="score",
                    min_value=0.5,
                ),
            )
        )
        result = stage.process(frame, empty_context)
        assert result.shape == (3, 2)
        assert set(result["instrument_id"].to_list()) == {10, 11, 13}

    def test_multiple_conditions_and(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """多条条件应为 AND 组合。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12, 13],
                "score": [0.9, 0.5, 0.3, 0.7],
            }
        )
        stage = FilteringStage(
            conditions=(
                FilterCondition(
                    name="min_score",
                    column="score",
                    min_value=0.5,
                ),
                FilterCondition(
                    name="max_score",
                    column="score",
                    max_value=0.7,
                ),
            )
        )
        result = stage.process(frame, empty_context)
        assert result.shape == (2, 2)
        assert set(result["instrument_id"].to_list()) == {11, 13}

    def test_exclude_nulls_true(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """exclude_nulls=True 时排除 null 值。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "score": [0.5, None, 0.8],
            }
        )
        stage = FilteringStage(
            conditions=(
                FilterCondition(
                    name="no_null_score",
                    column="score",
                    exclude_nulls=True,
                ),
            )
        )
        result = stage.process(frame, empty_context)
        assert result.shape == (2, 2)
        assert set(result["instrument_id"].to_list()) == {10, 12}

    def test_exclude_nulls_false(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """exclude_nulls=False 时保留 null 值行。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "score": [0.5, None, 0.8],
            }
        )
        stage = FilteringStage(
            conditions=(
                FilterCondition(
                    name="allow_null",
                    column="score",
                    exclude_nulls=False,
                    min_value=0.0,
                ),
            )
        )
        result = stage.process(frame, empty_context)
        # B has null score, exclude_nulls=False, but min_value=0.0
        # null comparisons return null -> null is not >= 0.0 -> B filtered
        # This is expected Polars behavior: null != 0.0
        assert result.shape == (2, 2)

    def test_missing_column_raises(
        self,
        sample_instruments: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """过滤条件引用不存在的列时 Polars 应报错。"""
        stage = FilteringStage(
            conditions=(
                FilterCondition(
                    name="bad_col",
                    column="nonexistent",
                    min_value=0.0,
                ),
            )
        )
        with pytest.raises(pl.ColumnNotFoundError):
            stage.process(sample_instruments, empty_context)


# ---------------------------------------------------------------------------
# SelectionStage
# ---------------------------------------------------------------------------


class TestSelectionStage:
    @pytest.mark.parametrize(
        ("instrument_ids", "expected"),
        [
            pytest.param([3, 1, 2, 0], [1, 2], id="integer-instruments"),
            pytest.param(["C", "A", "B", "NULL"], ["A", "B"], id="text-instruments"),
        ],
    )
    def test_top_k_ties_use_canonical_instrument_order_independent_of_input(
        self,
        empty_context: StrategyContext,
        instrument_ids: list[int] | list[str],
        expected: list[int] | list[str],
    ) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": instrument_ids,
                "score": [0.9, 0.9, 0.9, None],
            }
        )
        stage = SelectionStage(top_k=2, score_column="score")

        original = stage.process(frame, empty_context)
        reversed_input = stage.process(frame.reverse(), empty_context)

        assert original["instrument_id"].to_list() == expected
        assert reversed_input["instrument_id"].to_list() == expected
        assert original["score"].null_count() == 0
        assert reversed_input["score"].null_count() == 0

    def test_top_k_larger_than_rows_returns_all(
        self,
        sample_instruments_with_score: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """top_k 大于行数时返回全部行（已排序）。"""
        stage = SelectionStage(top_k=10, score_column="score")
        result = stage.process(sample_instruments_with_score, empty_context)
        assert result.shape == (3, 2)
        # descending by default, so 0.9, 0.7, 0.3
        assert result["score"][0] == 0.9
        assert result["score"][1] == 0.7
        assert result["score"][2] == 0.3

    def test_top_k_zero_returns_empty(
        self,
        sample_instruments_with_score: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """top_k=0 时返回空 frame。"""
        stage = SelectionStage(top_k=0, score_column="score")
        result = stage.process(sample_instruments_with_score, empty_context)
        assert result.is_empty()

    def test_null_scores_sorted_last(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """null score 应排在最后（nulls_last=True）。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12, 13],
                "score": [0.9, None, 0.3, 0.7],
            }
        )
        stage = SelectionStage(top_k=3, score_column="score")
        result = stage.process(frame, empty_context)
        assert result.shape == (3, 2)
        # Top 3: 0.9, 0.7, 0.3; null excluded
        assert result["score"].to_list() == [0.9, 0.7, 0.3]

    def test_ascending_sort(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """ascending=True 时小值优先。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "score": [0.9, 0.3, 0.7],
            }
        )
        stage = SelectionStage(top_k=2, score_column="score", ascending=True)
        result = stage.process(frame, empty_context)
        assert result.shape == (2, 2)
        assert result["score"].to_list() == [0.3, 0.7]

    def test_empty_input_returns_empty(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """空输入应返回空 frame。"""
        empty_frame = pl.DataFrame(
            {
                "instrument_id": [],
                "score": [],
            },
            schema={"instrument_id": pl.Int64, "score": pl.Float64},
        )
        stage = SelectionStage(top_k=5, score_column="score")
        result = stage.process(empty_frame, empty_context)
        assert result.is_empty()


# ---------------------------------------------------------------------------
# TrendFilterStage
# ---------------------------------------------------------------------------


class TestTrendFilterStage:
    def test_long_direction_keeps_positive_signals(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """long 方向保留 signal >= threshold 的标的。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12, 13],
                "signal_value": [0.05, 0.12, -0.03, 0.0],
            }
        )
        stage = TrendFilterStage(threshold=0.05, direction="long")
        result = stage.process(frame, empty_context)
        # 10=0.05>=0.05, 11=0.12>=0.05, 12=-0.03 filtered, 13=0.0<0.05 filtered
        assert set(result["instrument_id"].to_list()) == {10, 11}

    def test_long_direction_filters_negative_signals(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """long 方向过滤掉 signal < threshold 的标的。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "signal_value": [0.05, -0.10, 0.0],
            }
        )
        stage = TrendFilterStage(threshold=0.05, direction="long")
        result = stage.process(frame, empty_context)
        # Only 10 meets signal_value >= 0.05; 11 is negative, 12 is 0.0 < 0.05
        assert set(result["instrument_id"].to_list()) == {10}

    def test_short_direction_keeps_negative_signals(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """short 方向保留 signal <= -threshold 的标的。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12, 13],
                "signal_value": [0.05, -0.12, -0.03, 0.0],
            }
        )
        stage = TrendFilterStage(threshold=0.05, direction="short")
        result = stage.process(frame, empty_context)
        assert set(result["instrument_id"].to_list()) == {11}

    def test_both_direction_keeps_strong_signals(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """both 方向保留 |signal| >= threshold 的标的。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12, 13, 14],
                "signal_value": [0.15, -0.12, 0.02, -0.01, 0.10],
            }
        )
        stage = TrendFilterStage(threshold=0.10, direction="both")
        result = stage.process(frame, empty_context)
        assert set(result["instrument_id"].to_list()) == {10, 11, 14}

    def test_threshold_zero_keeps_all_positive(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """threshold=0 时 long 方向保留所有非负信号。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "signal_value": [0.0, 0.05, -0.01],
            }
        )
        stage = TrendFilterStage(threshold=0.0, direction="long")
        result = stage.process(frame, empty_context)
        assert set(result["instrument_id"].to_list()) == {10, 11}

    def test_empty_frame_no_error(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """空 frame 不报错。"""
        frame = pl.DataFrame(
            {"instrument_id": [], "signal_value": []},
            schema={"instrument_id": pl.Int64, "signal_value": pl.Float64},
        )
        stage = TrendFilterStage(threshold=0.0, direction="long")
        result = stage.process(frame, empty_context)
        assert result.is_empty()

    def test_no_signal_column_raises(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """signal_column 不存在时由 Polars 抛出错误。"""
        frame = pl.DataFrame({"instrument_id": [10, 11]})
        stage = TrendFilterStage(threshold=0.0, direction="long")
        with pytest.raises(pl.ColumnNotFoundError):
            stage.process(frame, empty_context)

    def test_frozen(self) -> None:
        """TrendFilterStage 是 frozen dataclass。"""
        stage = TrendFilterStage(threshold=0.05)
        with pytest.raises(AttributeError):
            stage.threshold = 0.1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FilteringStage boundary
# ---------------------------------------------------------------------------


class TestFilteringStageBoundary:
    """FilteringStage 边界条件测试。"""

    def test_empty_frame(self, empty_context: StrategyContext) -> None:
        """空 frame 带过滤条件不应崩溃，仍返回空 frame。"""
        empty_frame = pl.DataFrame(
            {"instrument_id": [], "score": []},
            schema={"instrument_id": pl.Int64, "score": pl.Float64},
        )
        stage = FilteringStage(
            conditions=(
                FilterCondition(
                    name="min_score",
                    column="score",
                    min_value=0.5,
                ),
            )
        )
        result = stage.process(empty_frame, empty_context)
        assert result.is_empty()

    def test_all_filtered(self, empty_context: StrategyContext) -> None:
        """所有行被过滤掉时应返回空 frame。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "score": [0.1, 0.2, 0.3],
            }
        )
        stage = FilteringStage(
            conditions=(
                FilterCondition(
                    name="min_score",
                    column="score",
                    min_value=0.9,
                ),
            )
        )
        result = stage.process(frame, empty_context)
        assert result.is_empty()

    def test_min_greater_than_max_contradiction(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """min_value > max_value 矛盾条件：没有行能同时满足，返回空 frame。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "score": [0.3, 0.5, 0.7],
            }
        )
        stage = FilteringStage(
            conditions=(
                FilterCondition(
                    name="contradiction",
                    column="score",
                    min_value=0.8,
                    max_value=0.4,
                ),
            )
        )
        result = stage.process(frame, empty_context)
        assert result.is_empty()

    def test_only_null_exclusion(self, empty_context: StrategyContext) -> None:
        """仅有 exclude_nulls 条件（无 min/max）时，保留非 null 行。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12, 13],
                "score": [0.5, None, 0.8, None],
            }
        )
        stage = FilteringStage(
            conditions=(
                FilterCondition(
                    name="no_null_score",
                    column="score",
                    exclude_nulls=True,
                ),
            )
        )
        result = stage.process(frame, empty_context)
        assert result.shape == (2, 2)
        assert set(result["instrument_id"].to_list()) == {10, 12}

    def test_frozen(self) -> None:
        """FilteringStage 是 frozen dataclass，不可修改属性。"""
        stage = FilteringStage(
            conditions=(FilterCondition(name="t", column="c"),),
        )
        with pytest.raises(AttributeError):
            stage.conditions = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ScoringStage boundary
# ---------------------------------------------------------------------------


class TestScoringStageBoundary:
    """ScoringStage 边界条件测试。"""

    @pytest.mark.parametrize(
        "method",
        [ScoringMethod.RAW, ScoringMethod.RANK, ScoringMethod.ZSCORE],
    )
    def test_empty_frame(
        self,
        empty_context: StrategyContext,
        method: ScoringMethod,
    ) -> None:
        """空 frame：返回空 frame，带 score 列。"""
        empty_frame = pl.DataFrame(
            {"instrument_id": [], "signal_value": []},
            schema={"instrument_id": pl.Int64, "signal_value": pl.Float64},
        )
        stage = ScoringStage(method=method, output_column="score")
        result = stage.process(empty_frame, empty_context)
        assert result.is_empty()
        assert "score" in result.columns

    def test_single_row_raw(self, empty_context: StrategyContext) -> None:
        """RAW 模式单行：score = signal_value。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "signal_value": [0.42],
            }
        )
        stage = ScoringStage(method=ScoringMethod.RAW, output_column="score")
        result = stage.process(frame, empty_context)
        assert result["score"][0] == pytest.approx(0.42)

    def test_single_row_rank(self, empty_context: StrategyContext) -> None:
        """RANK 模式单行：score = 1.0（rank/count = 1/1）。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "signal_value": [0.42],
            }
        )
        stage = ScoringStage(method=ScoringMethod.RANK, output_column="score")
        result = stage.process(frame, empty_context)
        assert result["score"][0] == pytest.approx(1.0)

    def test_single_row_zscore(self, empty_context: StrategyContext) -> None:
        """ZSCORE 模式单行：std(ddof=1) 为 null，score 应为 null。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "signal_value": [0.42],
            }
        )
        stage = ScoringStage(method=ScoringMethod.ZSCORE, output_column="score")
        result = stage.process(frame, empty_context)
        # Polars std(ddof=1) 对单行返回 null，null == 0 为 null（非 True），
        # 走 otherwise 分支：(col - mean) / null = null
        assert result["score"][0] is None


# ---------------------------------------------------------------------------
# RiskLockFilter
# ---------------------------------------------------------------------------


class TestRiskLockFilter:
    def test_no_locked_instruments(
        self,
        sample_instruments: pl.DataFrame,
        empty_context: StrategyContext,
    ) -> None:
        """无锁定标的时应原样返回。"""
        stage = RiskLockFilter()
        result = stage.process(sample_instruments, empty_context)
        assert result.shape == (3, 1)

    def test_partial_lock(
        self,
        sample_instruments: pl.DataFrame,
    ) -> None:
        """部分标的被锁定时应过滤掉锁定行。"""
        ctx = StrategyContext(
            risk_locked_instruments={
                1: ("stop_loss", None),
            },
        )
        stage = RiskLockFilter()
        result = stage.process(sample_instruments, ctx)
        assert result.shape == (2, 1)
        assert set(result["instrument_id"].to_list()) == {2, 3}

    def test_all_locked(
        self,
        sample_instruments: pl.DataFrame,
    ) -> None:
        """所有标的被锁定时应返回空 frame。"""
        ctx = StrategyContext(
            risk_locked_instruments={
                1: ("stop_loss", None),
                2: ("stop_loss", None),
                3: ("stop_loss", None),
            },
        )
        stage = RiskLockFilter()
        result = stage.process(sample_instruments, ctx)
        assert result.is_empty()

    def test_empty_frame_with_locks(self) -> None:
        """空 frame 加锁定列表仍返回空 frame。"""
        ctx = StrategyContext(
            risk_locked_instruments={
                1: ("stop_loss", None),
            },
        )
        empty_frame = pl.DataFrame(
            {"instrument_id": []},
            schema={"instrument_id": pl.Int64},
        )
        stage = RiskLockFilter()
        result = stage.process(empty_frame, ctx)
        assert result.is_empty()

    def test_frozen(self) -> None:
        """RiskLockFilter 是 frozen dataclass。"""
        stage = RiskLockFilter()
        with pytest.raises(AttributeError):
            stage.process = lambda *a: pl.DataFrame()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


class TestFullPipelineIntegration:
    """端到端测试：Universe -> Signal -> Score -> Filter -> Select。"""

    def test_full_pipeline_universe_signal_score_filter_select(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """完整 Pipeline：白名单过滤 -> 信号提取 -> 评分 -> 过滤 -> 选取。"""
        # Arrange: 5 个标的，只有 3 个在白名单中
        frame = pl.DataFrame(
            {
                "instrument_id": [
                    10,
                    11,
                    12,
                    13,
                    14,
                ],
                "momentum": [0.1, 0.8, 0.5, 0.9, 0.2],
            }
        )

        # Stage 1: Universe - 保留 10, 11, 12, 13
        universe = UniverseStage(instrument_ids=frozenset({10, 11, 12, 13}))

        # Stage 2: Signal - 将 momentum 重命名为 signal_value
        signal = SignalStage(
            signal_column="signal_value",
            source_column="momentum",
        )

        # Stage 3: Scoring - RANK 模式
        scoring = ScoringStage(method=ScoringMethod.RANK, output_column="score")

        # Stage 4: Filtering - 保留 score >= 0.4
        filtering = FilteringStage(
            conditions=(
                FilterCondition(
                    name="min_score",
                    column="score",
                    min_value=0.4,
                ),
            )
        )

        # Stage 5: Selection - top 2
        selection = SelectionStage(top_k=2, score_column="score")

        # Act
        result = frame
        for stage in [universe, signal, scoring, filtering, selection]:
            result = stage.process(result, empty_context)

        # Assert: 默认 larger-is-better，因此 13(0.9)=1.0、11(0.8)=0.75、
        #         12(0.5)=0.5、10(0.1)=0.25。
        # Filter score >= 0.4 排除 10；Top 2 为 13 和 11。
        assert result.shape == (2, 4)  # instrument_id, momentum, signal_value, score
        assert set(result["instrument_id"].to_list()) == {11, 13}
