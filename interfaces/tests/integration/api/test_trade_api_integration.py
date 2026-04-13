"""Trade API 集成测试 — FastAPI TestClient + mock 依赖.

覆盖所有 9 个 trade 端点的路由注册 + DI 注入正确性:

正面场景 (11 tests):
  - ListIntents, UpdateIntentStatus, RecordFill, ListFills
  - ListPositions, ComputePnl, LatestSignals, SignalIntentsByDate
  - Comparison (含 not_found)

负面场景 (Phase 4.8):
  - TestMissingRequiredParams: 8 个端点缺少必需参数 → 422
  - TestInvalidRequestBody: 6 个无效请求体 → 422
  - TestBusinessRuleErrors: 5 个业务规则违反 → 500
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_app.command.trade import (
    RecordFillHandler,
    UpdateIntentStatusHandler,
)
from ditto_app.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
    TradeIntent,
)
from ditto_app.query.comparison import ComparisonQueryFacade
from ditto_app.query.portfolio_actual import PnlSummary, PortfolioActualQueryFacade
from ditto_app.query.signal import SignalQueryFacade
from ditto_app.query.trade import TradeQueryFacade
from ditto_interfaces.api.routes.trade import router
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_trade_facade() -> MagicMock:
    return MagicMock(spec=TradeQueryFacade)


@pytest.fixture
def mock_portfolio_facade() -> MagicMock:
    return MagicMock(spec=PortfolioActualQueryFacade)


@pytest.fixture
def mock_signal_facade() -> MagicMock:
    return MagicMock(spec=SignalQueryFacade)


@pytest.fixture
def mock_comparison_facade() -> MagicMock:
    return MagicMock(spec=ComparisonQueryFacade)


@pytest.fixture
def mock_fill_handler() -> MagicMock:
    return MagicMock(spec=RecordFillHandler)


@pytest.fixture
def mock_status_handler() -> MagicMock:
    return MagicMock(spec=UpdateIntentStatusHandler)


@pytest.fixture
def app(
    mock_trade_facade: MagicMock,
    mock_portfolio_facade: MagicMock,
    mock_signal_facade: MagicMock,
    mock_comparison_facade: MagicMock,
    mock_fill_handler: MagicMock,
    mock_status_handler: MagicMock,
) -> FastAPI:
    app = FastAPI()

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def trade_facade(self) -> TradeQueryFacade:
            return mock_trade_facade

        @provide
        def portfolio_facade(self) -> PortfolioActualQueryFacade:
            return mock_portfolio_facade

        @provide
        def signal_facade(self) -> SignalQueryFacade:
            return mock_signal_facade

        @provide
        def comparison_facade(self) -> ComparisonQueryFacade:
            return mock_comparison_facade

        @provide
        def fill_handler(self) -> RecordFillHandler:
            return mock_fill_handler

        @provide
        def status_handler(self) -> UpdateIntentStatusHandler:
            return mock_status_handler

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def general_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Type aliases for shorter test signatures
# ---------------------------------------------------------------------------

MC = MagicMock
TC = TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intent(**overrides: object) -> TradeIntent:
    defaults: dict[str, object] = {
        "intent_id": "int-001",
        "strategy_id": "strat-a",
        "signal_date": "2024-01-15",
        "instrument_id": 510300,
        "direction": "buy",
        "target_weight": 0.3,
        "current_weight": 0.1,
        "delta_weight": 0.2,
        "quantity": 1000,
        "status": "pending",
    }
    defaults.update(overrides)
    return TradeIntent(**defaults)  # type: ignore[arg-type]


def _make_fill(**overrides: object) -> ManualExecutionFill:
    defaults: dict[str, object] = {
        "fill_id": "fill-001",
        "intent_id": "int-001",
        "strategy_id": "strat-a",
        "trade_date": "2024-01-16",
        "instrument_id": 510300,
        "direction": "buy",
        "quantity": 1000,
        "fill_price": 4.12,
        "fee": 5.0,
        "slippage": 0.0,
        "notes": "",
        "settlement_date": "2024-01-17",
    }
    defaults.update(overrides)
    return ManualExecutionFill(**defaults)  # type: ignore[arg-type]


def _make_position(**overrides: object) -> ActualPositionSnapshot:
    defaults: dict[str, object] = {
        "snapshot_id": "snap-001",
        "strategy_id": "strat-a",
        "snapshot_date": "2024-01-16",
        "instrument_id": 510300,
        "quantity": 1000,
        "available_quantity": 0,
        "average_cost": 4.12,
        "market_value": 4120.0,
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
        "total_fees": 5.0,
    }
    defaults.update(overrides)
    return ActualPositionSnapshot(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: Intents
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListIntents:
    def test_returns_intents(self, client: TC, mock_trade_facade: MC) -> None:
        mock_trade_facade.list_intents.return_value = [_make_intent()]
        resp = client.get("/api/v1/trade/intents", params={"strategy_id": "strat-a"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["intent_id"] == "int-001"

    def test_empty_list(self, client: TC, mock_trade_facade: MC) -> None:
        mock_trade_facade.list_intents.return_value = []
        resp = client.get("/api/v1/trade/intents", params={"strategy_id": "strat-a"})
        assert resp.status_code == 200
        assert resp.json()["data"] == []


@pytest.mark.integration
class TestUpdateIntentStatus:
    def test_update_success(self, client: TC, mock_status_handler: MC) -> None:
        mock_status_handler.handle.return_value = True
        resp = client.put(
            "/api/v1/trade/intents/int-001/status",
            json={"status": "cancelled"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] is True


# ---------------------------------------------------------------------------
# Tests: Fills
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRecordFill:
    def test_record_success(self, client: TC, mock_fill_handler: MC) -> None:
        fill = _make_fill()
        mock_fill_handler.handle.return_value = fill
        resp = client.post(
            "/api/v1/trade/fills",
            json={
                "fill_id": "fill-001",
                "intent_id": "int-001",
                "strategy_id": "strat-a",
                "trade_date": "2024-01-16",
                "instrument_id": 510300,
                "direction": "buy",
                "quantity": 1000,
                "fill_price": 4.12,
                "fee": 5.0,
                "slippage": 0.0,
                "notes": "",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["fill_id"] == "fill-001"


@pytest.mark.integration
class TestListFills:
    def test_returns_fills(self, client: TC, mock_portfolio_facade: MC) -> None:
        fill = _make_fill()
        mock_portfolio_facade.get_fills.return_value = [fill]
        resp = client.get("/api/v1/trade/fills", params={"strategy_id": "strat-a"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1


# ---------------------------------------------------------------------------
# Tests: Positions
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListPositions:
    def test_returns_positions(self, client: TC, mock_portfolio_facade: MC) -> None:
        pos = _make_position()
        mock_portfolio_facade.get_position_history.return_value = [pos]
        resp = client.get("/api/v1/trade/positions", params={"strategy_id": "strat-a"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["instrument_id"] == 510300


# ---------------------------------------------------------------------------
# Tests: P&L
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestComputePnl:
    def test_returns_pnl(self, client: TC, mock_portfolio_facade: MC) -> None:
        mock_portfolio_facade.compute_pnl.return_value = PnlSummary(
            total_realized_pnl=100.0,
            total_unrealized_pnl=-50.0,
            total_fees=10.0,
            net_pnl=40.0,
        )
        resp = client.get(
            "/api/v1/trade/pnl",
            params={"strategy_id": "strat-a", "snapshot_date": "2024-01-16"},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["net_pnl"] == 40.0


# ---------------------------------------------------------------------------
# Tests: Signals
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLatestSignals:
    def test_returns_latest(self, client: TC, mock_signal_facade: MC) -> None:
        mock_signal_facade.get_latest_intents.return_value = [_make_intent()]
        resp = client.get(
            "/api/v1/trade/signals/latest",
            params={"strategy_id": "strat-a"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1


@pytest.mark.integration
class TestSignalIntentsByDate:
    def test_returns_by_date(self, client: TC, mock_signal_facade: MC) -> None:
        mock_signal_facade.get_intents_by_date.return_value = [_make_intent()]
        resp = client.get(
            "/api/v1/trade/signals/2024-01-15/intents",
            params={"strategy_id": "strat-a"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1


# ---------------------------------------------------------------------------
# Tests: Comparison
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestComparison:
    def test_returns_metrics(self, client: TC, mock_comparison_facade: MC) -> None:
        from ditto_app.query.comparison import ComparisonMetrics

        metrics = ComparisonMetrics(
            backtest_return=0.15,
            actual_return=0.12,
            return_diff=-0.03,
            return_diff_bps=-300.0,
            backtest_sharpe=1.5,
            actual_sharpe=1.2,
            backtest_total_cost=500.0,
            actual_total_cost=600.0,
            cost_drag_bps=20.0,
            nav_correlation=0.98,
            max_nav_diff_bps=150.0,
            avg_daily_tracking_error_bps=30.0,
        )
        mock_comparison_facade.get_comparison.return_value = metrics
        resp = client.get(
            "/api/v1/trade/comparison",
            params={"strategy_id": "strat-a", "run_id": "run-001"},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["backtest_return"] == 0.15
        assert body["actual_return"] == 0.12

    def test_not_found(self, client: TC, mock_comparison_facade: MC) -> None:
        mock_comparison_facade.get_comparison.return_value = None
        resp = client.get(
            "/api/v1/trade/comparison",
            params={"strategy_id": "strat-a", "run_id": "run-999"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Error Scenarios (Phase 4.8)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMissingRequiredParams:
    """缺少必需参数 → 422 Unprocessable Entity."""

    def test_list_intents_missing_strategy_id(
        self, client: TC, mock_trade_facade: MC
    ) -> None:
        """list_intents 缺少 strategy_id → 422."""
        resp = client.get("/api/v1/trade/intents")
        assert resp.status_code == 422

    def test_list_fills_missing_strategy_id(
        self, client: TC, mock_portfolio_facade: MC
    ) -> None:
        """list_fills 缺少 strategy_id → 422."""
        resp = client.get("/api/v1/trade/fills")
        assert resp.status_code == 422

    def test_list_positions_missing_strategy_id(
        self, client: TC, mock_portfolio_facade: MC
    ) -> None:
        """list_positions 缺少 strategy_id → 422."""
        resp = client.get("/api/v1/trade/positions")
        assert resp.status_code == 422

    def test_compute_pnl_missing_params(
        self, client: TC, mock_portfolio_facade: MC
    ) -> None:
        """compute_pnl 缺少 strategy_id 和 snapshot_date → 422."""
        resp = client.get("/api/v1/trade/pnl")
        assert resp.status_code == 422

    def test_compute_pnl_missing_snapshot_date(
        self, client: TC, mock_portfolio_facade: MC
    ) -> None:
        """compute_pnl 缺少 snapshot_date → 422."""
        resp = client.get(
            "/api/v1/trade/pnl",
            params={"strategy_id": "strat-a"},
        )
        assert resp.status_code == 422

    def test_comparison_missing_params(
        self, client: TC, mock_comparison_facade: MC
    ) -> None:
        """comparison 缺少 strategy_id 和 run_id → 422."""
        resp = client.get("/api/v1/trade/comparison")
        assert resp.status_code == 422

    def test_signals_latest_missing_strategy_id(
        self, client: TC, mock_signal_facade: MC
    ) -> None:
        """signals/latest 缺少 strategy_id → 422."""
        resp = client.get("/api/v1/trade/signals/latest")
        assert resp.status_code == 422

    def test_signal_intents_missing_strategy_id(
        self, client: TC, mock_signal_facade: MC
    ) -> None:
        """signals/{date}/intents 缺少 strategy_id → 422."""
        resp = client.get("/api/v1/trade/signals/2024-01-15/intents")
        assert resp.status_code == 422


@pytest.mark.integration
class TestInvalidRequestBody:
    """无效请求体 → 422 Unprocessable Entity."""

    def test_record_fill_missing_required_fields(self, client: TC) -> None:
        """record_fill 缺少必需字段 → 422."""
        resp = client.post(
            "/api/v1/trade/fills",
            json={"fill_id": "fill-001"},  # 缺少大量必需字段
        )
        assert resp.status_code == 422

    def test_record_fill_empty_body(self, client: TC) -> None:
        """record_fill 空请求体 → 422."""
        resp = client.post("/api/v1/trade/fills", json={})
        assert resp.status_code == 422

    def test_record_fill_invalid_direction(self, client: TC) -> None:
        """record_fill direction 不在 buy/sell 枚举中 → 422."""
        resp = client.post(
            "/api/v1/trade/fills",
            json={
                "fill_id": "fill-001",
                "intent_id": "int-001",
                "strategy_id": "strat-a",
                "trade_date": "2024-01-16",
                "instrument_id": 510300,
                "direction": "hold",
                "quantity": 1000,
                "fill_price": 4.12,
            },
        )
        assert resp.status_code == 422

    def test_record_fill_invalid_quantity_type(self, client: TC) -> None:
        """record_fill quantity 为字符串 → 422 (strict mode)."""
        resp = client.post(
            "/api/v1/trade/fills",
            json={
                "fill_id": "fill-001",
                "intent_id": "int-001",
                "strategy_id": "strat-a",
                "trade_date": "2024-01-16",
                "instrument_id": 510300,
                "direction": "buy",
                "quantity": "one thousand",
                "fill_price": 4.12,
            },
        )
        assert resp.status_code == 422

    def test_update_status_invalid_value(self, client: TC) -> None:
        """update_intent_status status 不在有效枚举中 → 422."""
        resp = client.put(
            "/api/v1/trade/intents/int-001/status",
            json={"status": "executing"},
        )
        assert resp.status_code == 422

    def test_update_status_empty_body(self, client: TC) -> None:
        """update_intent_status 空请求体 → 422."""
        resp = client.put(
            "/api/v1/trade/intents/int-001/status",
            json={},
        )
        assert resp.status_code == 422


@pytest.mark.integration
class TestBusinessRuleErrors:
    """业务规则违反 → 正确的 4xx HTTP 状态码 (M2).

    - not found → 404
    - transition → 409
    - 其他 ValueError → 400
    """

    def test_update_status_intent_not_found(
        self, client: TC, mock_status_handler: MC
    ) -> None:
        """更新不存在的 intent 状态 → 404."""
        mock_status_handler.handle.side_effect = ValueError("Intent not found: int-999")
        resp = client.put(
            "/api/v1/trade/intents/int-999/status",
            json={"status": "cancelled"},
        )
        assert resp.status_code == 404

    def test_update_status_invalid_transition(
        self, client: TC, mock_status_handler: MC
    ) -> None:
        """非法状态转换 (filled → pending) → 409."""
        mock_status_handler.handle.side_effect = ValueError(
            "Invalid transition: 'filled' -> 'pending'"
        )
        resp = client.put(
            "/api/v1/trade/intents/int-001/status",
            json={"status": "pending"},
        )
        assert resp.status_code == 409

    def test_record_fill_intent_not_found(
        self, client: TC, mock_fill_handler: MC
    ) -> None:
        """录入成交时 intent 不存在 → 404."""
        mock_fill_handler.handle.side_effect = ValueError("Intent not found: int-999")
        resp = client.post(
            "/api/v1/trade/fills",
            json={
                "fill_id": "fill-001",
                "intent_id": "int-999",
                "strategy_id": "strat-a",
                "trade_date": "2024-01-16",
                "instrument_id": 510300,
                "direction": "buy",
                "quantity": 1000,
                "fill_price": 4.12,
            },
        )
        assert resp.status_code == 404

    def test_record_fill_strategy_mismatch(
        self, client: TC, mock_fill_handler: MC
    ) -> None:
        """录入成交时 strategy_id 不匹配 → 400."""
        mock_fill_handler.handle.side_effect = ValueError(
            "Strategy mismatch: intent=strat-a, command=strat-b"
        )
        resp = client.post(
            "/api/v1/trade/fills",
            json={
                "fill_id": "fill-002",
                "intent_id": "int-001",
                "strategy_id": "strat-b",
                "trade_date": "2024-01-16",
                "instrument_id": 510300,
                "direction": "buy",
                "quantity": 1000,
                "fill_price": 4.12,
            },
        )
        assert resp.status_code == 400

    def test_record_fill_already_filled(
        self, client: TC, mock_fill_handler: MC
    ) -> None:
        """对已成交的 intent 录入成交 → 400."""
        mock_fill_handler.handle.side_effect = ValueError(
            "Intent int-001 status is 'filled',"
            " expected 'pending' or 'partially_filled'"
        )
        resp = client.post(
            "/api/v1/trade/fills",
            json={
                "fill_id": "fill-003",
                "intent_id": "int-001",
                "strategy_id": "strat-a",
                "trade_date": "2024-01-16",
                "instrument_id": 510300,
                "direction": "buy",
                "quantity": 1000,
                "fill_price": 4.12,
            },
        )
        assert resp.status_code == 400
