"""Signal package publisher unit tests."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_application.processes.execution.ports import PositionReader
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_execution.models import SignalRecord
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.models import TargetPortfolio


class _PositionReader(PositionReader):
    def get_current_positions(self, strategy_id: str) -> dict[int, float]:
        assert strategy_id == "stock-selection"
        return {1: 0.1}


@dataclass
class _IntentPort:
    saved: list[SignalRecord]

    def save_intent(self, record: SignalRecord) -> None:
        self.saved.append(record)

    def get_intent(self, intent_id: str) -> SignalRecord | None:
        return next((row for row in self.saved if row.intent_id == intent_id), None)

    def list_intents(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[SignalRecord]:
        return [
            row
            for row in self.saved
            if row.strategy_id == strategy_id
            and (signal_date is None or row.signal_date == signal_date)
            and (status is None or row.status == status)
        ]

    def update_intent_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        return False


def _target() -> TargetPortfolio:
    return TargetPortfolio(
        trade_date="2026-01-30",
        strategy_id="stock-selection",
        run_id="run-1",
        positions={InstrumentId(1): 0.3, InstrumentId(2): 0.2},
        cash_target=0.5,
    )


def test_publish_persists_stable_trade_intents_and_returns_package() -> None:
    port = _IntentPort(saved=[])
    publisher = SignalPackagePublisher(
        position_reader=_PositionReader(),
        intent_port=port,
    )

    package = publisher.publish(
        target=_target(),
        dataset_snapshot_ids={"stock_daily": "sha256:stock"},
        factor_ids=("quality_roe", "value_pe", "momentum_1m"),
        risk_flags=("lot_size_checked",),
        factor_values={1: {"quality_roe": 0.1}, 2: {"quality_roe": 0.2}},
    )

    assert package.run_id == "run-1"
    assert package.strategy_id == "stock-selection"
    assert package.signal_date == "2026-01-30"
    assert package.dataset_snapshot_ids == {"stock_daily": "sha256:stock"}
    assert package.factor_ids == ("quality_roe", "value_pe", "momentum_1m")
    assert package.risk_flags == ("lot_size_checked",)
    assert package.checksum.startswith("sha256:")
    assert [row.instrument_id for row in port.saved] == [1, 2]
    assert all(row.intent_id.startswith("sig-run-1-2026-01-30-") for row in port.saved)


def test_same_inputs_produce_same_checksum() -> None:
    first = SignalPackagePublisher(
        position_reader=_PositionReader(),
        intent_port=_IntentPort(saved=[]),
    ).publish(target=_target())
    second = SignalPackagePublisher(
        position_reader=_PositionReader(),
        intent_port=_IntentPort(saved=[]),
    ).publish(target=_target())

    assert first.checksum == second.checksum
