"""Stock-selection signal package E2E."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingContext,
    ManualSizingService,
)
from ditto_application.processes.execution.signal_package import (
    SignalPackagePublisher,
    SignalPackagePublishRequest,
)
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
from ditto_execution.models import FillAdjustmentRecord, FillRecord, SignalRecord
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLitePool
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)

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


class _FillPort:
    @contextmanager
    def ledger_transaction(self) -> Iterator[None]:
        yield

    def save_fill(self, record: FillRecord) -> bool:
        raise AssertionError("test does not persist fills")

    def get_fill(self, fill_id: str) -> FillRecord | None:
        return None

    def list_fills(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[FillRecord]:
        return []

    def list_effective_fills(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[FillRecord]:
        return []

    def get_fill_adjustment(
        self,
        adjustment_id: str,
    ) -> FillAdjustmentRecord | None:
        return None

    def list_fill_adjustments(
        self,
        strategy_id: str,
        *,
        fill_id: str | None = None,
        intent_id: str | None = None,
    ) -> list[FillAdjustmentRecord]:
        return []

    def apply_fill_adjustment(
        self,
        record: FillAdjustmentRecord,
        *,
        replacement_fill: FillRecord | None = None,
    ) -> bool:
        raise AssertionError("test does not persist fill adjustments")


@pytest.fixture
def artifact_service(tmp_path: Path) -> Iterator[StrategyArtifactService]:
    pool = SQLitePool(str(tmp_path / "signal-package.db"))
    writer = SQLiteStrategyArtifactWriter(pool)
    writer.init_schema()
    yield StrategyArtifactService(
        reader=SQLiteStrategyArtifactReader(pool),
        writer=writer,
    )
    pool.close()


@pytest.mark.integration
def test_stock_selection_target_publishes_readable_manual_trade_signals(
    artifact_service: StrategyArtifactService,
) -> None:
    target = TargetPortfolio(
        trade_date=SIGNAL_DATE,
        strategy_id=STRATEGY_ID,
        run_id=f"eod-{SIGNAL_DATE}-{STRATEGY_ID}-1",
        positions={
            InstrumentId(5): 1 / 3,
            InstrumentId(4): 1 / 3,
            InstrumentId(3): 1 / 3,
        },
        cash_target=0.0,
    )
    port = _IntentPort(rows=[])
    publisher = SignalPackagePublisher(
        snapshot_process=SignalSnapshotProcess(
            position_reader=_FlatPositionReader(),
            sizing_service=ManualSizingService(),
        ),
        intent_port=port,
        fill_port=_FillPort(),
        date_resolver=AShareTradeDateResolver(trading_days=(SIGNAL_DATE, "2026-03-02")),
        artifact_service=artifact_service,
    )

    package = publisher.publish(
        SignalPackagePublishRequest(
            target=target,
            strategy_version="1",
            account_id="paper-a",
            sleeve_id=f"manual-paper-a-{STRATEGY_ID}",
            sizing_contexts={
                instrument_id: ManualSizingContext(
                    nav=30_000.0,
                    current_quantity=0,
                    available_quantity=0,
                    cash_available=30_000.0,
                    reference_price=10.0,
                    current_weight=0.0,
                )
                for instrument_id in (3, 4, 5)
            },
            decision_date=SIGNAL_DATE,
            intended_trade_date="2026-03-02",
            required_datasets=(
                "stock_daily",
                "balance_sheet",
                "income_statement",
            ),
            required_dataset_states=(
                {
                    "dataset": "stock_daily",
                    "status": "ready",
                    "snapshot_id": "sha256:synthetic-stock",
                    "reason": "",
                },
                {
                    "dataset": "balance_sheet",
                    "status": "ready",
                    "snapshot_id": "sha256:synthetic-balance",
                    "reason": "",
                },
                {
                    "dataset": "income_statement",
                    "status": "ready",
                    "snapshot_id": "sha256:synthetic-income",
                    "reason": "",
                },
            ),
            dataset_snapshot_ids={
                "stock_daily": "sha256:synthetic-stock",
                "balance_sheet": "sha256:synthetic-balance",
                "income_statement": "sha256:synthetic-income",
            },
            factor_ids=("quality_roe", "value_pe", "momentum_1m"),
            factor_values={
                3: {"quality_roe": 0.8, "value_pe": -0.2, "momentum_1m": 0.4},
                4: {"quality_roe": 0.6, "value_pe": -0.4, "momentum_1m": 0.3},
                5: {"quality_roe": 0.7, "value_pe": -0.1, "momentum_1m": 0.5},
            },
            industry_by_instrument={
                3: "consumer",
                4: "technology",
                5: "healthcare",
            },
            risk_flags=("buying_power_checked", "lot_size_checked"),
        )
    )

    assert package.strategy_id == STRATEGY_ID
    assert package.signal_date == SIGNAL_DATE
    assert package.checksum.startswith("sha256:")
    assert len(package.intents) == 3
    assert len(port.list_intents(strategy_id=STRATEGY_ID, signal_date=SIGNAL_DATE)) == 3
    assert {row.instrument_id for row in port.rows} == {3, 4, 5}
    assert all(row.direction == "buy" for row in port.rows)
    # 三笔最低佣金必须共享同一现金池；第三笔只能建议 900 股。
    quantities = tuple(row.quantity for row in port.rows)
    assert None not in quantities
    assert sorted(quantity for quantity in quantities if quantity is not None) == [
        900,
        1000,
        1000,
    ]

    assert set(package.selection_reasons) == {3, 4, 5}
    for instrument_id, reason in package.selection_reasons.items():
        assert reason.target_weight == pytest.approx(1 / 3)
        assert reason.composite_score is not None
        assert reason.rank in {1, 2, 3}
        assert reason.positive_contributors
        assert reason.negative_contributors
        assert (
            reason.industry
            == {
                3: "consumer",
                4: "technology",
                5: "healthcare",
            }[instrument_id]
        )
