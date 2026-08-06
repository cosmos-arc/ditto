"""Daily decision cockpit query facade tests."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import orjson
import pytest
from ditto_application.execution_dto import ActualPositionSnapshot, TradeIntent
from ditto_application.queries.daily_decision import DailyDecisionV2Report
from ditto_application.queries.daily_decision_projection import (
    persisted_intents_match_package,
)
from ditto_application.queries.deviation import (
    SignalDeviationItem,
    SignalDeviationReport,
)
from ditto_application.queries.portfolio_actual import PnlSummary
from ditto_application.signal_package_contract import compute_signal_package_checksum
from ditto_execution.models import AccountSnapshotRecord
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.runs.models import StrategyRunRecord

_TEST_EOD_BATCH_KEY = "eod-2024-01-15-strat-a-3"  # gitleaks:allow


def _intent(
    *,
    intent_id: str | None = None,
    signal_date: str = "2024-01-15",
    instrument_id: int = 510300,
) -> TradeIntent:
    return TradeIntent(
        intent_id=intent_id or _fixture_intent_id(),
        strategy_id="strat-a",
        signal_date=signal_date,
        instrument_id=instrument_id,
        direction="buy",
        target_weight=0.3,
        current_weight=0.1,
        delta_weight=0.2,
        quantity=1000,
        status="pending",
    )


def _position() -> ActualPositionSnapshot:
    return ActualPositionSnapshot(
        snapshot_id="snap-1",
        strategy_id="strat-a",
        snapshot_date="2024-01-15",
        instrument_id=510300,
        quantity=1000,
        available_quantity=1000,
        average_cost=4.0,
        market_value=4000.0,
        unrealized_pnl=10.0,
        realized_pnl=5.0,
        total_fees=1.0,
    )


def _deviation() -> SignalDeviationReport:
    return SignalDeviationReport(
        strategy_id="strat-a",
        signal_date="2024-01-15",
        total_signals=1,
        filled=1,
        unfilled=0,
        items=(
            SignalDeviationItem(
                instrument_id=510300,
                signal_action="buy",
                signal_weight=0.3,
                actual_weight=0.3,
                deviation_bps=0.0,
                fill_status="filled",
            ),
        ),
    )


def _pnl() -> PnlSummary:
    return PnlSummary(
        total_realized_pnl=5.0,
        total_unrealized_pnl=10.0,
        total_fees=1.0,
        net_pnl=14.0,
    )


def _package_artifact(
    *,
    outcome: str = "completed",
    no_rebalance: bool = False,
    intents: list[dict[str, object]] | None = None,
    strategy_version: str = "3",
    status: str = "active",
    artifact_id: str | None = None,
    created_at: str = "2024-01-15T20:00:00Z",
) -> StrategyArtifactRecord:
    persisted_intents = (
        intents
        if intents is not None
        else [
            {
                "intent_id": "intent-1",
                "strategy_id": "strat-a",
                "signal_date": "2024-01-15",
                "instrument_id": 510300,
                "direction": "buy",
                "target_weight": 0.3,
                "current_weight": 0.1,
                "delta_weight": 0.2,
                "quantity": 1000,
                "raw_quantity": 1050,
                "rounded_quantity": 1000,
                "lot_size": 100,
                "reference_price": 4.2,
                "cash_impact": -4200.0,
                "sizing_reason": "rounded_down_to_board_lot",
                "sizing_readiness": "ready",
                "status": "pending",
            }
        ]
    )
    business_payload: dict[str, object] = {
        "account_id": "account-1",
        "cash_target": 0.6,
        "dataset_snapshot_ids": {"etf_daily": "snapshot-etf"},
        "factor_ids": ["momentum_1m"],
        "factor_values": {"510300": {"momentum_1m": 1.2}},
        "intents": [
            {key: value for key, value in item.items() if key != "intent_id"}
            for item in persisted_intents
        ],
        "risk_flags": [],
        "required_datasets": ["etf_daily"],
        "required_dataset_states": [
            {
                "dataset": "etf_daily",
                "status": "ready",
                "snapshot_id": "snapshot-etf",
                "reason": "",
            }
        ],
        "selection_reasons": {
            "510300": {
                "instrument_id": 510300,
                "target_weight": 0.3,
                "composite_score": 1.2,
                "rank": 1,
                "positive_contributors": ["momentum_1m"],
                "negative_contributors": [],
                "industry": None,
            }
        },
        "signal_date": "2024-01-15",
        "sleeve_id": "manual-account-1-strat-a",
        "decision_date": "2024-01-15",
        "intended_trade_date": "2024-01-16",
        "strategy_id": "strat-a",
        "strategy_version": strategy_version,
    }
    checksum = compute_signal_package_checksum(business_payload)
    batch_key = f"eod-2024-01-15-strat-a-{strategy_version}"
    revision = checksum.removeprefix("sha256:")[:12]
    persisted_intents = [
        {
            **item,
            "intent_id": (
                f"sig-{batch_key}-2024-01-15-{revision}-"
                f"{item['instrument_id']}-{item['direction']}"
            ),
        }
        for item in persisted_intents
    ]
    return StrategyArtifactRecord(
        artifact_id=(
            artifact_id
            or f"signal-package-strat-a-v{strategy_version}-2024-01-15-revision"
        ),
        strategy_id="strat-a",
        run_id=batch_key,
        artifact_type=ArtifactKind.SIGNAL_PACKAGE,
        file_path="inline://signal-package",
        metadata={
            **business_payload,
            "schema_version": "1.0",
            "business_payload": business_payload,
            "batch_key": batch_key,
            "checksum": checksum,
            "outcome": outcome,
            "no_rebalance": no_rebalance,
            "intents": persisted_intents,
        },
        status=status,
        created_at=created_at,
    )


def _fixture_intent_id() -> str:
    raw_intents = _package_artifact().metadata["intents"]
    assert isinstance(raw_intents, list)
    intent_id = raw_intents[0]["intent_id"]
    assert isinstance(intent_id, str)
    return intent_id


def _account_baseline() -> object:
    from ditto_application.queries.account import AccountBaselineReadModel

    return AccountBaselineReadModel(
        account=AccountSnapshotRecord(
            snapshot_id="account-snapshot-1",
            run_id="manual-account-1-strat-a",
            strategy_id="strat-a",
            account_id="account-1",
            snapshot_date="2024-01-15",
            cash_available=6000.0,
            cash_settled=6000.0,
            cash_frozen=0.0,
            total_value=10_000.0,
            nav=1.02,
            exposure=4000.0,
        ),
        positions=(),
    )


def _without_business_field(
    artifact: StrategyArtifactRecord,
    field: str,
) -> StrategyArtifactRecord:
    metadata = dict(artifact.metadata)
    raw_business_payload = metadata["business_payload"]
    assert isinstance(raw_business_payload, dict)
    business_payload = dict(raw_business_payload)
    metadata.pop(field, None)
    business_payload.pop(field, None)
    metadata["business_payload"] = business_payload
    checksum = compute_signal_package_checksum(business_payload)
    metadata["checksum"] = checksum
    raw_intents = metadata.get("intents")
    if isinstance(raw_intents, list):
        revision = checksum.removeprefix("sha256:")[:12]
        metadata["intents"] = [
            {
                **item,
                "intent_id": (
                    f"sig-{metadata['batch_key']}-2024-01-15-{revision}-"
                    f"{item['instrument_id']}-{item['direction']}"
                ),
            }
            for item in raw_intents
            if isinstance(item, dict)
        ]
    return replace(artifact, metadata=metadata)


def _eod_run(
    *,
    error_message: str,
    config_json: str,
    status: str = "failed",
    strategy_id: str = "strat-a",
    strategy_version: str = "3",
    mode: str = "recommendation",
) -> StrategyRunRecord:
    return StrategyRunRecord(
        run_id=_TEST_EOD_BATCH_KEY,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        mode=mode,
        status=status,
        error_message=error_message,
        config_json=config_json,
    )


def _valid_run_reader() -> MagicMock:
    reader = MagicMock()
    reader.get_run.return_value = _eod_run(
        error_message="",
        config_json="",
        status="completed",
    )
    return reader


def _missing_package_report(run: StrategyRunRecord) -> DailyDecisionV2Report:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = []
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    run_reader = MagicMock()
    run_reader.get_run.return_value = run
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []
    return DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(
        strategy_id="strat-a",
        trade_date="2024-01-15",
        account_id="account-1",
    )


def test_infers_latest_signal_date_from_signal_facade() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    signal_facade = MagicMock()
    signal_facade.get_latest_intents.return_value = [
        _intent(intent_id="old", signal_date="2024-01-14"),
        _intent(intent_id="new", signal_date="2024-01-15"),
    ]
    portfolio_facade = MagicMock()
    portfolio_facade.get_position_history.return_value = [_position()]
    portfolio_facade.compute_pnl.return_value = _pnl()
    deviation_facade = MagicMock()
    deviation_facade.get_deviation.return_value = _deviation()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
    ).get_report(strategy_id="strat-a")

    assert report.trade_date == "2024-01-15"
    signal_facade.get_latest_intents.assert_called_once_with("strat-a")
    portfolio_facade.get_position_history.assert_called_once_with(
        "strat-a",
        snapshot_date="2024-01-15",
    )
    deviation_facade.get_deviation.assert_called_once_with(
        strategy_id="strat-a",
        signal_date="2024-01-15",
    )


def test_returns_ready_report_with_daily_artifacts() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [_intent()]
    portfolio_facade = MagicMock()
    portfolio_facade.get_position_history.return_value = [_position()]
    portfolio_facade.compute_pnl.return_value = _pnl()
    deviation_facade = MagicMock()
    deviation_facade.get_deviation.return_value = _deviation()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
    ).get_report(strategy_id="strat-a", trade_date="2024-01-15")

    assert report.readiness_status == "ready"
    assert report.readiness_reasons == ()
    assert report.signal_intents == (_intent(),)
    assert report.positions == (_position(),)
    assert report.deviation == _deviation()
    assert report.pnl == _pnl()


def test_marks_review_when_positions_are_missing() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [_intent()]
    portfolio_facade = MagicMock()
    portfolio_facade.get_position_history.return_value = []
    portfolio_facade.compute_pnl.return_value = _pnl()
    deviation_facade = MagicMock()
    deviation_facade.get_deviation.return_value = _deviation()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
    ).get_report(strategy_id="strat-a", trade_date="2024-01-15")

    assert report.readiness_status == "review"
    assert report.readiness_reasons == ("positions unavailable for trade date",)


def test_returns_structured_blocked_report_when_no_signals_exist() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    signal_facade = MagicMock()
    signal_facade.get_latest_intents.return_value = []
    portfolio_facade = MagicMock()
    deviation_facade = MagicMock()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
    ).get_report(strategy_id="strat-a")

    assert report.strategy_id == "strat-a"
    assert report.trade_date is None
    assert report.readiness_status == "blocked"
    assert report.readiness_reasons == ("no signal intents available",)
    assert report.signal_intents == ()
    assert report.positions == ()
    assert report.deviation is None
    assert report.pnl is None
    portfolio_facade.get_position_history.assert_not_called()
    deviation_facade.get_deviation.assert_not_called()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"active_strategy": False}, ("blocked", ("NO_ACTIVE_STRATEGY",))),
        ({"data_ready": False}, ("blocked", ("REQUIRED_DATA_NOT_READY",))),
        ({"account_ready": False}, ("blocked", ("ACCOUNT_BASELINE_MISSING",))),
        ({"run_exists": False}, ("blocked", ("EOD_RUN_MISSING",))),
        ({"run_failed": True}, ("blocked", ("EOD_RUN_FAILED",))),
        ({"package_exists": False}, ("blocked", ("SIGNAL_PACKAGE_MISSING",))),
        ({"checksum_valid": False}, ("blocked", ("CHECKSUM_MISMATCH",))),
        ({"no_rebalance": True}, ("review", ("NO_REBALANCE_REQUIRED",))),
        ({"risk_warning": True}, ("review", ("RISK_WARNING",))),
        ({"date_mismatch": True}, ("review", ("TRADE_DATE_MISMATCH",))),
        ({"unresolved_conflict": True}, ("review", ("RERUN_CONFLICT",))),
        (
            {"fill_quantity_exceeded": True},
            ("review", ("FILL_QUANTITY_EXCEEDED",)),
        ),
        ({"quantity_available": False}, ("review", ("QUANTITY_UNAVAILABLE",))),
        ({}, ("ready", ("READY_FOR_REVIEW",))),
    ],
)
def test_v2_r1_reason_code_contract(
    overrides: dict[str, object],
    expected: tuple[str, tuple[str, ...]],
) -> None:
    """R1 计划 3.5 是 V2 readiness 的唯一 reason-code 真值表。"""
    from ditto_application.queries.daily_decision import (
        ReadinessFacts,
        evaluate_readiness,
    )

    assert evaluate_readiness(ReadinessFacts(**overrides)) == expected  # type: ignore[arg-type]


def test_v2_reads_package_baseline_sizing_evidence_and_effective_fills() -> None:
    """V2 sections 必须来自持久事实源，不能保留 None/空元组占位。"""
    from ditto_application.execution_dto import ManualExecutionFill
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    intent_id = _fixture_intent_id()
    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [_package_artifact()]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="", config_json="", status="completed"
    )
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [
        _intent(intent_id=intent_id).__class__(
            **{
                **_intent(intent_id=intent_id).__dict__,
                "status": "partially_filled",
            }
        )
    ]
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = [
        ManualExecutionFill(
            fill_id="fill-1",
            intent_id=intent_id,
            strategy_id="strat-a",
            trade_date="2024-01-16",
            instrument_id=510300,
            direction="buy",
            quantity=400,
            fill_price=4.21,
            fee=5.0,
        )
    ]
    portfolio_facade.compute_pnl.return_value = _pnl()
    deviation_facade = MagicMock()
    deviation_facade.get_deviation.return_value = _deviation()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(
        strategy_id="strat-a",
        trade_date="2024-01-15",
        account_id="account-1",
    )

    assert report.identity == {
        "strategy_id": "strat-a",
        "strategy_version": "3",
        "account_id": "account-1",
        "sleeve_id": "manual-account-1-strat-a",
        "signal_date": "2024-01-15",
        "decision_date": "2024-01-15",
        "intended_trade_date": "2024-01-16",
    }
    assert report.readiness == {
        "status": "ready",
        "reason_codes": ("READY_FOR_REVIEW",),
        "details": ("建议、数据、账户与风险证据已就绪, 请人工复核",),
    }
    assert report.account_positions["baseline_id"] == "account-snapshot-1"
    assert report.account_positions["cash_available"] == 6000.0
    assert report.account_positions["total_value"] == 10_000.0
    assert report.account_positions["nav"] == 1.02
    assert report.actions[0]["raw_quantity"] == 1050
    assert report.actions[0]["rounded_quantity"] == 1000
    assert report.actions[0]["reference_price"] == 4.2
    assert report.actions[0]["suggested_quantity"] == 1000
    assert report.actions[0]["lot_size"] == 100
    assert report.actions[0]["cash_impact"] == -4200.0
    assert report.actions[0]["reason"] == "rounded_down_to_board_lot"
    assert report.actions[0]["sizing_readiness"] == "ready"
    assert report.actions[0]["filled_quantity"] == 400
    assert report.actions[0]["remaining_quantity"] == 600
    assert report.actions[0]["intent_status"] == "partially_filled"
    effective_fills = report.execution_review["effective_fills"]
    assert isinstance(effective_fills, tuple)
    assert isinstance(effective_fills[0], ManualExecutionFill)
    assert effective_fills[0].fill_id == "fill-1"
    assert report.execution_review["pnl"] == _pnl()
    account_query.get_latest.assert_called_once_with(
        account_id="account-1",
        strategy_id="strat-a",
        signal_date="2024-01-15",
    )
    deviation_facade.get_deviation.assert_called_once_with(
        strategy_id="strat-a",
        signal_date="2024-01-15",
        execution_date="2024-01-16",
        intent_ids=(intent_id,),
    )


def test_v2_keeps_overfill_visible_as_stable_review_evidence() -> None:
    """真实超额成交不能丢弃，也不能伪装成重跑冲突。"""
    from ditto_application.execution_dto import ManualExecutionFill
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    intent_id = _fixture_intent_id()
    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [_package_artifact()]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [
        replace(_intent(intent_id=intent_id), status="filled")
    ]
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = [
        ManualExecutionFill(
            fill_id="fill-over",
            intent_id=intent_id,
            strategy_id="strat-a",
            trade_date="2024-01-16",
            instrument_id=510300,
            direction="buy",
            quantity=1200,
            fill_price=4.21,
            fee=5.0,
        )
    ]
    portfolio_facade.compute_pnl.return_value = _pnl()
    deviation_facade = MagicMock()
    deviation_facade.get_deviation.return_value = _deviation()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=_valid_run_reader(),
    ).get_report_v2(
        strategy_id="strat-a",
        trade_date="2024-01-15",
        account_id="account-1",
    )

    assert report.actions[0]["filled_quantity"] == 1200
    assert report.actions[0]["suggested_quantity"] == 1000
    assert report.readiness["status"] == "review"
    assert report.readiness["reason_codes"] == ("FILL_QUANTITY_EXCEEDED",)
    assert report.execution_review["unresolved_conflicts"] == (
        f"OVERFILLED:{intent_id}",
    )


def test_v2_without_account_id_uses_persisted_package_identity() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [_package_artifact()]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [_intent()]
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=_valid_run_reader(),
    ).get_report_v2(strategy_id="strat-a", trade_date="2024-01-15")

    assert report.identity["account_id"] == "account-1"
    assert report.identity["sleeve_id"] == "manual-account-1-strat-a"
    assert report.readiness["reason_codes"] == ("READY_FOR_REVIEW",)
    account_query.get_latest.assert_called_once_with(
        account_id="account-1",
        strategy_id="strat-a",
        signal_date="2024-01-15",
    )


@pytest.mark.parametrize("drop_field", ["account_id", "sleeve_id"])
def test_v2_fails_closed_when_package_account_identity_is_incomplete(
    drop_field: str,
) -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    artifact = _package_artifact()
    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [
        _without_business_field(artifact, drop_field)
    ]
    account_query = MagicMock()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)

    report = DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=MagicMock(),
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=_valid_run_reader(),
    ).get_report_v2(strategy_id="strat-a", account_id="account-1")

    assert report.readiness["reason_codes"] == ("ACCOUNT_BASELINE_MISSING",)
    account_query.get_latest.assert_not_called()


def test_v2_fails_closed_when_requested_account_conflicts_with_package() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [_package_artifact()]
    account_query = MagicMock()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)

    report = DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=MagicMock(),
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=_valid_run_reader(),
    ).get_report_v2(strategy_id="strat-a", account_id="another-account")

    assert report.identity["account_id"] == "account-1"
    assert report.readiness["reason_codes"] == ("ACCOUNT_BASELINE_MISSING",)
    account_query.get_latest.assert_not_called()


def test_v2_zero_rebalance_uses_package_date_without_signal_intents() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [
        _package_artifact(outcome="no_rebalance", no_rebalance=True, intents=[])
    ]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = []
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=_valid_run_reader(),
    ).get_report_v2(strategy_id="strat-a", account_id="account-1")

    assert report.identity["signal_date"] == "2024-01-15"
    assert report.actions == ()
    assert report.readiness["status"] == "review"
    assert report.readiness["reason_codes"] == ("NO_REBALANCE_REQUIRED",)


def test_v2_blocks_when_persisted_package_checksum_does_not_match() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    artifact = _package_artifact()
    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [
        replace(artifact, metadata={**artifact.metadata, "checksum": "sha256:tampered"})
    ]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [_intent()]
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=_valid_run_reader(),
    ).get_report_v2(
        strategy_id="strat-a",
        trade_date="2024-01-15",
        account_id="account-1",
    )

    assert report.readiness["status"] == "blocked"
    assert report.readiness["reason_codes"] == ("CHECKSUM_MISMATCH",)
    assert report.run_package["checksum_valid"] is False


@pytest.mark.parametrize(
    "missing_field",
    [
        "raw_quantity",
        "rounded_quantity",
        "lot_size",
        "reference_price",
        "cash_impact",
        "sizing_reason",
        "sizing_readiness",
    ],
)
def test_v2_does_not_guess_when_package_sizing_evidence_is_missing(
    missing_field: str,
) -> None:
    """历史 quantity 不能替代 package 中缺失的 sizing 证据。"""
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    intent = dict(_package_artifact().metadata["intents"][0])  # type: ignore[index]
    intent.pop(missing_field)
    package_reader = MagicMock()
    artifact = _package_artifact(intents=[intent])
    package_reader.list_by_strategy.return_value = [artifact]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="", config_json="", status="completed"
    )
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []
    signal_facade = MagicMock()
    raw_intents = artifact.metadata["intents"]
    assert isinstance(raw_intents, list)
    artifact_intent_id = raw_intents[0]["intent_id"]
    assert isinstance(artifact_intent_id, str)
    signal_facade.get_intents_by_date.return_value = [
        _intent(intent_id=artifact_intent_id)
    ]

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(strategy_id="strat-a", account_id="account-1")

    assert report.readiness["status"] == "review"
    assert report.readiness["reason_codes"] == ("QUANTITY_UNAVAILABLE",)
    if missing_field == "rounded_quantity":
        assert report.actions[0]["suggested_quantity"] is None


def test_v2_blocks_when_required_dataset_contract_is_missing() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    artifact = _package_artifact()
    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [
        _without_business_field(artifact, "required_datasets")
    ]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="", config_json="", status="completed"
    )
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(strategy_id="strat-a", account_id="account-1")

    assert report.readiness["status"] == "blocked"
    assert report.readiness["reason_codes"] == ("REQUIRED_DATA_NOT_READY",)


def test_v2_blocks_when_run_record_is_missing_even_if_package_exists() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [_package_artifact()]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    run_reader = MagicMock()
    run_reader.get_run.return_value = None
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(strategy_id="strat-a", account_id="account-1")

    assert report.readiness["status"] == "blocked"
    assert report.readiness["reason_codes"] == ("EOD_RUN_MISSING",)


def test_v2_failed_run_record_overrides_completed_package_metadata() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [_package_artifact()]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="failed:EOD_RUN_FAILED",
        config_json="",
        status="failed",
    )
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(strategy_id="strat-a", account_id="account-1")

    assert report.run_package["outcome"] == "failed"
    assert report.readiness["status"] == "blocked"
    assert report.readiness["reason_codes"] == ("EOD_RUN_FAILED",)


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("account_id", "attacker-account"),
        ("dataset_snapshot_ids", {"etf_daily": "attacker-snapshot"}),
        ("intents", []),
    ],
)
def test_v2_fails_closed_when_duplicated_package_metadata_is_tampered(
    field: str,
    tampered: object,
) -> None:
    """Checksum-covered facts must have one canonical source of truth."""
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    artifact = _package_artifact()
    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [
        replace(artifact, metadata={**artifact.metadata, field: tampered})
    ]
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="", config_json="", status="completed"
    )
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(
        strategy_id="strat-a",
        trade_date="2024-01-15",
        account_id="account-1",
    )

    assert report.readiness["reason_codes"] == ("CHECKSUM_MISMATCH",)
    assert report.run_package["checksum_valid"] is False


def test_v2_uses_package_for_latest_published_version_only() -> None:
    """A stale package must not make a newer published version look ready."""
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [
        _package_artifact(strategy_version="3")
    ]
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=4)
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    run_reader = MagicMock()
    run_reader.get_run.return_value = None
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(
        strategy_id="strat-a",
        trade_date="2024-01-15",
        account_id="account-1",
    )

    assert report.identity["strategy_version"] == "4"
    assert report.run_package["batch_key"] == "eod-2024-01-15-strat-a-4"
    assert report.run_package["artifact_id"] is None
    assert report.readiness["reason_codes"] == ("EOD_RUN_MISSING",)
    run_reader.get_run.assert_called_once_with("eod-2024-01-15-strat-a-4")


def test_v2_reports_successful_run_without_package_as_package_missing() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = []
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="",
        config_json="",
        status="completed",
    )
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(
        strategy_id="strat-a",
        trade_date="2024-01-15",
        account_id="account-1",
    )

    assert report.readiness["reason_codes"] == ("SIGNAL_PACKAGE_MISSING",)


def test_v2_rebuilds_dataset_evidence_from_blocked_run_without_package() -> None:
    config_json = orjson.dumps(
        {
            "batch_key": _TEST_EOD_BATCH_KEY,
            "outcome": "blocked",
            "required_dataset_states": [
                {
                    "dataset": "etf_daily",
                    "status": "dq_failed",
                    "snapshot_id": "snapshot-etf",
                    "reason": "DQ_FAILED: null ratio",
                },
                {
                    "dataset": "valuation",
                    "status": "missing",
                    "snapshot_id": None,
                    "reason": "partition missing",
                },
            ],
            "signal_date": "2024-01-15",
        }
    ).decode("utf-8")

    report = _missing_package_report(
        _eod_run(
            error_message="blocked:REQUIRED_DATA_NOT_READY",
            config_json=config_json,
        )
    )

    assert report.readiness["status"] == "blocked"
    assert report.readiness["reason_codes"] == ("REQUIRED_DATA_NOT_READY",)
    assert report.run_package["outcome"] == "blocked"
    assert report.data == {
        "required_datasets": ("etf_daily", "valuation"),
        "snapshot_ids": {"etf_daily": "snapshot-etf"},
        "dataset_states": (
            {
                "dataset": "etf_daily",
                "status": "dq_failed",
                "snapshot_id": "snapshot-etf",
                "reason": "DQ_FAILED: null ratio",
            },
            {
                "dataset": "valuation",
                "status": "missing",
                "snapshot_id": None,
                "reason": "partition missing",
            },
        ),
        "freshness": "blocked",
        "dq_state": "failed",
    }


def test_v2_treats_failed_run_prefix_as_eod_failure_without_package() -> None:
    report = _missing_package_report(
        _eod_run(
            error_message="failed:RuntimeError: artifact store unavailable",
            config_json="",
            status="completed",
        )
    )

    assert report.run_package["outcome"] == "failed"
    assert report.readiness["status"] == "blocked"
    assert report.readiness["reason_codes"] == ("EOD_RUN_FAILED",)


@pytest.mark.parametrize(
    "config_json",
    [
        "{not-json",
        "[]",
        orjson.dumps(
            {
                "batch_key": _TEST_EOD_BATCH_KEY,
                "outcome": "blocked",
                "required_dataset_states": [
                    {
                        "dataset": "attacker_dataset",
                        "status": "ready",
                        "snapshot_id": "attacker-snapshot",
                        "reason": "",
                    }
                ],
                "signal_date": "2024-01-14",
            }
        ).decode("utf-8"),
        orjson.dumps(
            {
                "batch_key": "eod-2024-01-14-strat-a-3",
                "outcome": "blocked",
                "required_dataset_states": [
                    {
                        "dataset": "attacker_dataset",
                        "status": "ready",
                        "snapshot_id": "attacker-snapshot",
                        "reason": "",
                    }
                ],
                "signal_date": "2024-01-15",
            }
        ).decode("utf-8"),
    ],
    ids=("non-json", "wrong-shape", "wrong-date", "wrong-batch"),
)
def test_v2_blocked_run_rejects_malformed_or_mismatched_config(
    config_json: str,
) -> None:
    report = _missing_package_report(
        _eod_run(
            error_message="blocked:REQUIRED_DATA_NOT_READY",
            config_json=config_json,
        )
    )

    assert report.readiness["reason_codes"] == ("REQUIRED_DATA_NOT_READY",)
    assert report.run_package["outcome"] == "blocked"
    assert report.data["required_datasets"] == ()
    assert report.data["snapshot_ids"] == {}
    assert report.data["dataset_states"] == ()


@pytest.mark.parametrize(
    ("identity_overrides"),
    [
        {"strategy_id": "wrong-strategy"},
        {"strategy_version": "999"},
        {"mode": "backtest"},
    ],
    ids=("strategy", "version", "mode"),
)
def test_v2_blocked_run_rejects_mismatched_record_identity(
    identity_overrides: dict[str, str],
) -> None:
    config_json = orjson.dumps(
        {
            "batch_key": _TEST_EOD_BATCH_KEY,
            "outcome": "blocked",
            "required_dataset_states": [
                {
                    "dataset": "forged_dataset",
                    "status": "ready",
                    "snapshot_id": "forged-snapshot",
                    "reason": "",
                }
            ],
            "signal_date": "2024-01-15",
        }
    ).decode("utf-8")

    report = _missing_package_report(
        _eod_run(
            error_message="blocked:REQUIRED_DATA_NOT_READY",
            config_json=config_json,
            **identity_overrides,
        )
    )

    assert report.readiness["reason_codes"] == ("EOD_RUN_MISSING",)
    assert report.data["required_datasets"] == ()
    assert report.data["snapshot_ids"] == {}
    assert report.data["dataset_states"] == ()


def test_v2_surfaces_persisted_conflict_without_hiding_active_package() -> None:
    """Conflict evidence is durable while the original fills/actions remain visible."""
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    active = _package_artifact()
    conflict = _package_artifact(
        outcome="rerun_conflict",
        status="conflict",
        artifact_id="signal-package-strat-a-v3-2024-01-15-conflict",
        created_at="2024-01-15T21:00:00Z",
    )
    conflict = replace(
        conflict,
        metadata={
            **conflict.metadata,
            "conflicting_artifact_id": active.artifact_id,
        },
    )
    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [conflict, active]
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="", config_json="", status="completed"
    )
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [_intent()]
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(
        strategy_id="strat-a",
        trade_date="2024-01-15",
        account_id="account-1",
    )

    assert report.run_package["artifact_id"] == active.artifact_id
    assert report.run_package["conflict_artifact_id"] == conflict.artifact_id
    assert report.run_package["outcome"] == "rerun_conflict"
    assert report.actions[0]["intent_id"] == _fixture_intent_id()
    assert report.readiness["status"] == "review"
    assert report.readiness["reason_codes"] == ("RERUN_CONFLICT",)


def test_v2_running_run_never_trusts_completed_package_outcome() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [_package_artifact()]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="",
        config_json="",
        status="running",
    )
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [_intent()]
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(strategy_id="strat-a", account_id="account-1")

    assert report.run_package["outcome"] == "running"
    assert report.readiness["status"] == "blocked"
    assert report.readiness["reason_codes"] == ("EOD_RUN_INCOMPLETE",)


def test_v2_package_run_identity_is_always_validated() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [_package_artifact()]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="",
        config_json="",
        status="completed",
        strategy_id="attacker-strategy",
    )
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [_intent()]
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(strategy_id="strat-a", account_id="account-1")

    assert report.readiness["status"] == "blocked"
    assert report.readiness["reason_codes"] == ("EOD_RUN_MISSING",)


def test_v2_missing_persisted_intent_fails_closed() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [_package_artifact()]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=3)
    run_reader = MagicMock()
    run_reader.get_run.return_value = _eod_run(
        error_message="",
        config_json="",
        status="completed",
    )
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = []
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(strategy_id="strat-a", account_id="account-1")

    assert report.actions[0]["intent_status"] is None
    assert report.readiness["status"] == "blocked"
    assert report.readiness["reason_codes"] == ("SIGNAL_INTENT_MISMATCH",)


def test_v2_ignores_an_older_published_version_intent_on_the_same_date() -> None:
    """A new published batch owns its intents without inheriting v3 pending rows."""
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    package = _package_artifact(strategy_version="4")
    raw_intents = package.metadata["intents"]
    assert isinstance(raw_intents, list)
    current_intent_id = raw_intents[0]["intent_id"]
    assert isinstance(current_intent_id, str)

    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [package]
    account_query = MagicMock()
    account_query.get_latest.return_value = _account_baseline()
    strategy_query = MagicMock()
    strategy_query.get_active_published.return_value = MagicMock(version=4)
    run_reader = MagicMock()
    run_reader.get_run.return_value = replace(
        _eod_run(error_message="", config_json="", status="completed"),
        run_id="eod-2024-01-15-strat-a-4",
        strategy_version="4",
    )
    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [
        _intent(),
        _intent(intent_id=current_intent_id),
    ]
    portfolio_facade = MagicMock()
    portfolio_facade.get_effective_fills.return_value = []

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=MagicMock(),
        package_reader=package_reader,
        account_query=account_query,
        strategy_query=strategy_query,
        run_reader=run_reader,
    ).get_report_v2(
        strategy_id="strat-a",
        trade_date="2024-01-15",
        account_id="account-1",
    )

    assert report.readiness["status"] == "ready"
    assert report.readiness["reason_codes"] == ("READY_FOR_REVIEW",)
    assert [action["intent_id"] for action in report.actions] == [current_intent_id]


def test_package_intents_require_exact_non_superseded_persisted_id_set() -> None:
    raw = _package_artifact().metadata["intents"]
    assert isinstance(raw, list)
    raw_intents = tuple(item for item in raw if isinstance(item, dict))
    current = _intent()
    extra = _intent(
        intent_id=("sig-eod-2024-01-15-strat-a-3-2024-01-15-stalechecksum-510500-buy"),
        instrument_id=510500,
    )

    assert not persisted_intents_match_package(
        raw_intents=raw_intents,
        persisted_intents={
            current.intent_id: current,
            extra.intent_id: extra,
        },
    )


def test_package_intents_allow_superseded_history_outside_package() -> None:
    raw = _package_artifact().metadata["intents"]
    assert isinstance(raw, list)
    raw_intents = tuple(item for item in raw if isinstance(item, dict))
    current = _intent()
    old = replace(
        _intent(intent_id="old-revision", instrument_id=510500),
        status="superseded",
    )

    assert persisted_intents_match_package(
        raw_intents=raw_intents,
        persisted_intents={current.intent_id: current, old.intent_id: old},
    )


def test_latest_package_orders_by_business_signal_date_before_created_at() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    latest_signal = _package_artifact(created_at="2024-01-15T20:00:00Z")
    late_old_revision = _package_artifact(
        artifact_id="late-old-revision",
        created_at="2024-01-20T20:00:00Z",
    )
    old_metadata = {
        **late_old_revision.metadata,
        "signal_date": "2024-01-14",
    }
    late_old_revision = replace(late_old_revision, metadata=old_metadata)
    package_reader = MagicMock()
    package_reader.list_by_strategy.return_value = [
        latest_signal,
        late_old_revision,
    ]

    facade = DailyDecisionQueryFacade(
        signal_facade=MagicMock(),
        portfolio_facade=MagicMock(),
        deviation_facade=MagicMock(),
        package_reader=package_reader,
    )

    assert facade._latest_package("strat-a", None, "3") == latest_signal
