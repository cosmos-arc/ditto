"""请求模型拒绝裸 Infinity/NaN（#685 审计批C，finding #18）.

Starlette 用 Python ``json.loads`` 收裸 ``Infinity`` 后以 float('inf') 传入
pydantic 绑定；三组请求模型补 ``allow_inf_nan=False`` 后在绑定层 422。
"""

from __future__ import annotations

import math

import pytest
from ditto_apps.models.backtest import CostConfigRequest, CreateBacktestRunRequest
from ditto_apps.models.paper import (
    CreatePaperAccountBody,
    PaperInstrumentRulesBody,
    PaperMarketSnapshotBody,
)
from ditto_apps.models.portfolio_comparison import PortfolioScenarioBody
from pydantic import ValidationError

_BACKTEST_RUN_BODY: dict[str, object] = {
    "strategy_id": "strategy-1",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
}

_PAPER_ACCOUNT_BODY: dict[str, object] = {
    "account_id": "paper-1",
    "name": "paper",
    "opened_at": "2024-01-01T00:00:00",
    "trade_date": "2024-01-01",
    "initial_cash": 1_000_000,
    "idempotency_key": "idem-1",
}

_MARKET_SNAPSHOT_BODY: dict[str, object] = {
    "dataset_id": "stock_daily",
    "source": "tushare",
    "source_snapshot_id": "snap-1",
    "observed_at": "2024-01-15T09:30:00",
    "publication_cutoff": "2024-01-15T09:30:00",
    "open": 10.0,
    "high": 11.0,
    "low": 9.5,
    "close": 10.5,
    "prev_close": 10.0,
    "volume": 1_000_000.0,
    "amount": 10_500_000.0,
}

_RULES_BODY: dict[str, object] = {
    "asset_class": "stock",
    "exchange": "XSHE",
    "tick_size": 0.01,
    "lot_size": 100,
    "board_segment": "main",
    "settlement_cycle": 1,
    "commission_rate": 0.0003,
    "min_commission": 5.0,
    "stamp_duty_rate": 0.001,
    "transfer_fee_rate": 0.00001,
}

_SCENARIO_BODY: dict[str, object] = {
    "strategy_id": "strategy-1",
    "model_portfolio_id": "mp-1",
    "paper_account_id": "paper-1",
    "manual_account_id": "manual-1",
    "paper_session_id": "session-1",
    "as_of": "2024-01-15",
    "knowledge_cutoff": "2024-01-15T15:00:00",
    "publication_cutoff": "2024-01-15T15:00:00",
    "source_snapshot_ids": ["snap-1"],
    "baseline_kind": "model",
}


@pytest.mark.unit
class TestBacktestRequestInfNan:
    """backtest 请求模型拒绝 inf/nan."""

    def test_initial_cash_infinity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateBacktestRunRequest.model_validate(
                {**_BACKTEST_RUN_BODY, "initial_cash": math.inf}
            )

    def test_initial_cash_nan_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateBacktestRunRequest.model_validate(
                {**_BACKTEST_RUN_BODY, "initial_cash": math.nan}
            )

    def test_cost_config_infinity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CostConfigRequest.model_validate({"commission_rate": math.inf})

    def test_finite_values_still_accepted(self) -> None:
        body = CreateBacktestRunRequest.model_validate(
            {**_BACKTEST_RUN_BODY, "initial_cash": 500_000.0}
        )
        assert body.initial_cash == 500_000.0


@pytest.mark.unit
class TestPaperRequestInfNan:
    """paper 请求模型（共享 _REQUEST_CONFIG）拒绝 inf/nan."""

    def test_initial_cash_infinity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreatePaperAccountBody.model_validate(
                {**_PAPER_ACCOUNT_BODY, "initial_cash": math.inf}
            )

    def test_market_snapshot_price_infinity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaperMarketSnapshotBody.model_validate(
                {**_MARKET_SNAPSHOT_BODY, "open": math.inf}
            )

    def test_rules_tick_size_infinity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaperInstrumentRulesBody.model_validate(
                {**_RULES_BODY, "tick_size": math.inf}
            )


@pytest.mark.unit
class TestPortfolioScenarioInfNan:
    """portfolio comparison 请求模型拒绝 inf/nan."""

    def test_market_shock_infinity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PortfolioScenarioBody.model_validate(
                {**_SCENARIO_BODY, "market_shock": math.inf}
            )

    def test_industry_shock_value_nan_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PortfolioScenarioBody.model_validate(
                {**_SCENARIO_BODY, "industry_shocks": {"801010": math.nan}}
            )
