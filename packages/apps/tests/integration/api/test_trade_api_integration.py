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

from typing import cast
from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.commands.account import (
    AccountBaselineResult,
    ImportAccountBaselineHandler,
)
from ditto_application.commands.trade import (
    RecordFillHandler,
    ReplaceFillHandler,
    UpdateIntentStatusHandler,
    VoidFillHandler,
)
from ditto_application.exceptions import AppConflictError, AppNotFoundError
from ditto_application.execution_dto import (
    ActualPositionSnapshot,
    FillAdjustment,
    ManualExecutionFill,
    TradeIntent,
)
from ditto_application.queries.account import (
    AccountBaselineQuery,
    AccountBaselineReadModel,
)
from ditto_application.queries.comparison import ComparisonQueryFacade
from ditto_application.queries.daily_decision import (
    DailyDecisionQueryFacade,
    DailyDecisionReport,
    DailyDecisionV2Report,
)
from ditto_application.queries.daily_decision_v3 import (
    DailyDecisionV3QueryFacade,
    DailyDecisionV3Report,
    FactorRiskSection,
    PortfolioConstructionSection,
    ProvenanceSection,
    ReconciliationSection,
    StressTestSection,
    TailRiskSection,
)
from ditto_application.queries.deviation import (
    SignalDeviationItem,
    SignalDeviationQueryFacade,
    SignalDeviationReport,
)
from ditto_application.queries.portfolio_actual import (
    PnlSummary,
    PortfolioActualQueryFacade,
)
from ditto_application.queries.signal import SignalQueryFacade
from ditto_application.queries.trade import TradeQueryFacade
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.trade import router
from ditto_apps.middleware import api_error_handler
from ditto_execution.models import AccountSnapshotRecord, PositionRecord
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
def mock_daily_decision_facade() -> MagicMock:
    return MagicMock(spec=DailyDecisionQueryFacade)


@pytest.fixture
def mock_daily_decision_v3_facade() -> MagicMock:
    return MagicMock(spec=DailyDecisionV3QueryFacade)


@pytest.fixture
def mock_deviation_facade() -> MagicMock:
    return MagicMock(spec=SignalDeviationQueryFacade)


@pytest.fixture
def mock_fill_handler() -> MagicMock:
    return MagicMock(spec=RecordFillHandler)


@pytest.fixture
def mock_void_fill_handler() -> MagicMock:
    return MagicMock(spec=VoidFillHandler)


@pytest.fixture
def mock_replace_fill_handler() -> MagicMock:
    return MagicMock(spec=ReplaceFillHandler)


@pytest.fixture
def mock_status_handler() -> MagicMock:
    return MagicMock(spec=UpdateIntentStatusHandler)


@pytest.fixture
def mock_account_handler() -> MagicMock:
    return MagicMock(spec=ImportAccountBaselineHandler)


@pytest.fixture
def mock_account_query() -> MagicMock:
    return MagicMock(spec=AccountBaselineQuery)


@pytest.fixture
def app(request: pytest.FixtureRequest) -> FastAPI:
    def mock(name: str) -> MagicMock:
        return cast(MagicMock, request.getfixturevalue(name))

    mock_trade_facade = mock("mock_trade_facade")
    mock_portfolio_facade = mock("mock_portfolio_facade")
    mock_signal_facade = mock("mock_signal_facade")
    mock_comparison_facade = mock("mock_comparison_facade")
    mock_daily_decision_facade = mock("mock_daily_decision_facade")
    mock_daily_decision_v3_facade = mock("mock_daily_decision_v3_facade")
    mock_deviation_facade = mock("mock_deviation_facade")
    mock_fill_handler = mock("mock_fill_handler")
    mock_void_fill_handler = mock("mock_void_fill_handler")
    mock_replace_fill_handler = mock("mock_replace_fill_handler")
    mock_status_handler = mock("mock_status_handler")
    mock_account_handler = mock("mock_account_handler")
    mock_account_query = mock("mock_account_query")
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
        def daily_decision_facade(self) -> DailyDecisionQueryFacade:
            return mock_daily_decision_facade

        @provide
        def daily_decision_v3_facade(self) -> DailyDecisionV3QueryFacade:
            return mock_daily_decision_v3_facade

        @provide
        def deviation_facade(self) -> SignalDeviationQueryFacade:
            return mock_deviation_facade

        @provide
        def fill_handler(self) -> RecordFillHandler:
            return mock_fill_handler

        @provide
        def void_fill_handler(self) -> VoidFillHandler:
            return mock_void_fill_handler

        @provide
        def replace_fill_handler(self) -> ReplaceFillHandler:
            return mock_replace_fill_handler

        @provide
        def status_handler(self) -> UpdateIntentStatusHandler:
            return mock_status_handler

        @provide
        def account_handler(self) -> ImportAccountBaselineHandler:
            return mock_account_handler

        @provide
        def account_query(self) -> AccountBaselineQuery:
            return mock_account_query

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


def _make_daily_decision_v2_report() -> DailyDecisionV2Report:
    return DailyDecisionV2Report(
        identity={
            "strategy_id": "strat-a",
            "strategy_version": "1",
            "account_id": "account-1",
            "sleeve_id": "core",
            "signal_date": "2024-01-15",
            "decision_date": "2024-01-15",
            "intended_trade_date": "2024-01-16",
        },
        readiness={"status": "ready", "reason_codes": (), "details": ()},
        data={
            "required_datasets": ("stock_daily",),
            "snapshot_ids": {"stock_daily": "snapshot-stock"},
            "dataset_states": (
                {
                    "dataset": "stock_daily",
                    "status": "ready",
                    "snapshot_id": "snapshot-stock",
                    "reason": "",
                },
            ),
            "freshness": "ready",
            "dq_state": "passed",
        },
        run_package={
            "outcome": "completed",
            "batch_key": "eod-2024-01-15-strat-a-1",
            "artifact_id": "package-1",
            "conflict_artifact_id": None,
            "checksum": "sha256:package",
            "checksum_valid": True,
            "no_rebalance": False,
            "factor_evidence": {},
            "risk_evidence": (),
        },
        account_positions={
            "baseline_id": "baseline-1",
            "account_id": "account-1",
            "sleeve_id": "core",
            "cash_available": 10_000.0,
            "cash_settled": 10_000.0,
            "cash_frozen": 0.0,
            "total_value": 10_000.0,
            "nav": 1.0,
            "exposure": 0.0,
            "as_of": "2024-01-15",
            "positions": (),
        },
        actions=(),
        execution_review={
            "effective_fills": (),
            "deviation": None,
            "pnl": None,
            "exceptions": (),
            "unresolved_conflicts": (),
        },
    )


class TestAccountBaseline:
    """账户基线导入与按信号日读取 API。"""

    def test_import_empty_positions_returns_stable_identity(
        self, client: TC, mock_account_handler: MC
    ) -> None:
        mock_account_handler.handle.return_value = AccountBaselineResult(
            snapshot_id="baseline-abc",
            sleeve_id="manual-acct-strat-a",
            status="created",
        )

        response = client.post(
            "/api/v1/trade/account-baseline",
            json={
                "account_id": "acct",
                "strategy_id": "strat-a",
                "snapshot_date": "2024-01-15",
                "cash_available": 1000.0,
                "cash_settled": 1000.0,
                "cash_frozen": 0.0,
                "total_value": 1000.0,
                "nav": 1.0,
                "positions": [],
            },
        )

        assert response.status_code == 200
        assert response.json()["data"] == {
            "snapshot_id": "baseline-abc",
            "sleeve_id": "manual-acct-strat-a",
            "status": "created",
        }
        command = mock_account_handler.handle.call_args.args[0]
        assert command.positions == ()

    def test_rejects_negative_values_before_handler(
        self, client: TC, mock_account_handler: MC
    ) -> None:
        response = client.post(
            "/api/v1/trade/account-baseline",
            json={
                "account_id": "acct",
                "strategy_id": "strat-a",
                "snapshot_date": "2024-01-15",
                "cash_available": -1.0,
                "cash_settled": 0.0,
                "cash_frozen": 0.0,
                "total_value": 0.0,
                "nav": 1.0,
            },
        )

        assert response.status_code == 422
        mock_account_handler.handle.assert_not_called()

    def test_idempotent_replay_returns_unchanged(
        self, client: TC, mock_account_handler: MC
    ) -> None:
        mock_account_handler.handle.return_value = AccountBaselineResult(
            snapshot_id="baseline-abc",
            sleeve_id="manual-acct-strat-a",
            status="unchanged",
        )
        payload = {
            "account_id": "acct",
            "strategy_id": "strat-a",
            "snapshot_date": "2024-01-15",
            "cash_available": 1000.0,
            "cash_settled": 1000.0,
            "cash_frozen": 0.0,
            "total_value": 1000.0,
            "nav": 1.0,
            "positions": [],
        }

        response = client.post("/api/v1/trade/account-baseline", json=payload)

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "unchanged"

    def test_explicit_replacement_flag_reaches_command(
        self, client: TC, mock_account_handler: MC
    ) -> None:
        mock_account_handler.handle.return_value = AccountBaselineResult(
            snapshot_id="baseline-new",
            sleeve_id="manual-acct-strat-a",
            status="replaced",
        )

        response = client.post(
            "/api/v1/trade/account-baseline",
            json={
                "account_id": "acct",
                "strategy_id": "strat-a",
                "snapshot_date": "2024-01-15",
                "cash_available": 1000.0,
                "cash_settled": 1000.0,
                "cash_frozen": 0.0,
                "total_value": 1000.0,
                "nav": 1.0,
                "positions": [],
                "replace_confirmed": True,
            },
        )

        assert response.status_code == 200
        command = mock_account_handler.handle.call_args.args[0]
        assert command.replace_confirmed is True

    def test_rejects_malformed_snapshot_date_before_handler(
        self, client: TC, mock_account_handler: MC
    ) -> None:
        response = client.post(
            "/api/v1/trade/account-baseline",
            json={
                "account_id": "acct",
                "strategy_id": "strat-a",
                "snapshot_date": "2024/01/15",
                "cash_available": 1000.0,
                "cash_settled": 1000.0,
                "cash_frozen": 0.0,
                "total_value": 1000.0,
                "nav": 1.0,
            },
        )

        assert response.status_code == 422
        mock_account_handler.handle.assert_not_called()

    def test_query_returns_account_and_same_baseline_positions(
        self, client: TC, mock_account_query: MC
    ) -> None:
        account = AccountSnapshotRecord(
            snapshot_id="baseline-abc",
            run_id="manual-acct-strat-a",
            strategy_id="strat-a",
            account_id="acct",
            snapshot_date="2024-01-15",
            cash_available=500.0,
            cash_settled=500.0,
            cash_frozen=0.0,
            total_value=1000.0,
            nav=1.0,
            exposure=500.0,
            created_at="2024-01-15T08:00:00+00:00",
        )
        position = PositionRecord(
            snapshot_id="baseline-abc-510300",
            run_id=account.run_id,
            strategy_id=account.strategy_id,
            snapshot_date=account.snapshot_date,
            instrument_id=510300,
            quantity=100,
            available_quantity=100,
            average_cost=5.0,
            market_value=500.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
            created_at=account.created_at,
        )
        mock_account_query.get_latest.return_value = AccountBaselineReadModel(
            account=account,
            positions=(position,),
        )

        response = client.get(
            "/api/v1/trade/account-baseline",
            params={
                "account_id": "acct",
                "strategy_id": "strat-a",
                "signal_date": "2024-01-16",
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["snapshot_date"] == "2024-01-15"
        assert response.json()["data"]["positions"][0]["snapshot_id"] == (
            "baseline-abc-510300"
        )


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


def _make_adjustment(**overrides: object) -> FillAdjustment:
    defaults: dict[str, object] = {
        "adjustment_id": "adj-001",
        "fill_id": "fill-001",
        "adjustment_type": "void",
        "replacement_fill_id": None,
        "reason": "duplicate fill",
        "created_at": "2026-07-16T10:00:00Z",
    }
    defaults.update(overrides)
    return FillAdjustment(**defaults)  # type: ignore[arg-type]


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


def _make_deviation_report(**overrides: object) -> SignalDeviationReport:
    defaults: dict[str, object] = {
        "strategy_id": "strat-a",
        "signal_date": "2024-01-15",
        "total_signals": 1,
        "filled": 1,
        "unfilled": 0,
        "items": (
            SignalDeviationItem(
                instrument_id=510300,
                signal_action="buy",
                signal_weight=0.3,
                actual_weight=0.3,
                deviation_bps=0.0,
                fill_status="filled",
            ),
        ),
    }
    defaults.update(overrides)
    return SignalDeviationReport(**defaults)  # type: ignore[arg-type]


def _make_daily_decision_report(**overrides: object) -> DailyDecisionReport:
    defaults: dict[str, object] = {
        "strategy_id": "strat-a",
        "trade_date": "2024-01-15",
        "readiness_status": "ready",
        "readiness_reasons": (),
        "signal_intents": (_make_intent(),),
        "deviation": _make_deviation_report(),
        "positions": (_make_position(snapshot_date="2024-01-15"),),
        "pnl": PnlSummary(
            total_realized_pnl=100.0,
            total_unrealized_pnl=-50.0,
            total_fees=10.0,
            net_pnl=40.0,
        ),
    }
    defaults.update(overrides)
    return DailyDecisionReport(**defaults)  # type: ignore[arg-type]


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

    def test_returns_effective_fills(
        self,
        client: TC,
        mock_portfolio_facade: MC,
    ) -> None:
        mock_portfolio_facade.get_effective_fills.return_value = [_make_fill()]

        resp = client.get(
            "/api/v1/trade/fills/effective",
            params={"strategy_id": "strat-a"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"][0]["fill_id"] == "fill-001"
        mock_portfolio_facade.get_effective_fills.assert_called_once_with(
            strategy_id="strat-a",
            start_date=None,
            end_date=None,
        )

    def test_returns_fill_adjustments(
        self,
        client: TC,
        mock_portfolio_facade: MC,
    ) -> None:
        mock_portfolio_facade.get_fill_adjustments.return_value = [
            _make_adjustment(
                adjustment_type="replace",
                replacement_fill_id="fill-002",
            )
        ]

        resp = client.get(
            "/api/v1/trade/fill-adjustments",
            params={
                "strategy_id": "strat-a",
                "fill_id": "fill-001",
                "intent_id": "intent-001",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["data"][0]["replacement_fill_id"] == "fill-002"
        mock_portfolio_facade.get_fill_adjustments.assert_called_once_with(
            strategy_id="strat-a",
            fill_id="fill-001",
            intent_id="intent-001",
        )


@pytest.mark.integration
class TestFillAdjustments:
    def test_void_fill_returns_append_only_event(
        self,
        client: TC,
        mock_void_fill_handler: MC,
    ) -> None:
        mock_void_fill_handler.handle.return_value = _make_adjustment()

        resp = client.post(
            "/api/v1/trade/fills/fill-001/void",
            json={"adjustment_id": "adj-001", "reason": "duplicate fill"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["adjustment_type"] == "void"
        command = mock_void_fill_handler.handle.call_args.args[0]
        assert command.fill_id == "fill-001"
        assert command.adjustment_id == "adj-001"

    def test_replace_fill_returns_link_event(
        self,
        client: TC,
        mock_replace_fill_handler: MC,
    ) -> None:
        mock_replace_fill_handler.handle.return_value = _make_adjustment(
            adjustment_type="replace",
            replacement_fill_id="fill-002",
            reason="correct price",
        )

        resp = client.post(
            "/api/v1/trade/fills/fill-001/replace",
            json={
                "adjustment_id": "adj-001",
                "replacement_fill_id": "fill-002",
                "trade_date": "2026-07-16",
                "quantity": 100,
                "fill_price": 4.21,
                "fee": 1.0,
                "slippage": 0.0,
                "notes": "broker correction",
                "reason": "correct price",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["replacement_fill_id"] == "fill-002"
        command = mock_replace_fill_handler.handle.call_args.args[0]
        assert command.fill_id == "fill-001"
        assert command.replacement_fill_id == "fill-002"


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
# Tests: Daily Decision
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDailyDecision:
    def test_v2_returns_stable_readiness_sections(
        self, client: TC, mock_daily_decision_facade: MC
    ) -> None:
        mock_daily_decision_facade.get_report_v2.return_value = DailyDecisionV2Report(
            identity={
                "strategy_id": "strat-a",
                "strategy_version": "1",
                "account_id": "account-1",
                "sleeve_id": "manual-account-1-strat-a",
                "signal_date": "2024-01-15",
                "decision_date": "2024-01-15",
                "intended_trade_date": "2024-01-16",
            },
            readiness={
                "status": "review",
                "reason_codes": ("NO_REBALANCE_REQUIRED",),
                "details": ("本日无需调仓, 请复核 package 证据",),
            },
            data={
                "required_datasets": ("etf_daily",),
                "snapshot_ids": {"etf_daily": "snapshot-etf"},
                "dataset_states": (
                    {
                        "dataset": "etf_daily",
                        "status": "ready",
                        "snapshot_id": "snapshot-etf",
                        "reason": "",
                    },
                ),
                "freshness": "ready",
                "dq_state": "passed",
            },
            run_package={
                "outcome": "no_rebalance",
                "batch_key": "eod-2024-01-15-strat-a-1",
                "artifact_id": "package-1",
                "conflict_artifact_id": "package-conflict-1",
                "checksum": "sha256:package",
                "checksum_valid": True,
                "no_rebalance": True,
                "factor_evidence": {},
                "risk_evidence": (),
            },
            account_positions={
                "baseline_id": "baseline-1",
                "account_id": "account-1",
                "sleeve_id": "manual-account-1-strat-a",
                "cash_available": 10_000.0,
                "cash_settled": 10_000.0,
                "cash_frozen": 0.0,
                "total_value": 10_000.0,
                "nav": 1.0,
                "exposure": 0.0,
                "as_of": "2024-01-15",
                "positions": (),
            },
            actions=(),
            execution_review={
                "effective_fills": (),
                "deviation": None,
                "pnl": None,
                "exceptions": (),
                "unresolved_conflicts": (),
            },
        )

        response = client.get(
            "/api/v1/trade/daily-decision/v2",
            params={
                "strategy_id": "strat-a",
                "trade_date": "2024-01-15",
                "account_id": "account-1",
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["readiness"]["status"] == "review"
        assert response.json()["data"]["run_package"]["outcome"] == "no_rebalance"
        assert (
            response.json()["data"]["run_package"]["conflict_artifact_id"]
            == "package-conflict-1"
        )
        mock_daily_decision_facade.get_report_v2.assert_called_once_with(
            strategy_id="strat-a",
            trade_date="2024-01-15",
            account_id="account-1",
        )

    def test_v2_openapi_uses_typed_nested_sections(self, client: TC) -> None:
        """前端 codegen 不得再把七个 V2 section 生成为 unknown record。"""
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        report = schemas["DailyDecisionV2Response"]

        for field in (
            "identity",
            "readiness",
            "data",
            "run_package",
            "account_positions",
            "execution_review",
        ):
            assert "$ref" in report["properties"][field]
        assert report["properties"]["actions"]["items"] == {
            "$ref": "#/components/schemas/DailyDecisionActionResponse"
        }
        action = schemas["DailyDecisionActionResponse"]
        assert {
            "intent_id",
            "instrument_id",
            "target_weight",
            "raw_quantity",
            "rounded_quantity",
            "suggested_quantity",
            "reference_price",
            "lot_size",
            "cash_impact",
            "reason",
            "sizing_readiness",
            "filled_quantity",
            "remaining_quantity",
        } <= set(action["properties"])
        assert (
            "conflict_artifact_id"
            in schemas["DailyDecisionRunPackageResponse"]["properties"]
        )

    def test_v3_returns_typed_risk_and_reconciliation_sections(
        self,
        client: TC,
        mock_daily_decision_v3_facade: MC,
    ) -> None:
        mock_daily_decision_v3_facade.get_report_v3.return_value = (
            DailyDecisionV3Report(
                v2=_make_daily_decision_v2_report(),
                readiness="blocked",
                blocking_reasons=("RECONCILIATION_MISMATCH",),
                portfolio_construction=PortfolioConstructionSection(
                    status="optimal",
                    mode="enforced",
                    policy_digest="sha256:policy",
                    solver="OSQP",
                    solver_version="1.1.3",
                    solver_status="optimal",
                    duration_ms=12.0,
                ),
                tail_risk=TailRiskSection(0.04, 0.03, 0.02, 0.025, 42),
                factor_risk=FactorRiskSection(
                    availability="partial",
                    total_risk=0.10,
                    marginal_contributions={"size": 0.2},
                    percentage_contributions={"size": 1.0},
                    euler_residual=0.0,
                ),
                stress_tests=StressTestSection(
                    catalog_version="r4-v1",
                    losses={"hypothetical:market-minus-10pct": 0.08},
                    unavailable_scenarios=(
                        "hypothetical:style-factor-plus-minus-3sigma",
                    ),
                ),
                reconciliation=ReconciliationSection(
                    status="mismatch",
                    differences=("risk_position_fingerprint",),
                    alert_idempotency_key="reconciliation:abc",
                ),
                provenance=ProvenanceSection(
                    decision_time="2024-01-15T15:00:00Z",
                    knowledge_cutoff="2024-01-15T14:59:00Z",
                    publication_cutoff="2024-01-15T14:59:00Z",
                    source_snapshot_ids=("snapshot-stock",),
                    generated_at="2024-01-15T15:01:00Z",
                ),
            )
        )

        response = client.get(
            "/api/v1/trade/daily-decision/v3",
            params={
                "strategy_id": "strat-a",
                "trade_date": "2024-01-15",
                "account_id": "account-1",
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["readiness"] == "blocked"
        assert data["tail_risk"]["historical_es99"] == 0.04
        assert data["factor_risk"]["availability"] == "partial"
        assert data["factor_risk"]["marginal_contributions"] == {"size": 0.2}
        assert data["stress_tests"]["unavailable_scenarios"] == [
            "hypothetical:style-factor-plus-minus-3sigma"
        ]
        assert data["reconciliation"]["status"] == "mismatch"
        mock_daily_decision_v3_facade.get_report_v3.assert_called_once_with(
            strategy_id="strat-a",
            trade_date="2024-01-15",
            account_id="account-1",
        )

    def test_returns_report(
        self,
        client: TC,
        mock_daily_decision_facade: MC,
    ) -> None:
        mock_daily_decision_facade.get_report.return_value = (
            _make_daily_decision_report()
        )

        resp = client.get(
            "/api/v1/trade/daily-decision",
            params={"strategy_id": "strat-a", "trade_date": "2024-01-15"},
        )

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["strategy_id"] == "strat-a"
        assert body["trade_date"] == "2024-01-15"
        assert body["readiness"]["status"] == "ready"
        assert body["readiness"]["reasons"] == []
        assert body["signal_intents"][0]["intent_id"] == "int-001"
        assert body["positions"][0]["snapshot_id"] == "snap-001"
        assert body["deviation"]["total_signals"] == 1
        assert body["pnl"]["net_pnl"] == 40.0
        mock_daily_decision_facade.get_report.assert_called_once_with(
            strategy_id="strat-a",
            trade_date="2024-01-15",
        )

    def test_returns_empty_structured_report_when_no_signals_exist(
        self,
        client: TC,
        mock_daily_decision_facade: MC,
    ) -> None:
        mock_daily_decision_facade.get_report.return_value = (
            _make_daily_decision_report(
                trade_date=None,
                readiness_status="blocked",
                readiness_reasons=("no signal intents available",),
                signal_intents=(),
                deviation=None,
                positions=(),
                pnl=None,
            )
        )

        resp = client.get(
            "/api/v1/trade/daily-decision",
            params={"strategy_id": "strat-a"},
        )

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["trade_date"] is None
        assert body["readiness"] == {
            "status": "blocked",
            "reasons": ["no signal intents available"],
        }
        assert body["signal_intents"] == []
        assert body["positions"] == []
        assert body["deviation"] is None
        assert body["pnl"] is None
        mock_daily_decision_facade.get_report.assert_called_once_with(
            strategy_id="strat-a",
            trade_date=None,
        )


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

    def test_daily_decision_missing_strategy_id(self, client: TC) -> None:
        """daily-decision 缺少 strategy_id → 422."""
        resp = client.get("/api/v1/trade/daily-decision")
        assert resp.status_code == 422

    def test_effective_fills_missing_strategy_id(self, client: TC) -> None:
        resp = client.get("/api/v1/trade/fills/effective")
        assert resp.status_code == 422

    def test_fill_adjustments_missing_strategy_id(self, client: TC) -> None:
        resp = client.get("/api/v1/trade/fill-adjustments")
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

    def test_record_fill_impossible_calendar_date_is_422(
        self,
        client: TC,
        mock_fill_handler: MC,
    ) -> None:
        resp = client.post(
            "/api/v1/trade/fills",
            json={
                "fill_id": "fill-001",
                "intent_id": "int-001",
                "strategy_id": "strat-a",
                "trade_date": "2026-02-31",
                "instrument_id": 510300,
                "direction": "buy",
                "quantity": 1000,
                "fill_price": 4.12,
            },
        )

        assert resp.status_code == 422
        mock_fill_handler.handle.assert_not_called()

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

    def test_void_fill_blank_reason(self, client: TC) -> None:
        resp = client.post(
            "/api/v1/trade/fills/fill-001/void",
            json={"adjustment_id": "adj-001", "reason": ""},
        )
        assert resp.status_code == 422

    def test_replace_fill_invalid_economics(self, client: TC) -> None:
        resp = client.post(
            "/api/v1/trade/fills/fill-001/replace",
            json={
                "adjustment_id": "adj-001",
                "replacement_fill_id": "fill-002",
                "trade_date": "2026/07/16",
                "quantity": 0,
                "fill_price": 4.21,
                "reason": "correction",
            },
        )
        assert resp.status_code == 422

    def test_replace_fill_impossible_calendar_date_is_422(
        self,
        client: TC,
        mock_replace_fill_handler: MC,
    ) -> None:
        resp = client.post(
            "/api/v1/trade/fills/fill-001/replace",
            json={
                "adjustment_id": "adj-001",
                "replacement_fill_id": "fill-002",
                "trade_date": "2026-02-31",
                "quantity": 100,
                "fill_price": 4.21,
                "reason": "correction",
            },
        )

        assert resp.status_code == 422
        mock_replace_fill_handler.handle.assert_not_called()


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

    def test_void_fill_not_found_is_typed_404(
        self,
        client: TC,
        mock_void_fill_handler: MC,
    ) -> None:
        mock_void_fill_handler.handle.side_effect = AppNotFoundError(
            "Fill not found: fill-missing"
        )

        resp = client.post(
            "/api/v1/trade/fills/fill-missing/void",
            json={"adjustment_id": "adj-001", "reason": "duplicate fill"},
        )

        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NOT_FOUND"

    def test_replace_fill_conflict_is_typed_409(
        self,
        client: TC,
        mock_replace_fill_handler: MC,
    ) -> None:
        mock_replace_fill_handler.handle.side_effect = AppConflictError(
            "Fill already adjusted: fill-001"
        )

        resp = client.post(
            "/api/v1/trade/fills/fill-001/replace",
            json={
                "adjustment_id": "adj-002",
                "replacement_fill_id": "fill-002",
                "trade_date": "2026-07-16",
                "quantity": 100,
                "fill_price": 4.21,
                "reason": "correct price",
            },
        )

        assert resp.status_code == 409
        assert resp.json()["error_code"] == "CONFLICT"


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
        self,
        client: TC,
        mock_deviation_facade: MC,
    ) -> None:
        """返回偏差报告 — 部分成交."""
        mock_deviation_facade.get_deviation.return_value = _make_deviation_report(
            total_signals=2,
            filled=1,
            unfilled=1,
            items=(
                SignalDeviationItem(
                    instrument_id=510300,
                    signal_action="buy",
                    signal_weight=0.3,
                    actual_weight=0.3,
                    deviation_bps=0.0,
                    fill_status="filled",
                ),
                SignalDeviationItem(
                    instrument_id=159915,
                    signal_action="sell",
                    signal_weight=0.2,
                    actual_weight=None,
                    deviation_bps=None,
                    fill_status="unfilled",
                ),
            ),
        )
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
        mock_deviation_facade.get_deviation.assert_called_once_with(
            strategy_id="strat-a",
            signal_date="2024-01-15",
            execution_date=None,
        )

    def test_all_filled(
        self,
        client: TC,
        mock_deviation_facade: MC,
    ) -> None:
        """所有信号均已成交."""
        mock_deviation_facade.get_deviation.return_value = _make_deviation_report()
        resp = client.get(
            "/api/v1/trade/deviation",
            params={"strategy_id": "strat-a", "signal_date": "2024-01-15"},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["filled"] == 1
        assert body["unfilled"] == 0

    def test_no_intents(
        self,
        client: TC,
        mock_deviation_facade: MC,
    ) -> None:
        """无信号时返回空报告."""
        mock_deviation_facade.get_deviation.return_value = _make_deviation_report(
            total_signals=0,
            filled=0,
            unfilled=0,
            items=(),
        )
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
