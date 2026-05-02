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
from ditto_application.commands.trade import (
    RecordFillHandler,
    UpdateIntentStatusHandler,
)
from ditto_application.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
    TradeIntent,
)
from ditto_application.queries.comparison import ComparisonQueryFacade
from ditto_application.queries.portfolio_actual import (
    PnlSummary,
    PortfolioActualQueryFacade,
)
from ditto_application.queries.signal import SignalQueryFacade
from ditto_application.queries.trade import TradeQueryFacade
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.trade import router
from ditto_apps.middleware import api_error_handler
from fastapi import FastAPI
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

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")

    # 注册 APIError 异常处理器
    app.add_exception_handler(APIError, api_error_handler)

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
        from ditto_application.queries.comparison_math import ComparisonMetrics

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


# ---------------------------------------------------------------------------
# Tests: Pagination
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPositionsPagination:
    """positions 端点分页."""

    def test_pagination_in_response(
        self, client: TC, mock_portfolio_facade: MC
    ) -> None:
        """positions 响应应包含 pagination 字段."""
        mock_portfolio_facade.get_position_history.return_value = [_make_position()]
        resp = client.get("/api/v1/trade/positions", params={"strategy_id": "strat-a"})
        assert resp.status_code == 200
        body = resp.json()
        assert "pagination" in body
        assert body["pagination"]["total"] == 1
        assert body["pagination"]["limit"] == 20
        assert body["pagination"]["offset"] == 0

    def test_pagination_limit_offset(
        self, client: TC, mock_portfolio_facade: MC
    ) -> None:
        """positions 支持 limit + offset 分页."""
        positions = [_make_position(snapshot_id=f"snap-{i}") for i in range(5)]
        mock_portfolio_facade.get_position_history.return_value = positions
        resp = client.get(
            "/api/v1/trade/positions",
            params={"strategy_id": "strat-a", "limit": 2, "offset": 1},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["total"] == 5
        assert body["pagination"]["limit"] == 2
        assert body["pagination"]["offset"] == 1
        assert len(body["data"]) == 2


@pytest.mark.integration
class TestSignalsLatestPagination:
    """signals/latest 端点分页."""

    def test_pagination_in_response(self, client: TC, mock_signal_facade: MC) -> None:
        """signals/latest 响应应包含 pagination 字段."""
        mock_signal_facade.get_latest_intents.return_value = [_make_intent()]
        resp = client.get(
            "/api/v1/trade/signals/latest",
            params={"strategy_id": "strat-a"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "pagination" in body
        assert body["pagination"]["total"] == 1


@pytest.mark.integration
class TestSignalIntentsPagination:
    """signals/{date}/intents 端点分页."""

    def test_pagination_in_response(self, client: TC, mock_signal_facade: MC) -> None:
        """signals/{date}/intents 响应应包含 pagination 字段."""
        mock_signal_facade.get_intents_by_date.return_value = [_make_intent()]
        resp = client.get(
            "/api/v1/trade/signals/2024-01-15/intents",
            params={"strategy_id": "strat-a"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "pagination" in body
        assert body["pagination"]["total"] == 1


# ---------------------------------------------------------------------------
# Tests: Deviation
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeviation:
    """信号-成交偏差报告."""

    def test_returns_deviation(
        self, client: TC, mock_trade_facade: MC, mock_portfolio_facade: MC
    ) -> None:
        """返回偏差报告 — 部分成交."""
        mock_trade_facade.list_intents.return_value = [
            _make_intent(instrument_id=510300, direction="buy", target_weight=0.3),
            _make_intent(
                intent_id="int-002",
                instrument_id=159915,
                direction="sell",
                target_weight=0.2,
            ),
        ]
        # 只有 510300 有成交
        mock_portfolio_facade.get_fills.return_value = [
            _make_fill(instrument_id=510300, quantity=1000),
        ]
        resp = client.get(
            "/api/v1/trade/deviation",
            params={"strategy_id": "strat-a", "signal_date": "2024-01-15"},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["strategy_id"] == "strat-a"
        assert body["signal_date"] == "2024-01-15"
        assert body["total_signals"] == 2
        assert body["filled"] == 1
        assert body["unfilled"] == 1
        assert len(body["items"]) == 2

        # 第一个有成交
        item_0 = body["items"][0]
        assert item_0["instrument_id"] == 510300
        assert item_0["fill_status"] == "filled"
        assert item_0["actual_weight"] == 0.3

        # 第二个无成交
        item_1 = body["items"][1]
        assert item_1["instrument_id"] == 159915
        assert item_1["fill_status"] == "unfilled"
        assert item_1["actual_weight"] is None

    def test_all_filled(
        self, client: TC, mock_trade_facade: MC, mock_portfolio_facade: MC
    ) -> None:
        """所有信号均已成交."""
        mock_trade_facade.list_intents.return_value = [
            _make_intent(instrument_id=510300),
        ]
        mock_portfolio_facade.get_fills.return_value = [
            _make_fill(instrument_id=510300),
        ]
        resp = client.get(
            "/api/v1/trade/deviation",
            params={"strategy_id": "strat-a", "signal_date": "2024-01-15"},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["filled"] == 1
        assert body["unfilled"] == 0

    def test_no_intents(
        self, client: TC, mock_trade_facade: MC, mock_portfolio_facade: MC
    ) -> None:
        """无信号时返回空报告."""
        mock_trade_facade.list_intents.return_value = []
        mock_portfolio_facade.get_fills.return_value = []
        resp = client.get(
            "/api/v1/trade/deviation",
            params={"strategy_id": "strat-a", "signal_date": "2024-01-15"},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["total_signals"] == 0
        assert body["filled"] == 0
        assert body["unfilled"] == 0
        assert body["items"] == []

    def test_missing_required_params(self, client: TC) -> None:
        """缺少必需参数 → 422."""
        resp = client.get("/api/v1/trade/deviation", params={"strategy_id": "strat-a"})
        assert resp.status_code == 422

        resp = client.get(
            "/api/v1/trade/deviation", params={"signal_date": "2024-01-15"}
        )
        assert resp.status_code == 422
