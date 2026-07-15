"""ManualSizingService 的 A 股建议数量规则。"""

from ditto_application.processes.execution.manual_sizing import (
    ManualSizingContext,
    ManualSizingRequest,
    ManualSizingService,
)
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess


def _request(**overrides: object) -> ManualSizingRequest:
    values: dict[str, object] = {
        "direction": "buy",
        "target_weight": 0.115,
        "nav": 10_000.0,
        "current_quantity": 0,
        "available_quantity": 0,
        "cash_available": 10_000.0,
        "reference_price": 10.0,
        "lot_size": 100,
    }
    values.update(overrides)
    return ManualSizingRequest(**values)  # type: ignore[arg-type]


def test_buy_150_raw_shares_rounds_down_to_one_board_lot() -> None:
    result = ManualSizingService().size(_request(target_weight=0.15, nav=10_000.0))

    assert result.raw_quantity == 150
    assert result.rounded_quantity == 100
    assert result.cash_impact == -1000.0
    assert result.reason == "rounded_down_to_board_lot"


def test_buy_is_capped_by_cash_and_risk_limit() -> None:
    result = ManualSizingService().size(
        _request(
            target_weight=0.8,
            cash_available=2_500.0,
            risk_quantity_limit=150,
        )
    )

    assert result.raw_quantity == 800
    assert result.rounded_quantity == 100
    assert result.reason == "capped_by_cash_and_risk_limit"


def test_buy_below_one_lot_is_reviewable_no_trade() -> None:
    result = ManualSizingService().size(_request(target_weight=0.05))

    assert result.raw_quantity == 50
    assert result.rounded_quantity == 0
    assert result.reason == "below_board_lot"
    assert result.readiness == "review"


def test_sell_uses_available_quantity_and_allows_odd_lot() -> None:
    result = ManualSizingService().size(
        _request(
            direction="sell",
            target_weight=0.0,
            current_quantity=250,
            available_quantity=150,
        )
    )

    assert result.raw_quantity == 250
    assert result.rounded_quantity == 150
    assert result.cash_impact == 1500.0
    assert result.reason == "t_plus1_available_quantity_cap"


def test_missing_price_and_market_blocks_produce_no_fake_quantity() -> None:
    service = ManualSizingService()

    missing = service.size(_request(reference_price=None))
    suspended = service.size(_request(is_suspended=True))
    limit_up = service.size(_request(at_price_limit=True))

    assert (missing.rounded_quantity, missing.reason, missing.readiness) == (
        0,
        "missing_reference_price",
        "blocked",
    )
    assert suspended.reason == "suspended"
    assert suspended.readiness == "blocked"
    assert limit_up.reason == "price_limit"
    assert limit_up.readiness == "review"


def test_identical_input_is_deterministic() -> None:
    service = ManualSizingService()
    request = _request(target_weight=0.3)

    assert service.size(request) == service.size(request)


def test_signal_snapshot_writes_suggested_quantity_only_with_current_context() -> None:
    reader = type(
        "Reader",
        (),
        {"get_current_positions": lambda self, strategy_id: {}},
    )()
    target = type("Target", (), {"positions": {510300: 0.15}})()
    process = SignalSnapshotProcess(
        position_reader=reader,
        sizing_service=ManualSizingService(),
    )

    intent = process.generate_intents(
        strategy_id="strategy-1",
        signal_date="2026-03-20",
        target=target,
        sizing_contexts={
            510300: ManualSizingContext(
                nav=10_000.0,
                current_quantity=0,
                available_quantity=0,
                cash_available=10_000.0,
                reference_price=10.0,
            )
        },
    )[0]

    assert intent.quantity == 100
