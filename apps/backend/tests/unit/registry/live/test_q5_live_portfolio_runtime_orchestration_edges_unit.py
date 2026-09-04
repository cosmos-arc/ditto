"""State, recovery, and evidence edges for the Q5 portfolio runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import TypeVar, cast

import orjson
import polars as pl
import pytest
from ditto_application.commands.account import (
    AccountBaselineResult,
    ImportAccountBaselineCommand,
    ImportAccountBaselineHandler,
)
from ditto_application.processes.execution.eod_coordinator import (
    EodStrategyOutcome,
    EodStrategyRequest,
)
from ditto_application.processes.execution.signal_package import (
    SignalPackage,
    SignalPackagePublisher,
)
from ditto_application.processes.execution.strategy_run_process import (
    StrategyFacade,
    StrategyRunMode,
    StrategyRunResult,
    StrategyRunServiceConfig,
)
from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.daily_decision import DailyDecisionQueryFacade
from ditto_application.queries.portfolio_comparison import GetPortfolioComparisonQuery
from ditto_application.queries.source import SourceDataPort
from ditto_apps.operations.q4_live_account_acceptance import canonical_hash
from ditto_apps.operations.q5_live_portfolio_acceptance import (
    ApprovedLivePortfolioAcceptance,
)
from ditto_apps.registry.live import q5_live_portfolio_acceptance_runtime as runtime
from ditto_backtest.data_feed import Slice
from ditto_data.catalog.provider_payload import ProviderPayloadWriter
from ditto_data.catalog.source_snapshot import ProviderSnapshotWriter
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

_T = TypeVar("_T")
_OBSERVED_AT = datetime(2026, 9, 2, 8, tzinfo=UTC)


def _provider_row() -> dict[str, object]:
    return {
        "instrument_id": 101,
        "source_ticker": "510300.SH",
        "trade_date": "2026-09-02",
        "knowledge_date": "2026-09-02",
        "open": 4.0,
        "high": 4.2,
        "low": 3.9,
        "close": 4.1,
        "pre_close": 4.0,
        "volume": 1_000.0,
        "amount": 4_100.0,
        "pct_change": 2.5,
    }


def _approved(tmp_path: Path) -> ApprovedLivePortfolioAcceptance:
    return ApprovedLivePortfolioAcceptance(
        request_hash="a" * 64,
        data_root=(tmp_path / "state").resolve(),
        trading_database=(tmp_path / "trading.sqlite").resolve(),
        evidence_root=(tmp_path / "evidence").resolve(),
        observed_at=_OBSERVED_AT,
        signal_date="2026-09-02",
        intended_trade_date="2026-09-03",
        provider_rows=(_provider_row(),),
        raw_provider_row_count=1,
        provider_snapshot_id="snapshot-approved",
        provider_payload_checksum="b" * 64,
        paper_snapshot_alias="snapshot-paper",
        target_positions={101: 0.6},
        cash_target=0.4,
        factor_values={101: {"signal_value": 0.025}},
        strategy_spec_hash="c" * 64,
        strategy_universe="csi300",
        q3_evidence_path=(tmp_path / "q3.json").resolve(),
        account_evidence_path=(tmp_path / "account.json").resolve(),
    )


def _strategy_result(*, weight: float = 0.6) -> StrategyRunResult:
    return StrategyRunResult(
        run_id="strategy-run",
        trade_date="2026-09-02",
        strategy_id="seed_etf_industry_rotation",
        target=TargetPortfolio(
            trade_date="2026-09-02",
            strategy_id="seed_etf_industry_rotation",
            run_id="strategy-run",
            positions={InstrumentId(101): weight},
            cash_target=0.4,
        ),
        mode=StrategyRunMode.RECOMMENDATION,
        factor_ids=("signal_value",),
        factor_values={101: {"signal_value": 0.025}},
        risk_flags=(),
    )


class _Container:
    def __init__(self, services: Mapping[type[object], object]) -> None:
        self.services = services
        self.closed = False

    def get(self, dependency_type: type[_T]) -> _T:
        return cast("_T", self.services[dependency_type])

    def close(self) -> None:
        self.closed = True


class _Facade:
    def __init__(self, result: StrategyRunResult) -> None:
        self.result = result
        self.calls: list[tuple[StrategyRunServiceConfig, str, Slice, int]] = []

    def run_strategy_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        trade_date: str,
        slice_: Slice,
        version: int,
    ) -> StrategyRunResult:
        self.calls.append((config, trade_date, slice_, version))
        return self.result


def test_strategy_projection_binds_sorted_payload_and_catalog_identity(
    tmp_path: Path,
) -> None:
    approved = _approved(tmp_path)
    facade = _Facade(_strategy_result())

    result = runtime._run_strategy(
        cast("StrategyFacade", facade),
        approved,
        mode=StrategyRunMode.RESEARCH,
        run_id="preview-run",
    )

    assert result is facade.result
    config, trade_date, slice_, version = facade.calls[0]
    assert config == StrategyRunServiceConfig(
        strategy_id="seed_etf_industry_rotation",
        strategy_version="1",
        run_id="preview-run",
        mode=StrategyRunMode.RESEARCH,
        manage_run_lifecycle=False,
    )
    assert trade_date == "2026-09-02"
    assert version == 1
    assert slice_.trade_date == "2026-09-02"
    assert slice_.source_snapshot_ids == {InstrumentId(101): "snapshot-approved"}
    assert runtime._result_payload(result) == runtime._expected_payload(approved)


def _position(
    *,
    quantity: Decimal = Decimal("10"),
    available_quantity: Decimal = Decimal("8"),
) -> object:
    return SimpleNamespace(
        instrument_id=InstrumentId(101),
        quantity=quantity,
        available_quantity=available_quantity,
        average_cost=Decimal("3.50"),
        market_value=Decimal("41"),
        unrealized_pnl=Decimal("6"),
        realized_pnl=Decimal("2"),
        total_fees=Decimal("0.5"),
    )


def _manual_snapshot(
    *,
    valuation_complete: bool = True,
    positions: tuple[object, ...] | None = None,
) -> object:
    return SimpleNamespace(
        valuation_complete=valuation_complete,
        positions=(_position(),) if positions is None else positions,
        cash=SimpleNamespace(
            available=Decimal("59"),
            settled=Decimal("57"),
            frozen=Decimal("2"),
        ),
        total_value=Decimal("100"),
    )


class _BaselineHandler:
    def __init__(self, result: AccountBaselineResult) -> None:
        self.result = result
        self.commands: list[ImportAccountBaselineCommand] = []

    def handle(self, command: ImportAccountBaselineCommand) -> AccountBaselineResult:
        self.commands.append(command)
        return self.result


def _baseline_container(
    snapshot: object,
    *,
    persisted_snapshot_id: str | None = "baseline-1",
) -> tuple[_Container, _BaselineHandler]:
    result = AccountBaselineResult(
        snapshot_id="baseline-1",
        sleeve_id="manual-sleeve",
        status="created",
    )
    handler = _BaselineHandler(result)
    persisted = (
        None
        if persisted_snapshot_id is None
        else SimpleNamespace(account=SimpleNamespace(snapshot_id=persisted_snapshot_id))
    )
    return (
        _Container(
            {
                AccountLedgerQuery: SimpleNamespace(
                    get_manual=lambda **_kwargs: SimpleNamespace(snapshot=snapshot)
                ),
                ImportAccountBaselineHandler: handler,
                AccountBaselineQuery: SimpleNamespace(
                    get_latest=lambda **_kwargs: persisted
                ),
            }
        ),
        handler,
    )


def test_manual_baseline_rebuilds_an_exact_integral_snapshot(tmp_path: Path) -> None:
    approved = _approved(tmp_path)
    snapshot = _manual_snapshot()
    container, handler = _baseline_container(snapshot)

    rebuilt_snapshot, result = runtime._import_manual_baseline(
        cast("runtime._Container", container), approved
    )

    assert rebuilt_snapshot is snapshot
    assert result.snapshot_id == "baseline-1"
    assert handler.commands == [
        ImportAccountBaselineCommand(
            account_id="manual-q4-owner-acceptance",
            strategy_id="seed_etf_industry_rotation",
            snapshot_date="2026-09-02",
            cash_available=59.0,
            cash_settled=57.0,
            cash_frozen=2.0,
            total_value=100.0,
            nav=1.0,
            positions=(
                runtime.PositionBaselineInput(
                    instrument_id=101,
                    quantity=10,
                    available_quantity=8,
                    average_cost=3.5,
                    market_value=41.0,
                    unrealized_pnl=6.0,
                    realized_pnl=2.0,
                    total_fees=0.5,
                ),
            ),
        )
    ]


@pytest.mark.parametrize(
    ("snapshot", "persisted_snapshot_id", "message"),
    [
        (_manual_snapshot(valuation_complete=False), "baseline-1", "valuation"),
        (
            _manual_snapshot(positions=(_position(quantity=Decimal("10.5")),)),
            "baseline-1",
            "not integral",
        ),
        (
            _manual_snapshot(positions=(_position(available_quantity=Decimal("8.5")),)),
            "baseline-1",
            "not integral",
        ),
        (_manual_snapshot(), None, "not durably rebuilt"),
        (_manual_snapshot(), "baseline-drifted", "not durably rebuilt"),
    ],
)
def test_manual_baseline_fails_closed_for_invalid_or_non_durable_state(
    tmp_path: Path,
    snapshot: object,
    persisted_snapshot_id: str | None,
    message: str,
) -> None:
    container, _handler = _baseline_container(
        snapshot, persisted_snapshot_id=persisted_snapshot_id
    )

    with pytest.raises(ValueError, match=message):
        runtime._import_manual_baseline(
            cast("runtime._Container", container), _approved(tmp_path)
        )


class _Publisher:
    def __init__(self) -> None:
        self.publish_requests: list[object] = []
        self.staged_lookups: list[tuple[str, str, str]] = []
        self.finalized = 0
        self.package = cast(
            "SignalPackage",
            SimpleNamespace(artifact_id="signal-package", checksum="signal-checksum"),
        )

    def publish(self, request: object) -> SignalPackage:
        self.publish_requests.append(request)
        return self.package

    def finalize(self, package: SignalPackage) -> SignalPackage:
        assert package is self.package
        self.finalized += 1
        return package

    def find_staged(
        self, *, strategy_id: str, run_id: str, signal_date: str
    ) -> SignalPackage:
        self.staged_lookups.append((strategy_id, run_id, signal_date))
        return self.package


class _ScriptedCoordinator:
    def __init__(self, scenario: str, callbacks: Mapping[str, object]) -> None:
        self.scenario = scenario
        self.callbacks = callbacks

    def run(
        self,
        *,
        signal_date: str,
        strategies: tuple[EodStrategyRequest, ...],
        dataset_states: Mapping[str, object],
    ) -> tuple[EodStrategyOutcome, ...]:
        request = strategies[0]
        assert signal_date == "2026-09-02"
        assert dataset_states["etf_daily"].snapshot_id == "snapshot-approved"
        run_strategy = cast(
            "Callable[[EodStrategyRequest, str, str], object]",
            self.callbacks["run_strategy"],
        )
        publish_signals = cast(
            "Callable[[object, Mapping[str, str]], SignalPackage]",
            self.callbacks["publish_signals"],
        )
        find_staged = cast(
            "Callable[[EodStrategyRequest, str, str], SignalPackage | None]",
            self.callbacks["find_staged_signals"],
        )
        finalize = cast(
            "Callable[[SignalPackage], SignalPackage]",
            self.callbacks["finalize_signals"],
        )
        batch_key = "eod-2026-09-02-seed_etf_industry_rotation-1"
        if self.scenario == "identity":
            wrong = EodStrategyRequest(
                strategy_id="wrong", strategy_version="1", required_datasets=()
            )
            run_strategy(wrong, signal_date, batch_key)
        if self.scenario in {"output", "target", "success"}:
            target = run_strategy(request, signal_date, batch_key)
            assert find_staged(request, signal_date, batch_key) is not None
            package = publish_signals(
                object() if self.scenario == "target" else target,
                {"etf_daily": "snapshot-approved"},
            )
            finalize(package)
        status = "failed" if self.scenario == "failed" else "completed"
        artifact_id = None if self.scenario == "missing-artifact" else "signal-package"
        return (
            EodStrategyOutcome(
                strategy_id=request.strategy_id,
                strategy_version=request.strategy_version,
                batch_key=batch_key,
                status=cast("object", status),
                required_dataset_states=(),
                artifact_id=artifact_id,
                checksum="signal-checksum",
                reason="scripted outcome",
            ),
        )


def _install_coordinator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    scenario: str,
) -> None:
    def factory(**callbacks: object) -> _ScriptedCoordinator:
        return _ScriptedCoordinator(scenario, callbacks)

    monkeypatch.setattr(runtime, "EodCoordinator", factory)


def _eod_container(
    *, result: StrategyRunResult
) -> tuple[_Container, _Publisher, _Facade]:
    publisher = _Publisher()
    facade = _Facade(result)
    return (
        _Container(
            {
                StrategyFacade: facade,
                SignalPackagePublisher: publisher,
                StrategyRunLifecycleStore: object(),
            }
        ),
        publisher,
        facade,
    )


def test_eod_composition_publishes_and_exposes_recovery_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_coordinator(monkeypatch, scenario="success")
    container, publisher, _facade = _eod_container(result=_strategy_result())

    outcome, result = runtime._execute_eod(
        cast("runtime._Container", container),
        _approved(tmp_path),
        sizing_contexts={},
    )

    assert outcome.status == "completed"
    assert result.target.positions == {InstrumentId(101): 0.6}
    assert publisher.staged_lookups == [
        (
            "seed_etf_industry_rotation",
            "eod-2026-09-02-seed_etf_industry_rotation-1",
            "2026-09-02",
        )
    ]
    assert len(publisher.publish_requests) == 1
    assert publisher.finalized == 1


@pytest.mark.parametrize(
    ("scenario", "weight", "message"),
    [
        ("identity", 0.6, "EOD strategy identity drifted"),
        ("output", 0.5, "strategy output drifted"),
        ("target", 0.6, "EOD target identity drifted"),
        ("failed", 0.6, "live EOD package did not complete"),
        ("missing-artifact", 0.6, "live EOD package did not complete"),
    ],
)
def test_eod_composition_fails_closed_for_identity_output_and_outcome_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    weight: float,
    message: str,
) -> None:
    _install_coordinator(monkeypatch, scenario=scenario)
    container, _publisher, _facade = _eod_container(
        result=_strategy_result(weight=weight)
    )

    with pytest.raises(ValueError, match=message):
        runtime._execute_eod(
            cast("runtime._Container", container),
            _approved(tmp_path),
            sizing_contexts={},
        )


class _Source:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    def fetch_etf_daily(self, **kwargs: object) -> pl.DataFrame:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return pl.DataFrame([_provider_row()])


def _install_approval(
    monkeypatch: pytest.MonkeyPatch,
    approved: ApprovedLivePortfolioAcceptance,
) -> None:
    def approve(
        _proposal: Mapping[str, object], *, approved_request_hash: str
    ) -> ApprovedLivePortfolioAcceptance:
        assert approved_request_hash == approved.request_hash
        return approved

    monkeypatch.setattr(runtime, "approved_live_portfolio_acceptance_request", approve)


def test_runtime_rejects_execution_before_observation_without_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = _approved(tmp_path)
    _install_approval(monkeypatch, approved)

    with pytest.raises(ValueError, match="execution precedes"):
        runtime.run_live_portfolio_acceptance(
            {},
            approved_request_hash=approved.request_hash,
            operator_id="operator",
            executed_at=datetime(2026, 9, 2, 7, 59, tzinfo=UTC),
            source=_Source(),
            container_factory=cast(
                "Callable[[], runtime._Container]",
                lambda: pytest.fail("container must not open"),
            ),
        )


def test_owned_source_container_closes_when_provider_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = _approved(tmp_path)
    _install_approval(monkeypatch, approved)
    source = _Source(failure=RuntimeError("provider unavailable"))
    source_container = _Container({SourceDataPort: source})
    preload_calls: list[None] = []
    monkeypatch.setattr(
        runtime,
        "preload_runtime_secrets",
        lambda: preload_calls.append(None),
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        runtime.run_live_portfolio_acceptance(
            {},
            approved_request_hash=approved.request_hash,
            operator_id="operator",
            executed_at=_OBSERVED_AT,
            container_factory=cast(
                "Callable[[], runtime._Container]", lambda: source_container
            ),
        )

    assert preload_calls == [None]
    assert source.calls == [{"trade_date": "2026-09-02"}]
    assert source_container.closed


def test_runtime_rejects_unapproved_trading_store_before_container_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = _approved(tmp_path)
    _install_approval(monkeypatch, approved)
    monkeypatch.setattr(runtime, "state_root_matches", lambda _path: True)
    monkeypatch.setenv("DITTO_TRADING_SQLITE_PATH", str(tmp_path / "unapproved.sqlite"))

    with pytest.raises(ValueError, match="approved store"):
        runtime.run_live_portfolio_acceptance(
            {},
            approved_request_hash=approved.request_hash,
            operator_id="operator",
            executed_at=_OBSERVED_AT,
            source=_Source(),
            container_factory=cast(
                "Callable[[], runtime._Container]",
                lambda: pytest.fail("container must not open"),
            ),
        )


@dataclass(frozen=True)
class _DecisionEvidence:
    readiness: dict[str, str]


class _PayloadWriter:
    def __init__(self, *, checksum: str, row_count: int) -> None:
        self.checksum = checksum
        self.row_count = row_count
        self.calls = 0

    def retain_payload(self, **_kwargs: object) -> object:
        self.calls += 1
        return SimpleNamespace(checksum=self.checksum, row_count=self.row_count)


class _SnapshotWriter:
    def __init__(self) -> None:
        self.snapshots: list[object] = []

    def append_snapshot(self, snapshot: object) -> None:
        self.snapshots.append(snapshot)


def _install_runtime_helpers(
    monkeypatch: pytest.MonkeyPatch,
    approved: ApprovedLivePortfolioAcceptance,
    *,
    preview_weight: float = 0.6,
) -> tuple[StrategyRunResult, EodStrategyOutcome, object]:
    strategy_result = _strategy_result(weight=preview_weight)
    outcome = EodStrategyOutcome(
        strategy_id="seed_etf_industry_rotation",
        strategy_version="1",
        batch_key="eod-2026-09-02-seed_etf_industry_rotation-1",
        status="completed",
        required_dataset_states=(),
        artifact_id="signal-package",
        checksum="signal-checksum",
    )
    manual_snapshot = _manual_snapshot()
    monkeypatch.setattr(runtime, "_validate_strategy_and_accounts", lambda *_args: None)
    monkeypatch.setattr(
        runtime,
        "_run_strategy",
        lambda *_args, **_kwargs: strategy_result,
    )
    monkeypatch.setattr(
        runtime, "_approved_provider_snapshot", lambda _approved: "provider-snapshot"
    )
    monkeypatch.setattr(
        runtime,
        "_import_manual_baseline",
        lambda *_args: (
            manual_snapshot,
            AccountBaselineResult("baseline-1", "manual-sleeve", "created"),
        ),
    )
    monkeypatch.setattr(runtime, "_sizing_contexts", lambda *_args: {})
    monkeypatch.setattr(
        runtime, "_execute_eod", lambda *_args, **_kwargs: (outcome, strategy_result)
    )
    monkeypatch.setattr(
        runtime,
        "state_root_matches",
        lambda path: path == approved.data_root,
    )
    monkeypatch.setenv("DITTO_TRADING_SQLITE_PATH", str(approved.trading_database))
    return strategy_result, outcome, manual_snapshot


@pytest.mark.parametrize(
    ("stage", "expected_message"),
    [
        ("preview", "strategy preview drifted"),
        ("payload-checksum", "retained provider payload differs"),
        ("payload-count", "retained provider payload differs"),
        ("decision", "Daily Decision is not reviewable"),
    ],
)
def test_runtime_closes_persistence_and_withholds_receipt_on_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    expected_message: str,
) -> None:
    approved = _approved(tmp_path)
    _install_approval(monkeypatch, approved)
    _install_runtime_helpers(
        monkeypatch,
        approved,
        preview_weight=0.5 if stage == "preview" else 0.6,
    )
    payload_writer = _PayloadWriter(
        checksum=(
            "wrong"
            if stage == "payload-checksum"
            else approved.provider_payload_checksum
        ),
        row_count=0 if stage == "payload-count" else 1,
    )
    snapshot_writer = _SnapshotWriter()
    decision = _DecisionEvidence(
        readiness={"status": "blocked" if stage == "decision" else "ready"}
    )
    container = _Container(
        {
            StrategyFacade: object(),
            ProviderPayloadWriter: payload_writer,
            ProviderSnapshotWriter: snapshot_writer,
            GetPortfolioComparisonQuery: SimpleNamespace(get=lambda _request: {}),
            DailyDecisionQueryFacade: SimpleNamespace(
                get_report_v2=lambda **_kwargs: decision
            ),
        }
    )

    with pytest.raises(ValueError, match=expected_message):
        runtime.run_live_portfolio_acceptance(
            {},
            approved_request_hash=approved.request_hash,
            operator_id="operator",
            executed_at=_OBSERVED_AT,
            source=_Source(),
            container_factory=cast(
                "Callable[[], runtime._Container]", lambda: container
            ),
        )

    assert container.closed
    assert not runtime._receipt_path(approved).exists()


def test_runtime_success_closes_both_containers_and_authenticates_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = _approved(tmp_path)
    _install_approval(monkeypatch, approved)
    strategy_result, _outcome, _manual_snapshot_value = _install_runtime_helpers(
        monkeypatch, approved
    )
    source = _Source()
    source_container = _Container({SourceDataPort: source})
    payload_writer = _PayloadWriter(
        checksum=approved.provider_payload_checksum,
        row_count=len(approved.provider_rows),
    )
    snapshot_writer = _SnapshotWriter()
    decision = _DecisionEvidence(readiness={"status": "review"})
    comparison_requests: list[object] = []

    def comparison(request: object) -> dict[str, object]:
        comparison_requests.append(request)
        return {"as_of": approved.signal_date, "status": "comparable"}

    main_container = _Container(
        {
            StrategyFacade: object(),
            ProviderPayloadWriter: payload_writer,
            ProviderSnapshotWriter: snapshot_writer,
            GetPortfolioComparisonQuery: SimpleNamespace(get=comparison),
            DailyDecisionQueryFacade: SimpleNamespace(
                get_report_v2=lambda **_kwargs: decision
            ),
        }
    )
    containers = iter((source_container, main_container))
    preload_calls: list[None] = []
    monkeypatch.setattr(
        runtime,
        "preload_runtime_secrets",
        lambda: preload_calls.append(None),
    )

    result = runtime.run_live_portfolio_acceptance(
        {},
        approved_request_hash=approved.request_hash,
        operator_id="operator",
        executed_at=datetime(2026, 9, 2, 9, tzinfo=UTC),
        container_factory=cast(
            "Callable[[], runtime._Container]", lambda: next(containers)
        ),
    )

    assert preload_calls == [None]
    assert source_container.closed
    assert main_container.closed
    assert source.calls == [{"trade_date": approved.signal_date}]
    assert payload_writer.calls == 1
    assert snapshot_writer.snapshots == ["provider-snapshot"]
    assert len(comparison_requests) == 1
    request = comparison_requests[0]
    assert request.source_snapshot_ids == (approved.provider_snapshot_id,)
    assert result["operator_id"] == "operator"
    assert result["strategy_run"]["target"] == runtime._result_payload(strategy_result)
    evidence_hash = cast("str", result["evidence_hash"])
    body = {key: value for key, value in result.items() if key != "evidence_hash"}
    assert evidence_hash == canonical_hash(body)
    assert orjson.loads(runtime._receipt_path(approved).read_bytes()) == result
