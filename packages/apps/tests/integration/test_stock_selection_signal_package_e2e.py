"""Stock-selection signal package E2E."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_execution.models import SignalRecord
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.models import TargetPortfolio

STRATEGY_ID = "stock-selection-golden"
SIGNAL_DATE = "2026-02-27"


class _FlatPositionReader:
    def get_current_positions(self, strategy_id: str) -> dict[int, float]:
        assert strategy_id == STRATEGY_ID
        return {}


@dataclass
class _IntentPort:
    rows: list[SignalRecord]

    def save_intent(self, record: SignalRecord) -> None:
        self.rows.append(record)

    def get_intent(self, intent_id: str) -> SignalRecord | None:
        return next((row for row in self.rows if row.intent_id == intent_id), None)

    def list_intents(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[SignalRecord]:
        return [
            row
            for row in self.rows
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


@pytest.mark.integration
def test_stock_selection_target_publishes_readable_manual_trade_signals() -> None:
    target = TargetPortfolio(
        trade_date=SIGNAL_DATE,
        strategy_id=STRATEGY_ID,
        run_id=STRATEGY_ID,
        positions={
            InstrumentId(5): 1 / 3,
            InstrumentId(4): 1 / 3,
            InstrumentId(3): 1 / 3,
        },
        cash_target=0.0,
    )
    port = _IntentPort(rows=[])
    publisher = SignalPackagePublisher(
        position_reader=_FlatPositionReader(),
        intent_port=port,
    )

    package = publisher.publish(
        target=target,
        dataset_snapshot_ids={
            "stock_daily": "sha256:synthetic-stock",
            "balance_sheet": "sha256:synthetic-balance",
            "income_statement": "sha256:synthetic-income",
        },
        factor_ids=("quality_roe", "value_pe", "momentum_1m"),
        risk_flags=("buying_power_checked", "lot_size_checked"),
    )

    assert package.strategy_id == STRATEGY_ID
    assert package.signal_date == SIGNAL_DATE
    assert package.checksum.startswith("sha256:")
    assert len(package.intents) == 3
    assert len(port.list_intents(strategy_id=STRATEGY_ID, signal_date=SIGNAL_DATE)) == 3
    assert {row.instrument_id for row in port.rows} == {3, 4, 5}
    assert all(row.direction == "buy" for row in port.rows)
