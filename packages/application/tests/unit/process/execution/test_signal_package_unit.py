"""Signal package publisher unit tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from inspect import Parameter, signature
from typing import cast

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.execution_dto import TradeIntent
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingContext,
    ManualSizingService,
)
from ditto_application.processes.execution.ports import PositionReader
from ditto_application.processes.execution.signal_package import (
    SignalPackage,
    SignalPackagePublisher,
    SignalPackagePublishRequest,
)
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
from ditto_execution.models import FillRecord, SignalRecord
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
class _SnapshotProcess:
    intents: list[TradeIntent]

    def generate_intents(self, **kwargs: object) -> list[TradeIntent]:
        return list(self.intents)


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
class _FillPort:
    rows: list[FillRecord]

    def save_fill(self, record: FillRecord) -> None:
        self.rows.append(record)

    def list_fills(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[FillRecord]:
        return [
            row
            for row in self.rows
            if row.strategy_id == strategy_id
            and (trade_date is None or row.trade_date == trade_date)
            and (intent_id is None or row.intent_id == intent_id)
            and (end_date is None or row.trade_date <= end_date)
        ]


@dataclass
class _ArtifactStore:
    rows: list[StrategyArtifactRecord]

    def get(self, artifact_id: str) -> StrategyArtifactRecord | None:
        return next((row for row in self.rows if row.artifact_id == artifact_id), None)

    def list_all(self) -> list[StrategyArtifactRecord]:
        return list(self.rows)

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        return [row for row in self.rows if row.strategy_id == strategy_id]

    def save(self, record: StrategyArtifactRecord) -> bool:
        if self.get(record.artifact_id) is not None:
            return False
        self.rows.append(record)
        return True

    def update_status(
        self,
        artifact_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...] | None = None,
    ) -> bool:
        for index, row in enumerate(self.rows):
            if row.artifact_id == artifact_id and (
                expected_current is None or row.status in expected_current
            ):
                self.rows[index] = replace(row, status=status)
                return True
        return False

    def claim_replacement(
        self,
        candidate_artifact_id: str,
        replaced_artifact_id: str,
    ) -> bool:
        candidate = self.get(candidate_artifact_id)
        replaced = self.get(replaced_artifact_id)
        if candidate is None or replaced is None:
            return False
        if candidate.status != "staged" or replaced.status != "active":
            return False
        if any(
            row.status == "replacing"
            and row.strategy_id == candidate.strategy_id
            and row.run_id == candidate.run_id
            and row.artifact_type == candidate.artifact_type
            for row in self.rows
        ):
            return False
        return self.update_status(
            candidate_artifact_id,
            "replacing",
            expected_current=("staged",),
        )

    def activate_candidate(
        self,
        candidate_artifact_id: str,
        *,
        replaced_artifact_id: str | None = None,
    ) -> bool:
        candidate = self.get(candidate_artifact_id)
        if candidate is None:
            return False
        active = [
            row
            for row in self.rows
            if row.strategy_id == candidate.strategy_id
            and row.run_id == candidate.run_id
            and row.artifact_type == candidate.artifact_type
            and row.status == "active"
        ]
        if replaced_artifact_id is None:
            if active:
                return False
            expected_candidate = ("staged",)
        else:
            if [row.artifact_id for row in active] != [replaced_artifact_id]:
                return False
            expected_candidate = ("replacing",)
            if not self.update_status(
                replaced_artifact_id,
                "archived",
                expected_current=("active",),
            ):
                return False
        return self.update_status(
            candidate_artifact_id,
            "active",
            expected_current=expected_candidate,
        )


@dataclass
class _FailingActivationStore(_ArtifactStore):
    fail_once: bool = True

    def activate_candidate(
        self,
        candidate_artifact_id: str,
        *,
        replaced_artifact_id: str | None = None,
    ) -> bool:
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("injected activation failure")
        return super().activate_candidate(
            candidate_artifact_id,
            replaced_artifact_id=replaced_artifact_id,
        )


def _target(strategy_version: str = "7") -> TargetPortfolio:
    return TargetPortfolio(
        trade_date="2026-01-30",
        strategy_id="stock-selection",
        run_id=f"eod-2026-01-30-stock-selection-{strategy_version}",
        positions={InstrumentId(1): 0.3, InstrumentId(2): 0.2},
        cash_target=0.5,
    )


def _make_publisher(
    *,
    intent_port: _IntentPort | None = None,
    fill_port: _FillPort | None = None,
    artifact_service: StrategyArtifactService | None = None,
) -> SignalPackagePublisher:
    service = artifact_service
    if service is None:
        artifacts = _ArtifactStore(rows=[])
        service = StrategyArtifactService(artifacts, artifacts)
    return SignalPackagePublisher(
        snapshot_process=SignalSnapshotProcess(
            position_reader=_PositionReader(),
            sizing_service=ManualSizingService(),
        ),
        intent_port=intent_port or _IntentPort(saved=[]),
        fill_port=fill_port or _FillPort(rows=[]),
        date_resolver=AShareTradeDateResolver(
            trading_days=("2026-01-30", "2026-02-02")
        ),
        artifact_service=service,
    )


def _publish_package(
    publisher: SignalPackagePublisher,
    *,
    target: TargetPortfolio | None = None,
    strategy_version: str = "7",
    account_id: str = "paper-a",
    sleeve_id: str = "manual-paper-a-stock-selection",
    risk_flags: tuple[str, ...] = (),
    factor_values: dict[int, dict[str, float]] | None = None,
) -> SignalPackage:
    return publisher.publish(
        SignalPackagePublishRequest(
            target=target or _target(strategy_version),
            strategy_version=strategy_version,
            account_id=account_id,
            sleeve_id=sleeve_id,
            sizing_contexts={},
            decision_date="2026-01-30",
            intended_trade_date="2026-02-02",
            required_datasets=(),
            required_dataset_states=(),
            risk_flags=risk_flags,
            factor_values=factor_values or {},
        )
    )


def _publish_and_finalize(
    publisher: SignalPackagePublisher,
    **kwargs: object,
) -> SignalPackage:
    package = _publish_package(publisher, **kwargs)
    return publisher.finalize(package)


def test_publisher_requires_durable_artifact_service() -> None:
    parameter = signature(SignalPackagePublisher).parameters["artifact_service"]

    assert parameter.default is Parameter.empty


def test_publish_accepts_one_explicit_request_object() -> None:
    assert tuple(signature(SignalPackagePublisher.publish).parameters) == (
        "self",
        "request",
    )


def test_publish_persists_stable_trade_intents_and_returns_package() -> None:
    port = _IntentPort(saved=[])
    publisher = _make_publisher(intent_port=port)

    package = publisher.publish(
        SignalPackagePublishRequest(
            target=_target(),
            strategy_version="7",
            account_id="paper-a",
            sleeve_id="manual-paper-a-stock-selection",
            sizing_contexts={},
            decision_date="2026-01-30",
            intended_trade_date="2026-02-02",
            required_datasets=("stock_daily",),
            required_dataset_states=(),
            dataset_snapshot_ids={"stock_daily": "sha256:stock"},
            factor_ids=("quality_roe", "value_pe", "momentum_1m"),
            risk_flags=("lot_size_checked",),
            factor_values={1: {"quality_roe": 0.1}, 2: {"quality_roe": 0.2}},
        )
    )

    assert package.run_id == "eod-2026-01-30-stock-selection-7"
    assert package.strategy_id == "stock-selection"
    assert package.signal_date == "2026-01-30"
    assert package.dataset_snapshot_ids == {"stock_daily": "sha256:stock"}
    assert package.factor_ids == ("momentum_1m", "quality_roe", "value_pe")
    assert package.risk_flags == ("lot_size_checked",)
    assert package.checksum.startswith("sha256:")
    assert [row.instrument_id for row in port.saved] == [1, 2]
    assert all(
        row.intent_id.startswith("sig-eod-2026-01-30-stock-selection-7-2026-01-30-")
        for row in port.saved
    )


def test_publish_stages_package_until_explicit_finalize() -> None:
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )

    package = _publish_package(publisher)

    assert [row.status for row in artifacts.rows] == ["staged"]
    assert not [row for row in artifacts.rows if row.status == "active"]

    finalized = publisher.finalize(package)

    assert finalized == package
    assert [row.status for row in artifacts.rows] == ["active"]


def test_changed_input_never_reuses_an_existing_staged_candidate() -> None:
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )

    staged = _publish_package(publisher)
    conflict = _publish_package(publisher, risk_flags=("changed",))

    assert conflict.outcome == "rerun_conflict"
    assert conflict.artifact_id != staged.artifact_id
    assert [row.status for row in artifacts.rows] == [
        "staged",
        "archived",
        "conflict",
    ]
    publisher.finalize(conflict)
    assert not [row for row in artifacts.rows if row.status == "active"]


def test_publish_uses_injected_sizing_process_and_persists_trade_dates() -> None:
    intents = _IntentPort(saved=[])
    artifacts = _ArtifactStore(rows=[])
    snapshot = SignalSnapshotProcess(
        position_reader=_PositionReader(),
        sizing_service=ManualSizingService(),
    )
    publisher = SignalPackagePublisher(
        snapshot_process=snapshot,
        intent_port=intents,
        fill_port=_FillPort(rows=[]),
        date_resolver=AShareTradeDateResolver(
            trading_days=("2026-01-30", "2026-02-02")
        ),
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )

    package = publisher.publish(
        SignalPackagePublishRequest(
            target=_target(),
            strategy_version="7",
            account_id="paper-a",
            sleeve_id="manual-paper-a-stock-selection",
            sizing_contexts={
                1: ManualSizingContext(
                    nav=10_000.0,
                    current_quantity=100,
                    available_quantity=100,
                    cash_available=5_000.0,
                    reference_price=10.0,
                ),
                2: ManualSizingContext(
                    nav=10_000.0,
                    current_quantity=0,
                    available_quantity=0,
                    cash_available=5_000.0,
                    reference_price=10.0,
                ),
            },
            decision_date="2026-01-30",
            intended_trade_date="2026-02-02",
            required_datasets=("stock_daily", "balance_sheet"),
            required_dataset_states=(
                {
                    "dataset": "stock_daily",
                    "status": "ready",
                    "snapshot_id": "sha256:stock",
                    "reason": "",
                },
                {
                    "dataset": "balance_sheet",
                    "status": "ready",
                    "snapshot_id": "sha256:balance",
                    "reason": "",
                },
            ),
        )
    )

    assert [intent.quantity for intent in package.intents] == [200, 200]
    assert [intent.quantity for intent in intents.saved] == [200, 200]
    assert artifacts.rows[0].metadata["account_id"] == "paper-a"
    assert artifacts.rows[0].metadata["strategy_version"] == "7"
    assert artifacts.rows[0].metadata["sleeve_id"] == "manual-paper-a-stock-selection"
    assert artifacts.rows[0].metadata["decision_date"] == "2026-01-30"
    assert artifacts.rows[0].metadata["intended_trade_date"] == "2026-02-02"
    assert artifacts.rows[0].metadata["required_datasets"] == [
        "balance_sheet",
        "stock_daily",
    ]
    assert artifacts.rows[0].metadata["required_dataset_states"] == [
        {
            "dataset": "balance_sheet",
            "reason": "",
            "snapshot_id": "sha256:balance",
            "status": "ready",
        },
        {
            "dataset": "stock_daily",
            "reason": "",
            "snapshot_id": "sha256:stock",
            "status": "ready",
        },
    ]
    persisted_intents = cast(
        "list[dict[str, object]]",
        artifacts.rows[0].metadata["intents"],
    )
    assert {
        key: persisted_intents[0][key]
        for key in (
            "raw_quantity",
            "rounded_quantity",
            "lot_size",
            "reference_price",
            "cash_impact",
            "sizing_reason",
            "sizing_readiness",
        )
    } == {
        "raw_quantity": 200,
        "rounded_quantity": 200,
        "lot_size": 100,
        "reference_price": 10.0,
        "cash_impact": -2_000.0,
        "sizing_reason": "exact_board_lot",
        "sizing_readiness": "ready",
    }


def test_package_persists_blocked_sizing_evidence_without_reference_price() -> None:
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )

    publisher.publish(
        SignalPackagePublishRequest(
            target=replace(_target(), positions={InstrumentId(1): 0.3}),
            strategy_version="7",
            account_id="paper-a",
            sleeve_id="manual-paper-a-stock-selection",
            sizing_contexts={
                1: ManualSizingContext(
                    nav=10_000.0,
                    current_quantity=0,
                    available_quantity=0,
                    cash_available=10_000.0,
                    reference_price=None,
                    current_weight=0.0,
                )
            },
            decision_date="2026-01-30",
            intended_trade_date="2026-02-02",
            required_datasets=(),
            required_dataset_states=(),
        )
    )

    persisted_intents = cast(
        "list[dict[str, object]]",
        artifacts.rows[0].metadata["intents"],
    )
    evidence = persisted_intents[0]
    assert evidence["quantity"] == 0
    assert evidence["raw_quantity"] == 0
    assert evidence["rounded_quantity"] == 0
    assert evidence["lot_size"] == 100
    assert evidence["reference_price"] is None
    assert evidence["cash_impact"] == 0.0
    assert evidence["sizing_reason"] == "missing_reference_price"
    assert evidence["sizing_readiness"] == "blocked"


def test_same_inputs_produce_same_checksum() -> None:
    first = _publish_package(_make_publisher())
    second = _publish_package(_make_publisher())

    assert first.checksum == second.checksum


def test_account_and_sleeve_identity_participate_in_checksum() -> None:
    first = _publish_package(_make_publisher())
    other = _publish_package(
        _make_publisher(),
        account_id="paper-b",
        sleeve_id="manual-paper-b-stock-selection",
    )

    assert other.checksum != first.checksum


def test_strategy_version_participates_in_checksum() -> None:
    first = _publish_package(_make_publisher(), strategy_version="7")
    next_version = _publish_package(_make_publisher(), strategy_version="8")

    assert next_version.checksum != first.checksum


def test_cash_target_participates_in_checksum() -> None:
    first = _publish_package(_make_publisher())
    more_cash = _publish_package(
        _make_publisher(),
        target=replace(_target(), cash_target=0.6),
    )

    assert more_cash.checksum != first.checksum


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["target_weight", "cash_target"])
def test_publish_rejects_non_finite_target_numbers(
    field: str,
    value: float,
) -> None:
    target = (
        replace(_target(), positions={InstrumentId(1): value})
        if field == "target_weight"
        else replace(_target(), cash_target=value)
    )

    with pytest.raises(AppProcessError, match="finite"):
        _publish_package(_make_publisher(), target=target)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_publish_rejects_non_finite_factor_values(value: float) -> None:
    with pytest.raises(AppProcessError, match="finite"):
        _publish_package(
            _make_publisher(),
            factor_values={1: {"quality": value}},
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_publish_rejects_non_finite_intent_reference_price(value: float) -> None:
    artifacts = _ArtifactStore(rows=[])
    publisher = SignalPackagePublisher(
        snapshot_process=cast(
            SignalSnapshotProcess,
            _SnapshotProcess(
                [
                    TradeIntent(
                        intent_id="unstable",
                        strategy_id="stock-selection",
                        signal_date="2026-01-30",
                        instrument_id=1,
                        direction="buy",
                        target_weight=0.3,
                        current_weight=0.1,
                        delta_weight=0.2,
                        reference_price=value,
                    )
                ]
            ),
        ),
        intent_port=_IntentPort(saved=[]),
        fill_port=_FillPort(rows=[]),
        date_resolver=AShareTradeDateResolver(
            trading_days=("2026-01-30", "2026-02-02")
        ),
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )

    with pytest.raises(AppProcessError, match="finite"):
        _publish_package(publisher)

    assert artifacts.rows == []


def test_checksum_is_independent_of_snapshot_intent_iteration_order() -> None:
    first_intent = TradeIntent(
        intent_id="random-a",
        strategy_id="stock-selection",
        signal_date="2026-01-30",
        instrument_id=1,
        direction="buy",
        target_weight=0.3,
        current_weight=0.1,
        delta_weight=0.2,
        quantity=200,
    )
    second_intent = replace(
        first_intent,
        intent_id="random-b",
        instrument_id=2,
        target_weight=0.2,
        current_weight=0.0,
    )
    resolver = AShareTradeDateResolver(trading_days=("2026-01-30", "2026-02-02"))

    def _publish(intents: list[TradeIntent]) -> SignalPackage:
        artifacts = _ArtifactStore(rows=[])
        return SignalPackagePublisher(
            snapshot_process=cast(
                SignalSnapshotProcess,
                _SnapshotProcess(intents),
            ),
            intent_port=_IntentPort(saved=[]),
            fill_port=_FillPort(rows=[]),
            date_resolver=resolver,
            artifact_service=StrategyArtifactService(artifacts, artifacts),
        ).publish(
            SignalPackagePublishRequest(
                target=_target(),
                strategy_version="7",
                account_id="paper-a",
                sleeve_id="manual-paper-a-stock-selection",
                sizing_contexts={},
                decision_date="2026-01-30",
                intended_trade_date="2026-02-02",
                required_datasets=(),
                required_dataset_states=(),
            )
        )

    forward = _publish([first_intent, second_intent])
    reverse = _publish([second_intent, first_intent])

    assert forward.checksum == reverse.checksum
    assert [intent.intent_id for intent in forward.intents] == [
        intent.intent_id for intent in reverse.intents
    ]


def test_checksum_and_retry_ignore_factor_and_risk_set_order() -> None:
    intents = _IntentPort(saved=[])
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        intent_port=intents,
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )

    def _publish(
        factor_ids: tuple[str, ...],
        risk_flags: tuple[str, ...],
    ) -> SignalPackage:
        return publisher.publish(
            SignalPackagePublishRequest(
                target=_target(),
                strategy_version="7",
                account_id="paper-a",
                sleeve_id="manual-paper-a-stock-selection",
                sizing_contexts={},
                decision_date="2026-01-30",
                intended_trade_date="2026-02-02",
                required_datasets=(),
                required_dataset_states=(),
                factor_ids=factor_ids,
                risk_flags=risk_flags,
                factor_values={1: {"quality": 0.2, "value": 0.4}},
            )
        )

    first = _publish(
        ("value", "quality", "value"),
        ("turnover_checked", "lot_size_checked", "turnover_checked"),
    )
    retry = _publish(
        ("quality", "value"),
        ("lot_size_checked", "turnover_checked"),
    )

    assert first.factor_ids == ("quality", "value")
    assert first.risk_flags == ("lot_size_checked", "turnover_checked")
    assert retry.checksum == first.checksum
    assert retry.artifact_id == first.artifact_id
    assert [intent.intent_id for intent in retry.intents] == [
        intent.intent_id for intent in first.intents
    ]
    assert len(artifacts.rows) == 1
    assert len(intents.saved) == 2


def test_same_batch_retry_persists_one_artifact_and_no_duplicate_intents() -> None:
    intents = _IntentPort(saved=[])
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        intent_port=intents,
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )

    first = _publish_package(publisher)
    second = _publish_package(publisher)

    assert first.artifact_id == second.artifact_id
    assert len(artifacts.rows) == 1
    assert len(intents.saved) == 2
    assert artifacts.rows[0].artifact_type == ArtifactKind.SIGNAL_PACKAGE
    assert artifacts.rows[0].metadata["schema_version"] == "1.0"


def test_zero_intents_still_persists_no_rebalance_package() -> None:
    artifacts = _ArtifactStore(rows=[])
    target = replace(_target(), positions={InstrumentId(1): 0.1})
    package = _publish_package(
        _make_publisher(
            intent_port=_IntentPort(saved=[]),
            artifact_service=StrategyArtifactService(artifacts, artifacts),
        ),
        target=target,
    )

    assert package.intents == ()
    assert package.no_rebalance is True
    assert package.outcome == "no_rebalance"
    assert artifacts.rows[0].metadata["no_rebalance"] is True


def test_changed_checksum_with_non_pending_intent_fails_closed() -> None:
    intents = _IntentPort(saved=[])
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        intent_port=intents,
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )
    active = _publish_and_finalize(publisher)
    intents.saved[0] = replace(intents.saved[0], status="filled")

    conflict = _publish_package(publisher, risk_flags=("changed",))

    assert conflict.outcome == "rerun_conflict"
    assert len(artifacts.rows) == 2
    assert artifacts.rows[0].status == "active"
    assert artifacts.rows[1].status == "conflict"
    assert artifacts.rows[1].artifact_id == conflict.artifact_id
    assert artifacts.rows[1].metadata["outcome"] == "rerun_conflict"
    assert artifacts.rows[1].metadata["conflicting_artifact_id"] == active.artifact_id
    assert len(intents.saved) == 2

    retry = _publish_package(publisher, risk_flags=("changed",))

    assert retry.artifact_id == conflict.artifact_id
    assert retry.outcome == "rerun_conflict"
    assert len(artifacts.rows) == 2


def test_changed_checksum_with_existing_fill_fails_closed_even_if_status_pending() -> (
    None
):
    class _RawHistoryFillPort(_FillPort):
        def list_effective_fills(
            self,
            *args: object,
            **kwargs: object,
        ) -> list[FillRecord]:
            del args, kwargs
            raise AssertionError("package replacement guard must read raw fills")

    intents = _IntentPort(saved=[])
    fills = _RawHistoryFillPort(rows=[])
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        intent_port=intents,
        fill_port=fills,
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )
    active = _publish_and_finalize(publisher)
    fills.rows.append(
        FillRecord(
            fill_id="fill-1",
            intent_id=intents.saved[0].intent_id,
            strategy_id="stock-selection",
            trade_date="2026-02-02",
            instrument_id=intents.saved[0].instrument_id,
            direction=intents.saved[0].direction,
            quantity=100,
            fill_price=10.0,
            fee=1.0,
        )
    )

    conflict = _publish_package(publisher, risk_flags=("changed",))

    assert conflict.outcome == "rerun_conflict"
    assert len(artifacts.rows) == 2
    assert artifacts.rows[0].artifact_id == active.artifact_id
    assert artifacts.rows[0].status == "active"
    assert artifacts.rows[1].artifact_id == conflict.artifact_id
    assert artifacts.rows[1].status == "conflict"
    assert artifacts.rows[1].metadata["outcome"] == "rerun_conflict"
    assert all(intent.status == "pending" for intent in intents.saved)


def test_publisher_rejects_noncanonical_batch_and_sleeve_identity() -> None:
    publisher = _make_publisher()

    with pytest.raises(AppProcessError, match="batch key"):
        _publish_package(publisher, target=replace(_target(), run_id="run-1"))

    with pytest.raises(AppProcessError, match="sleeve_id"):
        _publish_package(publisher, sleeve_id="manual-wrong")


def test_zero_intent_revision_does_not_supersede_other_version_intents() -> None:
    intents = _IntentPort(saved=[])
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        intent_port=intents,
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )
    version_8 = _publish_and_finalize(publisher, strategy_version="8")
    zero_target = replace(_target(), positions={InstrumentId(1): 0.1})
    first_version_7 = _publish_package(publisher, target=zero_target)
    publisher.finalize(first_version_7)

    replacement = _publish_package(
        publisher,
        target=zero_target,
        risk_flags=("changed",),
    )
    replacement = publisher.finalize(replacement)

    version_8_ids = {intent.intent_id for intent in version_8.intents}
    assert replacement.outcome == "no_rebalance"
    assert all(
        intent.status == "pending"
        for intent in intents.saved
        if intent.intent_id in version_8_ids
    )
    assert len([row for row in artifacts.rows if row.status == "active"]) == 2


def test_same_checksum_retry_fails_closed_for_multiple_active_artifacts() -> None:
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )
    first = _publish_and_finalize(publisher)
    artifacts.rows[0] = replace(artifacts.rows[0], created_at="2026-01-30T20:00:00Z")
    newer = replace(
        artifacts.rows[0],
        artifact_id=f"{first.artifact_id}-newer",
        created_at="2026-01-30T21:00:00Z",
    )
    artifacts.rows.append(newer)

    retry = _publish_package(publisher)

    assert retry.outcome == "rerun_conflict"
    assert retry.artifact_id not in {first.artifact_id, newer.artifact_id}
    assert [row.status for row in artifacts.rows[:2]] == ["active", "active"]


def test_activation_failure_keeps_old_active_and_retry_completes_replacement() -> None:
    intents = _IntentPort(saved=[])
    artifacts = _FailingActivationStore(rows=[])
    artifacts.fail_once = False
    publisher = _make_publisher(
        intent_port=intents,
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )
    active = _publish_and_finalize(publisher)
    artifacts.fail_once = True
    staged = _publish_package(publisher, risk_flags=("changed",))

    assert [row.artifact_id for row in artifacts.rows if row.status == "active"] == [
        active.artifact_id
    ]
    assert (
        next(
            row for row in artifacts.rows if row.artifact_id == staged.artifact_id
        ).status
        == "staged"
    )

    with pytest.raises(RuntimeError, match="injected activation failure"):
        publisher.finalize(staged)

    assert [row.artifact_id for row in artifacts.rows if row.status == "active"] == [
        active.artifact_id
    ]

    replacement = publisher.find_staged(
        strategy_id="stock-selection",
        run_id="eod-2026-01-30-stock-selection-7",
        signal_date="2026-01-30",
    )
    assert replacement is not None
    replacement = publisher.finalize(replacement)

    assert replacement.outcome == "completed"
    assert [row.artifact_id for row in artifacts.rows if row.status == "active"] == [
        replacement.artifact_id
    ]
    assert (
        next(
            row for row in artifacts.rows if row.artifact_id == active.artifact_id
        ).status
        == "archived"
    )
    old_ids = {intent.intent_id for intent in active.intents}
    assert all(
        intent.status == "superseded"
        for intent in intents.saved
        if intent.intent_id in old_ids
    )


def test_retry_fails_closed_when_active_artifact_metadata_is_inconsistent() -> None:
    intents = _IntentPort(saved=[])
    artifacts = _ArtifactStore(rows=[])
    publisher = _make_publisher(
        intent_port=intents,
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )
    active = _publish_and_finalize(publisher)
    artifacts.rows[0] = replace(
        artifacts.rows[0],
        metadata={**artifacts.rows[0].metadata, "account_id": "tampered"},
    )

    conflict = _publish_package(publisher)

    assert conflict.outcome == "rerun_conflict"
    assert conflict.artifact_id != active.artifact_id
    assert len(intents.saved) == 2
    assert len(artifacts.rows) == 2
    assert artifacts.rows[1].status == "conflict"
    assert artifacts.rows[1].metadata["conflicting_artifact_id"] == active.artifact_id
    assert artifacts.rows[1].metadata["conflict_reason"] == "CHECKSUM_MISMATCH"
