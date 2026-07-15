"""Signal package publisher unit tests."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ditto_application.processes.execution.ports import PositionReader
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_execution.models import SignalRecord
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)


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
        for index, row in enumerate(self.saved):
            if row.intent_id == intent_id and row.status in expected_current:
                self.saved[index] = replace(row, status=status)
                return True
        return False


@dataclass
class _ArtifactStore:
    rows: list[StrategyArtifactRecord]

    def get(self, artifact_id: str) -> StrategyArtifactRecord | None:
        return next((row for row in self.rows if row.artifact_id == artifact_id), None)

    def list_all(self) -> list[StrategyArtifactRecord]:
        return list(self.rows)

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        return [row for row in self.rows if row.strategy_id == strategy_id]

    def save(self, record: StrategyArtifactRecord) -> None:
        self.rows.append(record)

    def update_status(self, artifact_id: str, status: str) -> bool:
        for index, row in enumerate(self.rows):
            if row.artifact_id == artifact_id:
                self.rows[index] = replace(row, status=status)
                return True
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


def test_same_batch_retry_persists_one_artifact_and_no_duplicate_intents() -> None:
    intents = _IntentPort(saved=[])
    artifacts = _ArtifactStore(rows=[])
    publisher = SignalPackagePublisher(
        position_reader=_PositionReader(),
        intent_port=intents,
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )

    first = publisher.publish(target=_target())
    second = publisher.publish(target=_target())

    assert first.artifact_id == second.artifact_id
    assert len(artifacts.rows) == 1
    assert len(intents.saved) == 2
    assert artifacts.rows[0].artifact_type == ArtifactKind.SIGNAL_PACKAGE
    assert artifacts.rows[0].metadata["schema_version"] == "1.0"


def test_zero_intents_still_persists_no_rebalance_package() -> None:
    artifacts = _ArtifactStore(rows=[])
    target = replace(_target(), positions={InstrumentId(1): 0.1})
    package = SignalPackagePublisher(
        position_reader=_PositionReader(),
        intent_port=_IntentPort(saved=[]),
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    ).publish(target=target)

    assert package.intents == ()
    assert package.no_rebalance is True
    assert package.outcome == "no_rebalance"
    assert artifacts.rows[0].metadata["no_rebalance"] is True


def test_changed_checksum_with_non_pending_intent_fails_closed() -> None:
    intents = _IntentPort(saved=[])
    artifacts = _ArtifactStore(rows=[])
    publisher = SignalPackagePublisher(
        position_reader=_PositionReader(),
        intent_port=intents,
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )
    publisher.publish(target=_target())
    intents.saved[0] = replace(intents.saved[0], status="filled")

    conflict = publisher.publish(
        target=_target(),
        risk_flags=("changed",),
    )

    assert conflict.outcome == "rerun_conflict"
    assert len(artifacts.rows) == 1
    assert len(intents.saved) == 2
