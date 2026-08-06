"""Unit tests for evaluation/evaluator/_report_builder.py.

Tests EvaluationConfig defaults, compute_optional_analysis flag combinations,
and assemble_report correct assembly of FactorEvaluationReport.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta
from types import MappingProxyType

import polars as pl
import pytest
from ditto_features.evaluation.evaluator._helpers import (
    compute_quantile_annual_returns,
    empty_report,
    estimate_avg_turnover,
    prepare_data,
    resolve_period,
)
from ditto_features.evaluation.evaluator._report_builder import (
    EvaluationConfig,
    ICMetricsData,
    OptionalAnalysisData,
    QuantileMetricsData,
    assemble_report,
    compute_optional_analysis,
)
from ditto_features.evaluation.report import (
    R3_FACTOR_DIAGNOSTIC_METRIC_IDS,
    R3_FACTOR_DIAGNOSTICS_SCHEMA_VERSION,
    FactorEvaluationReport,
    ICSummary,
    LongShortResult,
    R3FactorDiagnosticsProjection,
    R3FactorDiagnosticsProvenance,
    TailRiskMetrics,
    project_r3_factor_diagnostics,
    r3_factor_diagnostics_content_hash,
    r3_factor_diagnostics_projection_hash,
)


def _diagnostic_provenance(
    *,
    period: tuple[str, str] = ("2024-01-01", "2024-12-31"),
) -> R3FactorDiagnosticsProvenance:
    return R3FactorDiagnosticsProvenance(
        factor_id="momentum_1m",
        factor_version=1,
        evaluation_period=period,
        dataset_id="factor_evaluation",
        catalog_snapshot_id="snapshot-r3",
        universe="a-share-r3",
        cost_bps=20.0,
    )


def test_r3_projection_carries_immutable_provenance_and_fixed_schema() -> None:
    source = {
        "coverage": 0.95,
        "market_regime_performance": {"bull": 0.12},
        "liquidity": {"high": 0.04},
        "industry_exposure": {"bank": 0.10},
        "size_exposure": {"large": -0.05},
        "style_exposure": {"value": 0.08},
    }
    provenance = _diagnostic_provenance()
    projection = project_r3_factor_diagnostics(
        source,
        provenance=provenance,
    )

    assert projection.provenance == provenance
    assert projection.computed_metrics == (
        "coverage",
        "market_regime_performance",
        "liquidity",
        "industry_exposure",
        "size_exposure",
        "style_exposure",
    )
    assert R3_FACTOR_DIAGNOSTIC_METRIC_IDS[-5:] == (
        "market_regime_performance",
        "liquidity",
        "industry_exposure",
        "size_exposure",
        "style_exposure",
    )
    assert projection.content_hash == (
        r3_factor_diagnostics_projection_hash(
            source,
            provenance=provenance,
        )
    )


def test_r3_projection_hash_has_a_public_versioned_contract() -> None:
    source = {"coverage": 0.95}
    provenance = _diagnostic_provenance()

    assert R3_FACTOR_DIAGNOSTICS_SCHEMA_VERSION == 1
    assert r3_factor_diagnostics_projection_hash(source, provenance=provenance) == (
        r3_factor_diagnostics_content_hash(source, provenance=provenance)
    )


def test_r3_projection_hash_binds_factor_provenance() -> None:
    source = {"coverage": 0.95}
    first = _diagnostic_provenance()
    relabeled = replace(first, dataset_id="factor_evaluation_v2")

    assert r3_factor_diagnostics_projection_hash(
        source,
        provenance=first,
    ) != r3_factor_diagnostics_projection_hash(
        source,
        provenance=relabeled,
    )


def test_r3_projection_rejects_content_hash_drift() -> None:
    with pytest.raises(ValueError, match="content hash"):
        R3FactorDiagnosticsProjection(
            provenance=_diagnostic_provenance(),
            content_hash="a" * 64,
            computed_metrics=("coverage",),
            values={"coverage": 0.95},
        )


def test_diagnostic_hash_and_nested_mapping_order_are_canonical() -> None:
    first = {
        "factor_exposure": {
            "style": {"value": 0.2, "growth": -0.1},
            "industry": {"bank": 0.3},
        }
    }
    second = {
        "factor_exposure": {
            "industry": {"bank": 0.3},
            "style": {"growth": -0.1, "value": 0.2},
        }
    }

    first_projection = project_r3_factor_diagnostics(
        first,
        provenance=_diagnostic_provenance(),
    )
    second_projection = project_r3_factor_diagnostics(
        second,
        provenance=_diagnostic_provenance(),
    )

    provenance = _diagnostic_provenance()
    assert r3_factor_diagnostics_projection_hash(first, provenance=provenance) == (
        r3_factor_diagnostics_projection_hash(second, provenance=provenance)
    )
    assert tuple(first_projection.values["exposure"]) == ("industry", "style")
    assert first_projection.values == second_projection.values


@pytest.mark.parametrize("bad_key", ["", " bank", "bank "])
def test_diagnostic_mapping_keys_must_be_canonical(bad_key: str) -> None:
    source = {"industry_exposure": {bad_key: 0.1}}

    with pytest.raises(ValueError, match="canonical string"):
        r3_factor_diagnostics_projection_hash(
            source,
            provenance=_diagnostic_provenance(),
        )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ({"coverage": 1.01}, "coverage.*between zero and one"),
        ({"missingness": -0.01}, "missingness.*between zero and one"),
        ({"avg_turnover": -0.01}, "turnover.*non-negative"),
        ({"cost_drag": -0.01}, "cost_drag.*non-negative"),
    ],
)
def test_r3_projection_validates_metric_domains(
    source: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        project_r3_factor_diagnostics(
            source,
            provenance=_diagnostic_provenance(),
        )


@pytest.mark.parametrize(
    "bad_value",
    [True, False, math.nan, math.inf, -math.inf, "0.5"],
)
def test_diagnostics_reject_invalid_scalar_shapes(bad_value: object) -> None:
    with pytest.raises(ValueError, match=r"coverage.*finite number"):
        project_r3_factor_diagnostics(
            {"coverage": bad_value},
            provenance=_diagnostic_provenance(),
        )


def test_diagnostics_reject_wrong_metric_collection_shapes() -> None:
    with pytest.raises(ValueError, match=r"decay.*pairs"):
        project_r3_factor_diagnostics(
            {"ic_decay": {"day": 0.1}},
            provenance=_diagnostic_provenance(),
        )
    with pytest.raises(ValueError, match=r"quantile_return.*numeric mapping"):
        project_r3_factor_diagnostics(
            {"quantile_annual_returns": [0.1, 0.2]},
            provenance=_diagnostic_provenance(),
        )
    with pytest.raises(ValueError, match=r"factor_contribution.*numeric mapping"):
        project_r3_factor_diagnostics(
            {"factor_contribution": {"value": True}},
            provenance=_diagnostic_provenance(),
        )


def test_diagnostics_projection_is_deeply_immutable_and_defensively_copied() -> None:
    contribution = {"momentum": 0.3}
    exposure = {"industry": {"bank": 0.2}}
    source = {
        "factor_contribution": contribution,
        "factor_exposure": exposure,
    }
    projection = project_r3_factor_diagnostics(
        source,
        provenance=_diagnostic_provenance(),
    )
    contribution["momentum"] = 9.9
    exposure["industry"]["bank"] = 9.9

    assert isinstance(projection.values, MappingProxyType)
    assert projection.values["factor_contribution"]["momentum"] == 0.3
    assert projection.values["exposure"]["industry"]["bank"] == 0.2
    with pytest.raises(TypeError):
        projection.values["new"] = 1.0  # type: ignore[index]
    with pytest.raises(TypeError):
        projection.values["exposure"]["industry"]["bank"] = 1.0  # type: ignore[index]


# ---------------------------------------------------------------------------
# EvaluationConfig
# ---------------------------------------------------------------------------


class TestEvaluationConfig:
    """Tests for EvaluationConfig defaults and immutability."""

    def test_default_values(self) -> None:
        """EvaluationConfig has sensible defaults."""
        config = EvaluationConfig()
        assert config.asset_class == "stock"
        assert config.adj == "none"
        assert config.holding_period == 5
        assert config.n_quantiles == 5
        assert config.ic_lags is None
        assert config.ic_autocorr_max_lag == 10
        assert config.risk_free_rate == 0.0
        assert config.cost_bps == 20.0
        assert config.rebalance_freq == 5
        assert config.periods_per_year == 244
        assert config.run_fama_macbeth is False
        assert config.run_exposure_analysis is False
        assert config.run_regime_ic is False
        assert config.run_performance_attribution is False

    def test_custom_values(self) -> None:
        """EvaluationConfig accepts custom values."""
        config = EvaluationConfig(
            asset_class="etf",
            holding_period=10,
            n_quantiles=10,
            run_fama_macbeth=True,
        )
        assert config.asset_class == "etf"
        assert config.holding_period == 10
        assert config.n_quantiles == 10
        assert config.run_fama_macbeth is True

    def test_frozen(self) -> None:
        """EvaluationConfig is frozen (immutable)."""
        config = EvaluationConfig()
        with pytest.raises(AttributeError):
            config.holding_period = 99  # type: ignore[misc]

    def test_all_flags_off_by_default(self) -> None:
        """All optional analysis flags are off by default."""
        config = EvaluationConfig()
        assert not config.run_fama_macbeth
        assert not config.run_exposure_analysis
        assert not config.run_regime_ic
        assert not config.run_performance_attribution


# ---------------------------------------------------------------------------
# compute_optional_analysis
# ---------------------------------------------------------------------------


class TestComputeOptionalAnalysis:
    """Tests for compute_optional_analysis flag combinations."""

    def _make_factor_df(self, n: int = 100) -> pl.DataFrame:
        """Create a minimal factor DataFrame."""
        rows = []
        for i in range(n):
            rows.append(
                {
                    "trade_date": date(2024, 1, 1) + timedelta(days=i % 20),
                    "instrument_id": i % 10,
                    "value": float(i),
                }
            )
        return pl.DataFrame(rows)

    def _make_return_df(self, n: int = 100) -> pl.DataFrame:
        """Create a minimal return DataFrame."""
        rows = []
        for i in range(n):
            rows.append(
                {
                    "trade_date": date(2024, 1, 1) + timedelta(days=i % 20),
                    "instrument_id": i % 10,
                    "forward_return": float(i) * 0.01,
                }
            )
        return pl.DataFrame(rows)

    def test_all_flags_off(self) -> None:
        """When all flags are off, all optional results should be None."""
        factor_df = self._make_factor_df()
        return_df = self._make_return_df()
        ic_df = pl.DataFrame({"trade_date": [date(2024, 1, 1)], "ic": [0.05]})
        q_ret_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "quantile": [1, 2, 3, 4, 5],
                "mean_return": [0.01, 0.02, 0.03, 0.04, 0.05],
            }
        )
        config = EvaluationConfig()
        result = compute_optional_analysis(
            factor_df=factor_df,
            return_df=return_df,
            rank_ic_df=ic_df,
            q_ret_df=q_ret_df,
            config=config,
            risk_dfs={},
            ppw=244,
        )
        assert isinstance(result, OptionalAnalysisData)
        assert result.fama_macbeth is None
        assert result.factor_exposure is None
        assert result.regime_ic is None
        assert result.performance_attribution is None

    def test_regime_ic_flag_on(self) -> None:
        """When run_regime_ic is True, regime_ic result is computed."""
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(50)]
        ic_df = pl.DataFrame(
            {"trade_date": dates, "ic": [0.05 * (i % 3 + 1) for i in range(50)]}
        )
        q_ret_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "quantile": [1, 2, 3, 4, 5],
                "mean_return": [0.01, 0.02, 0.03, 0.04, 0.05],
            }
        )
        config = EvaluationConfig(run_regime_ic=True)
        result = compute_optional_analysis(
            factor_df=self._make_factor_df(),
            return_df=self._make_return_df(),
            rank_ic_df=ic_df,
            q_ret_df=q_ret_df,
            config=config,
            risk_dfs={},
            ppw=244,
        )
        assert result.regime_ic is not None

    def test_performance_attribution_flag_on(self) -> None:
        """When run_performance_attribution is True, result is computed."""
        ic_df = pl.DataFrame({"trade_date": [date(2024, 1, 1)], "ic": [0.05]})
        q_ret_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "quantile": [1, 2, 3, 4, 5],
                "mean_return": [0.01, 0.02, 0.03, 0.04, 0.05],
            }
        )
        config = EvaluationConfig(run_performance_attribution=True)
        result = compute_optional_analysis(
            factor_df=self._make_factor_df(),
            return_df=self._make_return_df(),
            rank_ic_df=ic_df,
            q_ret_df=q_ret_df,
            config=config,
            risk_dfs={},
            ppw=244,
        )
        assert result.performance_attribution is not None
        assert result.performance_attribution.selection_return > 0

    def test_empty_risk_dfs_skips_fm_and_exposure(self) -> None:
        """When risk_dfs is empty, FM and exposure are not computed."""
        ic_df = pl.DataFrame({"trade_date": [date(2024, 1, 1)], "ic": [0.05]})
        q_ret_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "quantile": [1, 2, 3, 4, 5],
                "mean_return": [0.01, 0.02, 0.03, 0.04, 0.05],
            }
        )
        config = EvaluationConfig(
            run_fama_macbeth=True,
            run_exposure_analysis=True,
        )
        result = compute_optional_analysis(
            factor_df=self._make_factor_df(),
            return_df=self._make_return_df(),
            rank_ic_df=ic_df,
            q_ret_df=q_ret_df,
            config=config,
            risk_dfs={},
            ppw=244,
        )
        assert result.fama_macbeth is None
        assert result.factor_exposure is None


# ---------------------------------------------------------------------------
# assemble_report
# ---------------------------------------------------------------------------


class TestAssembleReport:
    """Tests for assemble_report."""

    def _make_ic_data(self) -> ICMetricsData:
        """Create minimal ICMetricsData."""
        ic_summary = ICSummary(
            mean=0.05, std=0.10, icir=0.5, t_stat=2.0, p_value=0.05, win_rate=0.6
        )
        return ICMetricsData(
            rank_ic_df=pl.DataFrame({"trade_date": [date(2024, 1, 1)], "ic": [0.05]}),
            rank_ic_summary=ic_summary,
            pearson_ic_summary=ic_summary,
            ic_decay=[(1, 0.05), (5, 0.02)],
            ic_half_life=10.0,
            ic_autocorrelation=[(1, 0.3)],
            turnover_adjusted_ir=0.15,
            grinold_kahn_ir=0.20,
            sub_period_ic={"2024": ic_summary},
        )

    def _make_q_data(self) -> QuantileMetricsData:
        """Create minimal QuantileMetricsData."""
        tail = TailRiskMetrics(
            cvar_95=-0.02,
            cvar_99=-0.05,
            skewness=-0.1,
            kurtosis=0.5,
            max_single_day_loss=-0.03,
        )
        ls = LongShortResult(
            annual_return=0.10,
            annual_volatility=0.15,
            sharpe=0.67,
            portfolio_ir=0.67,
            sortino=1.0,
            max_drawdown=-0.08,
            calmar=1.25,
            tail_risk=tail,
        )
        return QuantileMetricsData(
            q_ret_df=pl.DataFrame(
                {
                    "trade_date": [date(2024, 1, 1)] * 5,
                    "quantile": [1, 2, 3, 4, 5],
                    "mean_return": [0.01, 0.02, 0.03, 0.04, 0.05],
                }
            ),
            long_short=ls,
            quantile_annual_returns={1: 0.01, 5: 0.05},
            avg_turnover=0.3,
            net_return_after_cost=0.08,
        )

    def _make_opt_data(self) -> OptionalAnalysisData:
        """Create minimal OptionalAnalysisData."""
        return OptionalAnalysisData(
            fama_macbeth=None,
            factor_exposure=None,
            regime_ic=None,
            performance_attribution=None,
        )

    def test_basic_assembly(self) -> None:
        """assemble_report correctly assembles a FactorEvaluationReport."""
        config = EvaluationConfig()
        ic_data = self._make_ic_data()
        q_data = self._make_q_data()
        opt_data = self._make_opt_data()

        report = assemble_report(
            config=config,
            period=("2024-01-01", "2024-12-31"),
            n_dates=244,
            n_observations=10000,
            ic_data=ic_data,
            q_data=q_data,
            opt_data=opt_data,
        )
        assert isinstance(report, FactorEvaluationReport)
        assert report.evaluation_period == ("2024-01-01", "2024-12-31")
        assert report.holding_period == 5
        assert report.n_quantiles == 5
        assert report.n_observations == 10000
        assert report.n_dates == 244
        assert report.rank_ic_summary.mean == 0.05
        assert report.ic_half_life == 10.0
        assert report.avg_turnover == 0.3
        assert report.net_return_after_cost == 0.08
        assert report.computed_at is not None

    def test_config_values_propagated(self) -> None:
        """Custom config values propagate into the report."""
        config = EvaluationConfig(holding_period=10, n_quantiles=3)
        ic_data = self._make_ic_data()
        q_data = self._make_q_data()
        opt_data = self._make_opt_data()

        report = assemble_report(
            config=config,
            period=("2024-01-01", "2024-06-30"),
            n_dates=120,
            n_observations=5000,
            ic_data=ic_data,
            q_data=q_data,
            opt_data=opt_data,
        )
        assert report.holding_period == 10
        assert report.n_quantiles == 3

    def test_ic_decay_propagated(self) -> None:
        """IC decay results are correctly propagated."""
        config = EvaluationConfig()
        ic_data = self._make_ic_data()
        q_data = self._make_q_data()
        opt_data = self._make_opt_data()

        report = assemble_report(
            config=config,
            period=("2024-01-01", "2024-12-31"),
            n_dates=244,
            n_observations=10000,
            ic_data=ic_data,
            q_data=q_data,
            opt_data=opt_data,
        )
        assert report.ic_decay == [(1, 0.05), (5, 0.02)]
        assert report.sub_period_ic == {"2024": ic_data.rank_ic_summary}


# ---------------------------------------------------------------------------
# resolve_period
# ---------------------------------------------------------------------------


class TestResolvePeriod:
    """Tests for resolve_period helper."""

    def test_uses_data_range_when_no_bounds(self) -> None:
        """Without explicit bounds, uses data min/max."""
        df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 3, 1),
                    date(2024, 1, 15),
                    date(2024, 6, 10),
                ],
                "value": [1.0, 2.0, 3.0],
            }
        )
        start, end = resolve_period(df, None, None)
        assert start == "2024-01-15"
        assert end == "2024-06-10"

    def test_explicit_bounds_override_data_range(self) -> None:
        """Explicit start/end override data min/max."""
        df = pl.DataFrame(
            {"trade_date": [date(2024, 1, 1), date(2024, 12, 31)], "value": [1.0, 2.0]}
        )
        start, end = resolve_period(df, "2024-03-01", "2024-09-30")
        assert start == "2024-03-01"
        assert end == "2024-09-30"

    def test_no_trade_date_column(self) -> None:
        """Without trade_date column, uses provided bounds or defaults."""
        df = pl.DataFrame({"value": [1.0]})
        start, end = resolve_period(df, None, None)
        assert start == "1970-01-01"
        assert end == "2099-12-31"

    def test_partial_bounds(self) -> None:
        """Only start provided: end uses data max."""
        df = pl.DataFrame(
            {"trade_date": [date(2024, 1, 1), date(2024, 6, 30)], "value": [1.0, 2.0]}
        )
        start, end = resolve_period(df, "2024-03-01", None)
        assert start == "2024-03-01"
        assert end == "2024-06-30"


# ---------------------------------------------------------------------------
# prepare_data
# ---------------------------------------------------------------------------


class TestPrepareData:
    """Tests for prepare_data helper."""

    def test_drops_nulls(self) -> None:
        """Null values in value/forward_return columns are dropped."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 3,
                "instrument_id": [1, 2, 3],
                "value": [1.0, None, 3.0],
            }
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 3,
                "instrument_id": [1, 2, 3],
                "forward_return": [0.01, 0.02, 0.03],
            }
        )
        f_clean, r_clean = prepare_data(factor_df, return_df)
        assert f_clean.height == 2
        assert r_clean.height == 3

    def test_date_filtering(self) -> None:
        """Data is filtered to the specified date range."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 3, 1),
                    date(2024, 6, 1),
                ],
                "instrument_id": [1, 1, 1],
                "value": [1.0, 2.0, 3.0],
            }
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 3, 1),
                    date(2024, 6, 1),
                ],
                "instrument_id": [1, 1, 1],
                "forward_return": [0.01, 0.02, 0.03],
            }
        )
        f_clean, r_clean = prepare_data(
            factor_df,
            return_df,
            start="2024-02-01",
            end="2024-05-01",
        )
        assert f_clean.height == 1
        assert r_clean.height == 1


# ---------------------------------------------------------------------------
# compute_quantile_annual_returns
# ---------------------------------------------------------------------------


class TestComputeQuantileAnnualReturns:
    """Tests for compute_quantile_annual_returns helper."""

    def test_empty_df_returns_empty_dict(self) -> None:
        """Empty DataFrame returns empty dict."""
        df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "quantile": pl.Int64,
                "mean_return": pl.Float64,
            }
        )
        result = compute_quantile_annual_returns(df)
        assert result == {}

    def test_computes_annual_returns(self) -> None:
        """Annual returns are mean * periods_per_year."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 3,
                "quantile": [1, 2, 3],
                "mean_return": [0.001, 0.002, 0.003],
            }
        )
        result = compute_quantile_annual_returns(df, periods_per_year=244)
        assert 1 in result
        assert result[1] == pytest.approx(0.001 * 244, abs=1e-6)
        assert result[2] == pytest.approx(0.002 * 244, abs=1e-6)

    def test_skips_null_means(self) -> None:
        """Quantiles with null mean_return are skipped."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 2,
                "quantile": [1, 2],
                "mean_return": [0.001, None],
            }
        )
        result = compute_quantile_annual_returns(df, periods_per_year=244)
        assert 1 in result
        assert 2 not in result


# ---------------------------------------------------------------------------
# estimate_avg_turnover
# ---------------------------------------------------------------------------


class TestEstimateAvgTurnover:
    """Tests for estimate_avg_turnover helper."""

    def test_empty_df_returns_zero(self) -> None:
        """Empty DataFrame returns 0.0."""
        df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "quantile": pl.Int64,
                "mean_return": pl.Float64,
            }
        )
        assert estimate_avg_turnover(df) == 0.0

    def test_single_date_returns_zero(self) -> None:
        """Single date (< min dates for turnover) returns 0.0."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 3,
                "quantile": [1, 2, 3],
                "mean_return": [0.01, 0.02, 0.03],
            }
        )
        assert estimate_avg_turnover(df) == 0.0

    def test_multiple_dates_returns_non_negative(self) -> None:
        """Multiple dates produce a non-negative turnover estimate."""
        df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 3),
                ],
                "quantile": [1, 2, 1, 2, 1, 2],
                "mean_return": [0.01, 0.02, 0.03, -0.01, 0.02, 0.04],
            }
        )
        result = estimate_avg_turnover(df)
        assert result >= 0.0


# ---------------------------------------------------------------------------
# empty_report
# ---------------------------------------------------------------------------


class TestEmptyReport:
    """Tests for empty_report helper."""

    def test_empty_report_structure(self) -> None:
        """empty_report produces a valid FactorEvaluationReport with zeros."""
        report = empty_report(
            factor_id="test_factor",
            factor_version=2,
            period=("2024-01-01", "2024-12-31"),
            holding_period=5,
            n_quantiles=5,
        )
        assert isinstance(report, FactorEvaluationReport)
        assert report.factor_id == "test_factor"
        assert report.factor_version == 2
        assert report.evaluation_period == ("2024-01-01", "2024-12-31")
        assert report.holding_period == 5
        assert report.n_quantiles == 5
        assert report.n_observations == 0
        assert report.n_dates == 0
        assert report.rank_ic_summary.mean == 0.0
        assert report.ic_decay == []
        assert report.quantile_annual_returns == {}
        assert report.long_short.annual_return == 0.0
        assert report.computed_at is not None

    def test_empty_report_ic_summaries_zero(self) -> None:
        """IC summaries in empty report are all zeros with p_value=1."""
        report = empty_report(
            factor_id="f",
            factor_version=1,
            period=("2024-01-01", "2024-01-31"),
            holding_period=1,
            n_quantiles=5,
        )
        assert report.rank_ic_summary.p_value == 1.0
        assert report.pearson_ic_summary.p_value == 1.0
        assert report.rank_ic_summary.icir == 0.0
