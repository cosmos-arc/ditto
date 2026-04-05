"""Tests for FactorEvaluationFacade -- 封装 DerivedArtifactReader + FactorEvaluator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
from ditto_analytics.evaluation.report import (
    FactorEvaluationReport,
    ICSummary,
    LongShortResult,
    TailRiskMetrics,
)
from ditto_app.query.evaluation import EvaluationOptions, FactorEvaluationFacade


def _make_report(**overrides: object) -> FactorEvaluationReport:
    """构造一个带默认值的 FactorEvaluationReport，支持按需覆写字段."""
    defaults: dict[str, object] = {
        "factor_id": "unknown",
        "factor_version": 0,
        "evaluation_period": ("2024-01-01", "2024-06-30"),
        "holding_period": 5,
        "n_quantiles": 5,
        "rank_ic_summary": ICSummary(
            mean=0.05, std=0.1, icir=0.5, t_stat=2.0, p_value=0.04, win_rate=0.55
        ),
        "pearson_ic_summary": ICSummary(
            mean=0.04, std=0.1, icir=0.4, t_stat=1.8, p_value=0.07, win_rate=0.53
        ),
        "ic_decay": [(1, 0.05), (2, 0.03)],
        "ic_half_life": 10.0,
        "ic_autocorrelation": [(1, 0.6)],
        "quantile_annual_returns": {1: 0.02, 2: 0.04, 3: 0.06, 4: 0.08, 5: 0.10},
        "long_short": LongShortResult(
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
        "avg_turnover": 0.3,
        "net_return_after_cost": 0.07,
        "turnover_adjusted_ir": 0.5,
        "grinold_kahn_ir": 0.6,
        "sub_period_ic": {},
        "n_observations": 1000,
        "n_dates": 120,
        "computed_at": "2024-07-01T00:00:00Z",
    }
    defaults.update(overrides)
    return FactorEvaluationReport(**defaults)  # type: ignore[arg-type]


class TestFactorEvaluationFacadeEvaluate:
    """FactorEvaluationFacade.evaluate -- 委托到 artifact_reader + FactorEvaluator."""

    @patch("ditto_app.query.evaluation.FactorEvaluator")
    def test_delegates_and_stamps_identity(self, mock_evaluator_cls: MagicMock) -> None:
        """验证 read_frame + FactorEvaluator.evaluate 被调用,
        且 report 的 factor_id/factor_version 被覆写.
        """
        factor_df = pl.DataFrame(
            {"instrument_id": [1], "trade_date": ["2024-01-01"], "value": [0.5]}
        )
        artifact_reader = MagicMock(spec=["read_frame"])
        artifact_reader.read_frame.return_value = factor_df

        inner_report = _make_report()
        mock_evaluator_instance = MagicMock(spec=["evaluate"])
        mock_evaluator_instance.evaluate.return_value = inner_report
        mock_evaluator_cls.return_value = mock_evaluator_instance

        forward_return_service = MagicMock(spec=["get_forward_returns"])
        facade = FactorEvaluationFacade(
            artifact_reader=artifact_reader,
            forward_return_service=forward_return_service,
        )

        options = EvaluationOptions(
            start="2024-01-01", end="2024-06-30", holding_period=10, n_quantiles=3
        )
        result = facade.evaluate("my_factor", version=7, options=options)

        # 验证 artifact_reader 被正确调用
        artifact_reader.read_frame.assert_called_once_with(
            derived_id="my_factor",
            version=7,
            start="2024-01-01",
            end="2024-06-30",
        )

        # 验证 FactorEvaluator 被实例化时注入了 forward_return_provider
        mock_evaluator_cls.assert_called_once_with(
            forward_return_provider=forward_return_service
        )

        # 验证 evaluator.evaluate 被调用（factor_df + config + start/end）
        mock_evaluator_instance.evaluate.assert_called_once()
        call_args = mock_evaluator_instance.evaluate.call_args
        assert call_args.args[0] is factor_df
        config = call_args.kwargs["config"]
        assert config.holding_period == 10
        assert config.n_quantiles == 3

        # 验证返回 report 的 factor_id 和 factor_version 被覆写
        assert result.factor_id == "my_factor"
        assert result.factor_version == 7

        # 验证其余字段从内部 report 透传
        assert result.holding_period == inner_report.holding_period
        assert result.rank_ic_summary == inner_report.rank_ic_summary
        assert result.n_observations == inner_report.n_observations
