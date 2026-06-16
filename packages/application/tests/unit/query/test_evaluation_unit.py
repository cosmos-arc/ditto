"""Unit tests for FactorEvaluationFacade version 解析与可选分析开关.

覆盖 Task A 范围:
- A1 version=None → resolve_offline_version 被调用，read_frame 用解析 version
- A2 version 显式 → 跳过 resolve_offline_version
- A3 resolve 抛 DerivedError → 包装 AppQueryError（保留 factor_id 与 __cause__）
- A4 run_regime_ic 透传到 EvaluationConfig
- A5 run_regime_ic=True → report.regime_ic 非空（透传修复）
- A6 run_performance_attribution=True → report.performance_attribution 非空
- A7 report.factor_id / factor_version 被覆写为传入值与解析 version
- A8 默认 options → 不触发可选分析，report 可选字段为 None

验证策略:
- version 解析与可选开关透传通过 monkeypatch 替换 FactorEvaluator，
  捕获 config 参数（避免依赖合成数据触发真实计算，可靠性更高）。
- report 重建透传通过注入构造好的 inner report（含可选分析结果），
  验证最终 report 保留这两个字段（修复当前丢弃 bug）。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evaluation import (
    EvaluationOptions,
    FactorEvaluationFacade,
)
from ditto_features.errors import DerivedNotFoundError
from ditto_features.evaluation.evaluator import EvaluationConfig
from ditto_features.evaluation.report import (
    FactorEvaluationReport,
    ICSummary,
    LongShortResult,
    PerformanceAttributionResult,
    RegimeICResult,
    TailRiskMetrics,
)


def _make_factor_df() -> pl.DataFrame:
    """构造最小 factor DataFrame（trade_date/instrument_id/value）。"""
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 1, 2],
            "trade_date": dates * 2,
            "value": [0.5, -0.3, 0.6, -0.2],
        },
    )


def _make_inner_report(
    *,
    regime_ic: RegimeICResult | None = None,
    performance_attribution: PerformanceAttributionResult | None = None,
) -> FactorEvaluationReport:
    """构造带默认值的内部 report，允许覆写可选分析字段。"""
    return FactorEvaluationReport(
        factor_id="unknown",
        factor_version=1,
        evaluation_period=("2024-01-02", "2024-01-03"),
        holding_period=5,
        n_quantiles=5,
        rank_ic_summary=ICSummary(
            mean=0.05, std=0.1, icir=0.5, t_stat=2.0, p_value=0.04, win_rate=0.55
        ),
        pearson_ic_summary=ICSummary(
            mean=0.04, std=0.1, icir=0.4, t_stat=1.8, p_value=0.07, win_rate=0.53
        ),
        ic_decay=[(1, 0.05)],
        ic_half_life=10.0,
        ic_autocorrelation=[(1, 0.6)],
        quantile_annual_returns={1: 0.02, 5: 0.10},
        long_short=LongShortResult(
            annual_return=0.08,
            annual_volatility=0.12,
            sharpe=0.67,
            portfolio_ir=0.67,
            sortino=0.90,
            max_drawdown=0.05,
            calmar=1.60,
            tail_risk=TailRiskMetrics(
                cvar_95=0.03,
                cvar_99=0.05,
                skewness=-0.2,
                kurtosis=3.1,
                max_single_day_loss=-0.04,
            ),
        ),
        avg_turnover=0.3,
        net_return_after_cost=0.07,
        turnover_adjusted_ir=0.5,
        grinold_kahn_ir=0.6,
        sub_period_ic={},
        n_observations=100,
        n_dates=2,
        computed_at="2024-07-01T00:00:00Z",
        regime_ic=regime_ic,
        performance_attribution=performance_attribution,
    )


def _make_regime_ic() -> RegimeICResult:
    """构造非空 regime IC 结果。"""
    return RegimeICResult(
        regimes={},
        regime_labels=[],
        transition_matrix={},
        ic_trend=0.01,
        ic_trend_p_value=0.5,
    )


def _make_performance_attribution() -> PerformanceAttributionResult:
    """构造非空绩效归因结果。"""
    return PerformanceAttributionResult(
        total_return=0.1,
        selection_return=0.05,
        timing_return=0.05,
        interaction_return=0.0,
        annual_alpha=0.05,
        tracking_error=0.02,
        information_ratio=2.5,
        win_rate_by_quantile={1: 0.4, 5: 0.6},
    )


class _SpyEvaluator:
    """捕获 evaluate 的 config 参数，返回预设 inner report。

    替换 FactorEvaluator 类，记录最后一次 evaluate 调用的 config，
    用于断言可选分析开关透传。
    """

    def __init__(
        self,
        *,
        forward_return_provider: object,
        inner_report: FactorEvaluationReport | None = None,
    ) -> None:
        # 与 FactorEvaluator 构造签名兼容（forward_return_provider 必填）
        self.forward_return_provider = forward_return_provider
        self._inner_report = inner_report or _make_inner_report()
        self.last_config: EvaluationConfig | None = None

    def evaluate(
        self,
        factor_df: pl.DataFrame,
        config: EvaluationConfig | None = None,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> FactorEvaluationReport:
        del factor_df, start, end  # spy: 仅捕获 config 参数
        self.last_config = config
        return self._inner_report


def _patch_evaluator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    inner_report: FactorEvaluationReport | None = None,
) -> dict[str, _SpyEvaluator | None]:
    """替换 evaluation 模块的 FactorEvaluator 为 _CapturingEvaluator。

    返回 holder dict，测试通过 ``holder["instance"]`` 访问最后一次
    ``FactorEvaluationFacade.evaluate`` 内部构造的 spy 实例（从而读取
    其捕获的 ``last_config``）。
    """
    holder: dict[str, _SpyEvaluator | None] = {"instance": None}

    class _CapturingEvaluator(_SpyEvaluator):
        def __init__(
            self,
            *,
            forward_return_provider: object,
        ) -> None:
            super().__init__(
                forward_return_provider=forward_return_provider,
                inner_report=inner_report,
            )
            holder["instance"] = self

    import ditto_application.queries.evaluation as eval_module

    monkeypatch.setattr(eval_module, "FactorEvaluator", _CapturingEvaluator)

    return holder


# ---------------------------------------------------------------------------
# A1: version=None → resolve_offline_version 被调用，read_frame 用解析后的 version
# ---------------------------------------------------------------------------


class TestVersionResolution:
    """version 解析：None 走 resolve_offline_version，显式值跳过。"""

    def test_evaluate_version_none_calls_resolve_offline_version(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A1: version=None → resolve 被调，read_frame 用解析 version。"""
        _patch_evaluator(monkeypatch)
        artifact_reader = MagicMock()
        artifact_reader.read_frame.return_value = _make_factor_df()
        artifact_reader.resolve_offline_version.return_value = 3

        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=MagicMock(),
        )
        facade.evaluate("fx.momentum", version=None)

        artifact_reader.resolve_offline_version.assert_called_once_with("fx.momentum")
        # read_frame 必须用解析后的 version=3
        artifact_reader.read_frame.assert_called_once_with(
            derived_id="fx.momentum",
            version=3,
            start=None,
            end=None,
        )

    def test_evaluate_explicit_version_skips_resolve(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A2: version=2 → resolve_offline_version 未被调用，read_frame version=2。"""
        _patch_evaluator(monkeypatch)
        artifact_reader = MagicMock()
        artifact_reader.read_frame.return_value = _make_factor_df()

        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=MagicMock(),
        )
        facade.evaluate("fx.momentum", version=2)

        artifact_reader.resolve_offline_version.assert_not_called()
        artifact_reader.read_frame.assert_called_once_with(
            derived_id="fx.momentum",
            version=2,
            start=None,
            end=None,
        )

    def test_evaluate_resolve_failure_wrapped_as_appqueryerror(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A3: resolve 抛 DerivedError → AppQueryError，保留 factor_id 与 __cause__。"""
        _patch_evaluator(monkeypatch)
        factor_id = "fx.missing"
        artifact_reader = MagicMock()
        artifact_reader.read_frame.return_value = _make_factor_df()
        artifact_reader.resolve_offline_version.side_effect = DerivedNotFoundError(
            derived_id=factor_id,
        )

        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=MagicMock(),
        )

        with pytest.raises(AppQueryError, match=factor_id) as exc_info:
            facade.evaluate(factor_id, version=None)

        # details 必须保留 factor_id 上下文
        assert exc_info.value.details.get("factor_id") == factor_id
        # __cause__ 链必须保留原始 DerivedNotFoundError
        assert isinstance(exc_info.value.__cause__, DerivedNotFoundError)


# ---------------------------------------------------------------------------
# A4: run_regime_ic 透传到 EvaluationConfig
# A8: 默认 options 不触发可选分析
# ---------------------------------------------------------------------------


class TestOptionalAnalysisPropagation:
    """可选分析开关透传到 EvaluationConfig。"""

    def test_options_run_regime_ic_propagated_to_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A4: options.run_regime_ic=True → config.run_regime_ic 为 True。"""
        holder = _patch_evaluator(monkeypatch)
        artifact_reader = MagicMock()
        artifact_reader.read_frame.return_value = _make_factor_df()

        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=MagicMock(),
        )
        facade.evaluate(
            "fx.test",
            version=1,
            options=EvaluationOptions(run_regime_ic=True),
        )

        spy = holder["instance"]
        assert spy is not None
        assert spy.last_config is not None
        assert spy.last_config.run_regime_ic is True

    def test_default_options_run_no_optional_analysis(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A8: 默认 options → config 两个可选分析开关均为 False。"""
        holder = _patch_evaluator(monkeypatch)
        artifact_reader = MagicMock()
        artifact_reader.read_frame.return_value = _make_factor_df()

        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=MagicMock(),
        )
        facade.evaluate("fx.test", version=1)  # 默认 options

        spy = holder["instance"]
        assert spy is not None
        assert spy.last_config is not None
        assert spy.last_config.run_regime_ic is False
        assert spy.last_config.run_performance_attribution is False


# ---------------------------------------------------------------------------
# A5/A6: report 重建透传 regime_ic / performance_attribution（修复丢弃 bug）
# ---------------------------------------------------------------------------


class TestReportRebuild:
    """report 重建必须保留可选分析结果（当前丢弃 bug 的修复验证）。"""

    def test_report_preserves_regime_ic_when_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A5: inner report 含 regime_ic → 最终 report.regime_ic is not None。"""
        regime_ic = _make_regime_ic()
        _patch_evaluator(
            monkeypatch,
            inner_report=_make_inner_report(regime_ic=regime_ic),
        )
        artifact_reader = MagicMock()
        artifact_reader.read_frame.return_value = _make_factor_df()

        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=MagicMock(),
        )
        report = facade.evaluate("fx.test", version=1)

        assert report.regime_ic is not None
        assert report.regime_ic is regime_ic

    def test_report_preserves_performance_attribution_when_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A6: inner report 含 performance_attribution → 最终 report 保留该字段。"""
        pa = _make_performance_attribution()
        _patch_evaluator(
            monkeypatch,
            inner_report=_make_inner_report(performance_attribution=pa),
        )
        artifact_reader = MagicMock()
        artifact_reader.read_frame.return_value = _make_factor_df()

        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=MagicMock(),
        )
        report = facade.evaluate("fx.test", version=1)

        assert report.performance_attribution is not None
        assert report.performance_attribution is pa


# ---------------------------------------------------------------------------
# A7: factor_id / factor_version 覆写（含 version=None → resolved version）
# A8 补充: 默认 options → report.regime_ic/performance_attribution 为 None
# ---------------------------------------------------------------------------


class TestReportStamping:
    """report 身份字段覆写与默认可选分析为 None。"""

    def test_evaluate_stamps_factor_id_and_version(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A7: report.factor_id == 传入值，factor_version == resolved version。"""
        _patch_evaluator(monkeypatch)
        artifact_reader = MagicMock()
        artifact_reader.read_frame.return_value = _make_factor_df()
        artifact_reader.resolve_offline_version.return_value = 7

        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=MagicMock(),
        )
        report = facade.evaluate("fx.momentum", version=None)

        assert report.factor_id == "fx.momentum"
        assert report.factor_version == 7

    def test_default_options_report_optional_analysis_is_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A8: 默认 options → report.regime_ic 与 performance_attribution 均为 None。

        inner report 默认无可选分析结果，最终 report 必须也是 None
        （确保重建逻辑不会凭空填充或错误覆盖）。
        """
        _patch_evaluator(monkeypatch)  # inner report 默认 regime_ic/pa 为 None
        artifact_reader = MagicMock()
        artifact_reader.read_frame.return_value = _make_factor_df()

        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=MagicMock(),
        )
        report = facade.evaluate("fx.test", version=1)

        assert report.regime_ic is None
        assert report.performance_attribution is None
