# RC-1 Real Data Signal Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the RC-1 gate for daily A-share stock/ETF/macro research and backtest production readiness, ending in a verified stock-selection signal package that can be read by the existing manual-trading APIs.

**Architecture:** Keep strategy, execution, data, and apps boundaries intact. Strategy continues to produce `TargetPortfolio`; application converts it into deterministic `TradeIntent` signal packages and persists intents through `IntentDataPort`; apps exposes CLI and acceptance workflows without moving business logic into transport code.

**Tech Stack:** Python 3.13, polars, Typer, FastAPI, SQLite-backed execution ports, pytest, ruff, basedpyright, import-linter, pixi.

---

## Scope And Exit Gate

RC-1 includes:

- A-share stocks, ETFs, and macro data at daily frequency.
- Research/backtest production readiness.
- Manual trading workflow: the system produces signals; humans trade; humans record fills.
- No real broker live trading and no broker order routing.

RC-1 exits only when these commands all pass in the release acceptance environment:

```bash
pixi run -e dev check
pixi run -e dev pytest packages/apps/tests/integration/test_golden_e2e.py packages/apps/tests/integration/test_stock_selection_golden_e2e.py packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py -q --no-cov
pixi run -e dev pytest packages/apps/tests/e2e/test_real_data_pipeline.py -m e2e --no-cov
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py --real-data --require-promoted --output artifacts/acceptance/rc1-report.json
```

The existing known xfail for complex multi-date `cs_rank` remains allowed only if stock-selection production templates do not use the unsupported `cs(ts(...))` expression shape.

## File Structure

Create:

- `packages/application/src/ditto_application/processes/execution/position_reader.py` - adapts `PositionDataPort` to `PositionReader` by converting latest stored position market values into weights.
- `packages/application/src/ditto_application/processes/execution/signal_package.py` - deterministic signal package builder and publisher.
- `packages/application/tests/unit/process/execution/test_position_reader_unit.py` - unit coverage for stored position weight calculation.
- `packages/application/tests/unit/process/execution/test_signal_package_unit.py` - unit coverage for package generation, deterministic checksums, and intent persistence.
- `packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py` - synthetic stock-selection to persisted manual-trading signal package E2E.
- `scripts/acceptance/rc1_real_data_acceptance.py` - release acceptance runner that collects command results and writes a JSON report.
- `docs/acceptance/rc1-release-checklist.md` - human-readable RC-1 release checklist.

Modify:

- `packages/application/src/ditto_application/providers_process.py` - provide `StoredPositionReader`, `SignalSnapshotProcess`, and `SignalPackagePublisher`.
- `packages/apps/src/ditto_apps/registry/contexts/bundle.py` - add `signal_package_publisher` to `StrategyBundle`.
- `packages/apps/src/ditto_apps/registry/contexts/strategy.py` - retrieve `SignalPackagePublisher` from DI.
- `packages/apps/src/ditto_apps/cli/commands/strategy.py` - add `publish-signals` command.
- `packages/apps/tests/unit/cli/commands/test_strategy_unit.py` - unit coverage for `publish-signals`.
- `packages/apps/tests/registry/test_strategy_bundle_public_surface_unit.py` - assert the strategy bundle exposes the publisher.
- `docs/plans/2026-06-14-production-launch-roadmap.md` - mark RC-1 as the new acceptance gate and link the checklist.

## Task 1: Stored Position Reader

**Files:**
- Create: `packages/application/src/ditto_application/processes/execution/position_reader.py`
- Create: `packages/application/tests/unit/process/execution/test_position_reader_unit.py`

- [ ] **Step 1: Write the failing unit tests**

Add this file:

```python
"""StoredPositionReader unit tests."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_application.processes.execution.position_reader import StoredPositionReader
from ditto_execution.models import PositionRecord


@dataclass
class _PositionPort:
    rows: list[PositionRecord]

    def list_positions(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
        run_id: str | None = None,
    ) -> list[PositionRecord]:
        assert strategy_id == "stock-selection"
        assert snapshot_date is None
        assert run_id is None
        return self.rows


def _row(
    instrument_id: int,
    snapshot_date: str,
    market_value: float,
) -> PositionRecord:
    return PositionRecord(
        snapshot_id=f"p-{instrument_id}-{snapshot_date}",
        strategy_id="stock-selection",
        snapshot_date=snapshot_date,
        instrument_id=instrument_id,
        quantity=100,
        available_quantity=100,
        average_cost=10.0,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def test_latest_snapshot_market_values_become_weights() -> None:
    reader = StoredPositionReader(
        position_port=_PositionPort(
            [
                _row(1, "2026-01-05", 900.0),
                _row(1, "2026-01-06", 600.0),
                _row(2, "2026-01-06", 400.0),
            ]
        )
    )

    result = reader.get_current_positions("stock-selection")

    assert result == {1: 0.6, 2: 0.4}


def test_empty_or_zero_market_value_returns_empty_weights() -> None:
    assert StoredPositionReader(position_port=_PositionPort([])).get_current_positions(
        "stock-selection"
    ) == {}
    assert StoredPositionReader(
        position_port=_PositionPort([_row(1, "2026-01-06", 0.0)])
    ).get_current_positions("stock-selection") == {}
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/execution/test_position_reader_unit.py -q --no-cov
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ditto_application.processes.execution.position_reader'`.

- [ ] **Step 3: Implement `StoredPositionReader`**

Add:

```python
"""PositionReader adapter backed by stored manual position snapshots."""

from __future__ import annotations

from ditto_execution.contracts import PositionDataPort

__all__ = ["StoredPositionReader"]


class StoredPositionReader:
    """Convert latest stored position market values into current weights."""

    def __init__(self, position_port: PositionDataPort) -> None:
        self._position_port = position_port

    def get_current_positions(self, strategy_id: str) -> dict[int, float]:
        rows = self._position_port.list_positions(strategy_id=strategy_id)
        if not rows:
            return {}

        latest_date = max(row.snapshot_date for row in rows)
        latest_rows = [row for row in rows if row.snapshot_date == latest_date]
        total_value = sum(row.market_value for row in latest_rows)
        if total_value <= 0:
            return {}

        return {
            row.instrument_id: row.market_value / total_value
            for row in sorted(latest_rows, key=lambda item: item.instrument_id)
            if row.market_value > 0
        }
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/execution/test_position_reader_unit.py -q --no-cov
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add packages/application/src/ditto_application/processes/execution/position_reader.py packages/application/tests/unit/process/execution/test_position_reader_unit.py
git commit -m "feat: add stored position reader for signal packages"
```

## Task 2: Deterministic Signal Package Publisher

**Files:**
- Create: `packages/application/src/ditto_application/processes/execution/signal_package.py`
- Create: `packages/application/tests/unit/process/execution/test_signal_package_unit.py`

- [ ] **Step 1: Write the failing unit tests**

Add this file:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/execution/test_signal_package_unit.py -q --no-cov
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ditto_application.processes.execution.signal_package'`.

- [ ] **Step 3: Implement the publisher**

Add:

```python
"""Deterministic signal package generation for manual trading."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256

import orjson
from ditto_execution.contracts import IntentDataPort
from ditto_execution.targets import TargetPortfolioLike

from ditto_application.execution_dto import TradeIntent, intent_to_record
from ditto_application.processes.execution.ports import PositionReader
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess

__all__ = [
    "SignalPackage",
    "SignalPackagePublisher",
]


@dataclass(frozen=True)
class SignalPackage:
    """Manual-trading signal package emitted from one target portfolio."""

    run_id: str
    strategy_id: str
    signal_date: str
    intents: tuple[TradeIntent, ...]
    dataset_snapshot_ids: dict[str, str]
    factor_ids: tuple[str, ...]
    risk_flags: tuple[str, ...]
    factor_values: dict[int, dict[str, float]]
    checksum: str


class SignalPackagePublisher:
    """Build deterministic packages and persist their trade intents."""

    def __init__(
        self,
        *,
        position_reader: PositionReader,
        intent_port: IntentDataPort,
    ) -> None:
        self._snapshot = SignalSnapshotProcess(position_reader=position_reader)
        self._intent_port = intent_port

    def publish(
        self,
        *,
        target: TargetPortfolioLike,
        dataset_snapshot_ids: dict[str, str] | None = None,
        factor_ids: tuple[str, ...] = (),
        risk_flags: tuple[str, ...] = (),
        factor_values: dict[int, dict[str, float]] | None = None,
        threshold: float = 0.01,
    ) -> SignalPackage:
        strategy_id = str(target.strategy_id)
        signal_date = str(target.trade_date)
        run_id = str(target.run_id)
        raw_intents = self._snapshot.generate_intents(
            strategy_id=strategy_id,
            signal_date=signal_date,
            target=target,
            threshold=threshold,
        )
        intents = tuple(
            sorted(
                (
                    replace(
                        intent,
                        intent_id=_stable_intent_id(run_id, signal_date, intent),
                    )
                    for intent in raw_intents
                ),
                key=lambda item: item.instrument_id,
            )
        )
        for intent in intents:
            self._intent_port.save_intent(intent_to_record(intent))

        payload = {
            "dataset_snapshot_ids": dict(sorted((dataset_snapshot_ids or {}).items())),
            "factor_ids": list(factor_ids),
            "factor_values": {
                str(instrument_id): dict(sorted(values.items()))
                for instrument_id, values in sorted((factor_values or {}).items())
            },
            "intents": [_intent_payload(intent) for intent in intents],
            "risk_flags": list(risk_flags),
            "run_id": run_id,
            "signal_date": signal_date,
            "strategy_id": strategy_id,
        }
        return SignalPackage(
            run_id=run_id,
            strategy_id=strategy_id,
            signal_date=signal_date,
            intents=intents,
            dataset_snapshot_ids=dict(sorted((dataset_snapshot_ids or {}).items())),
            factor_ids=factor_ids,
            risk_flags=risk_flags,
            factor_values=factor_values or {},
            checksum=_checksum(payload),
        )


def _stable_intent_id(run_id: str, signal_date: str, intent: TradeIntent) -> str:
    direction = intent.direction
    return f"sig-{run_id}-{signal_date}-{intent.instrument_id}-{direction}"


def _intent_payload(intent: TradeIntent) -> dict[str, object]:
    payload = asdict(intent)
    payload.pop("intent_id", None)
    return dict(sorted(payload.items()))


def _checksum(payload: dict[str, object]) -> str:
    data = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return f"sha256:{sha256(data).hexdigest()}"
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/execution/test_signal_package_unit.py -q --no-cov
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add packages/application/src/ditto_application/processes/execution/signal_package.py packages/application/tests/unit/process/execution/test_signal_package_unit.py
git commit -m "feat: publish deterministic signal packages"
```

## Task 3: DI And Strategy Bundle Wiring

**Files:**
- Modify: `packages/application/src/ditto_application/providers_process.py`
- Modify: `packages/apps/src/ditto_apps/registry/contexts/bundle.py`
- Modify: `packages/apps/src/ditto_apps/registry/contexts/strategy.py`
- Modify: `packages/apps/tests/registry/test_strategy_bundle_public_surface_unit.py`

- [ ] **Step 1: Write the failing registry test**

Append this test:

```python
def test_strategy_bundle_exposes_signal_package_publisher() -> None:
    from dataclasses import fields

    from ditto_apps.registry.contexts.bundle import StrategyBundle

    assert "signal_package_publisher" in {field.name for field in fields(StrategyBundle)}
```

- [ ] **Step 2: Run the registry test and confirm it fails**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/registry/test_strategy_bundle_public_surface_unit.py -q --no-cov
```

Expected: FAIL because `signal_package_publisher` is absent.

- [ ] **Step 3: Wire application providers**

In `providers_process.py`, add imports:

```python
from ditto_execution.contracts import IntentDataPort, PositionDataPort
from ditto_application.processes.execution.position_reader import StoredPositionReader
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
```

Add provider methods in the existing process provider class:

```python
    @provide
    def stored_position_reader(
        self,
        position_port: PositionDataPort,
    ) -> StoredPositionReader:
        """Stored position adapter for signal package generation."""
        return StoredPositionReader(position_port=position_port)

    @provide
    def signal_snapshot_process(
        self,
        position_reader: StoredPositionReader,
    ) -> SignalSnapshotProcess:
        """Signal snapshot process using stored manual positions."""
        return SignalSnapshotProcess(position_reader=position_reader)

    @provide
    def signal_package_publisher(
        self,
        position_reader: StoredPositionReader,
        intent_port: IntentDataPort,
    ) -> SignalPackagePublisher:
        """Signal package publisher backed by execution intent storage."""
        return SignalPackagePublisher(
            position_reader=position_reader,
            intent_port=intent_port,
        )
```

- [ ] **Step 4: Wire the apps strategy bundle**

In `bundle.py`, import and add the field:

```python
from ditto_application.processes.execution.signal_package import SignalPackagePublisher


@dataclass(frozen=True)
class StrategyBundle:
    """策略上下文组合包。"""

    strategy_facade: StrategyFacade
    catalog_service: StrategyCatalogReader | None = None
    run_service: RunLifecycleService | None = None
    run_writer: StrategyRunStatusWriter | None = None
    signal_package_publisher: SignalPackagePublisher | None = None
```

In `strategy.py`, import and retrieve the publisher:

```python
from ditto_application.processes.execution.signal_package import SignalPackagePublisher


signal_package_publisher=container.get(SignalPackagePublisher),
```

- [ ] **Step 5: Run registry and architecture tests**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/registry/test_strategy_bundle_public_surface_unit.py -q --no-cov
pixi run -e dev arch-check
```

Expected: tests pass and import contracts remain kept.

- [ ] **Step 6: Commit**

```bash
git add packages/application/src/ditto_application/providers_process.py packages/apps/src/ditto_apps/registry/contexts/bundle.py packages/apps/src/ditto_apps/registry/contexts/strategy.py packages/apps/tests/registry/test_strategy_bundle_public_surface_unit.py
git commit -m "feat: wire signal package publisher"
```

## Task 4: Strategy CLI `publish-signals`

**Files:**
- Modify: `packages/apps/src/ditto_apps/cli/commands/strategy.py`
- Modify: `packages/apps/tests/unit/cli/commands/test_strategy_unit.py`

- [ ] **Step 1: Add CLI unit tests**

Add to `TestStrategyCommandHelp`:

```python
    def test_strategy_publish_signals_help_exists(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["strategy", "publish-signals", "--help"])
        assert result.exit_code == 0
        assert "publish-signals" in result.output
```

Add to `TestStrategyCommandIntegration`:

```python
    def test_strategy_publish_signals_runs_recommendation_and_persists_package(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        from ditto_kernel.identity import InstrumentId
        from ditto_strategy.alpha.models import TargetPortfolio

        target = TargetPortfolio(
            trade_date="2026-01-30",
            strategy_id="stock-selection",
            run_id="run-publish-1",
            positions={InstrumentId(1): 0.3},
            cash_target=0.7,
        )
        mock_facade = MagicMock()
        mock_facade.run_strategy_for_date_from_catalog.return_value = Mock(
            run_id="run-publish-1",
            strategy_id="stock-selection",
            trade_date="2026-01-30",
            target=target,
        )
        mock_publisher = MagicMock()
        mock_publisher.publish.return_value = Mock(
            run_id="run-publish-1",
            strategy_id="stock-selection",
            signal_date="2026-01-30",
            intents=(Mock(), Mock()),
            checksum="sha256:abc",
        )
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)
        mock_create_bundle.return_value.__enter__.return_value = Mock(
            strategy_facade=mock_facade,
            signal_package_publisher=mock_publisher,
        )

        result = runner.invoke(
            app,
            [
                "strategy",
                "publish-signals",
                "stock-selection",
                "2026-01-30",
                "--dataset-snapshot",
                "stock_daily=sha256:stock",
                "--factor",
                "quality_roe",
            ],
        )

        assert result.exit_code == 0
        kwargs = mock_facade.run_strategy_for_date_from_catalog.call_args.kwargs
        assert kwargs["config"].mode == StrategyRunMode.RECOMMENDATION
        mock_publisher.publish.assert_called_once()
        publish_kwargs = mock_publisher.publish.call_args.kwargs
        assert publish_kwargs["target"] is target
        assert publish_kwargs["dataset_snapshot_ids"] == {
            "stock_daily": "sha256:stock"
        }
        assert publish_kwargs["factor_ids"] == ("quality_roe",)
        assert "intents=2" in result.output
        assert "checksum=sha256:abc" in result.output
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/cli/commands/test_strategy_unit.py -q --no-cov
```

Expected: FAIL because `publish-signals` command is absent.

- [ ] **Step 3: Implement the CLI command**

Add helpers:

```python
def _parse_dataset_snapshots(items: list[str] | None) -> dict[str, str]:
    snapshots: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise typer.BadParameter(
                f"dataset snapshot must be DATASET=CHECKSUM, got {item!r}"
            )
        dataset, checksum = item.split("=", 1)
        if not dataset or not checksum:
            raise typer.BadParameter(
                f"dataset snapshot must be DATASET=CHECKSUM, got {item!r}"
            )
        snapshots[dataset] = checksum
    return snapshots
```

Add command:

```python
@app.command("publish-signals")
def publish_signals(
    strategy_id: str = typer.Argument(..., help="策略 ID"),
    trade_date: str = typer.Argument(..., help="交易日期 YYYY-MM-DD"),
    version: int | None = typer.Option(None, "--version", help="策略版本"),
    source: str = typer.Option("tushare", "--source", help="数据源名称"),
    dataset_snapshot: list[str] | None = typer.Option(
        None,
        "--dataset-snapshot",
        help="数据快照校验，格式 DATASET=CHECKSUM，可重复",
    ),
    factor: list[str] | None = typer.Option(
        None,
        "--factor",
        help="信号解释中的因子 ID，可重复",
    ),
    threshold: float = typer.Option(0.01, "--threshold", help="最小调仓权重"),
    allow_experimental_data: bool = typer.Option(
        False,
        "--allow-experimental-data",
        help="显式允许 experimental 数据集进入推荐态运行",
    ),
) -> None:
    """运行推荐态策略并发布人工交易信号包。"""
    config = _build_run_config(strategy_id, StrategyRunMode.RECOMMENDATION)
    snapshots = _parse_dataset_snapshots(dataset_snapshot)
    with create_strategy_bundle() as bundle:
        if bundle.signal_package_publisher is None:
            raise typer.BadParameter("SignalPackagePublisher 未配置")
        result = bundle.strategy_facade.run_strategy_for_date_from_catalog(
            config=config,
            trade_date=trade_date,
            version=version,
            source=source,
            allow_experimental_data=allow_experimental_data,
        )
        package = bundle.signal_package_publisher.publish(
            target=result.target,
            dataset_snapshot_ids=snapshots,
            factor_ids=tuple(factor or ()),
            threshold=threshold,
        )
    typer.echo(
        " ".join(
            [
                f"run_id={package.run_id}",
                f"strategy_id={package.strategy_id}",
                f"signal_date={package.signal_date}",
                f"intents={len(package.intents)}",
                f"checksum={package.checksum}",
            ]
        )
    )
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/cli/commands/test_strategy_unit.py -q --no-cov
```

Expected: strategy CLI tests pass.

- [ ] **Step 5: Commit**

```bash
git add packages/apps/src/ditto_apps/cli/commands/strategy.py packages/apps/tests/unit/cli/commands/test_strategy_unit.py
git commit -m "feat: add signal publication cli"
```

## Task 5: Synthetic Stock Selection Signal Package E2E

**Files:**
- Create: `packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py`

- [ ] **Step 1: Add signal package E2E**

Add this file:

```python
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
```

- [ ] **Step 2: Run synthetic signal E2E**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py packages/apps/tests/integration/test_stock_selection_golden_e2e.py -q --no-cov
```

Expected: both integration test files pass.

- [ ] **Step 3: Commit**

```bash
git add packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py
git commit -m "test: add stock selection signal package e2e"
```

## Task 6: Release Acceptance Runner

**Files:**
- Create: `scripts/acceptance/rc1_real_data_acceptance.py`

- [ ] **Step 1: Add the acceptance runner**

Create:

```python
"""RC-1 release acceptance runner."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import orjson


@dataclass(frozen=True)
class CommandResult:
    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def _run(name: str, command: list[str]) -> CommandResult:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
    )
    return CommandResult(
        name=name,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout[-8000:],
        stderr=completed.stderr[-8000:],
    )


def _commands(real_data: bool, require_promoted: bool) -> list[tuple[str, list[str]]]:
    commands = [
        ("check", ["pixi", "run", "-e", "dev", "check"]),
        (
            "targeted-golden",
            [
                "pixi",
                "run",
                "-e",
                "dev",
                "pytest",
                "packages/apps/tests/integration/test_golden_e2e.py",
                "packages/apps/tests/integration/test_stock_selection_golden_e2e.py",
                "packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py",
                "-q",
                "--no-cov",
            ],
        ),
        (
            "promotion-evidence-stock-daily",
            [
                "pixi",
                "run",
                "-e",
                "dev",
                "python",
                "-m",
                "ditto_apps.cli.main",
                "ops",
                "promotion-collect",
                "stock_daily",
            ],
        ),
    ]
    if real_data:
        commands.append(
            (
                "real-data-e2e",
                [
                    "pixi",
                    "run",
                    "-e",
                    "dev",
                    "pytest",
                    "packages/apps/tests/e2e/test_real_data_pipeline.py",
                    "-m",
                    "e2e",
                    "--no-cov",
                ],
            )
        )
    if require_promoted:
        commands.append(
            (
                "maturity-status",
                [
                    "pixi",
                    "run",
                    "-e",
                    "dev",
                    "python",
                    "-m",
                    "ditto_apps.cli.main",
                    "ops",
                    "status",
                    "--json",
                ],
            )
        )
    return commands


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-data", action="store_true")
    parser.add_argument("--require-promoted", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    results = [_run(name, command) for name, command in _commands(args.real_data, args.require_promoted)]
    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "passed": all(result.passed for result in results),
        "results": [asdict(result) | {"passed": result.passed} for result in results],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the script in synthetic mode**

Run:

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py --output artifacts/acceptance/rc1-smoke.json
```

Expected: exit code 0 and `artifacts/acceptance/rc1-smoke.json` contains `"passed": true`.

- [ ] **Step 3: Commit**

```bash
git add scripts/acceptance/rc1_real_data_acceptance.py
git commit -m "chore: add rc1 acceptance runner"
```

## Task 7: RC-1 Checklist And Roadmap Sync

**Files:**
- Create: `docs/acceptance/rc1-release-checklist.md`
- Modify: `docs/plans/2026-06-14-production-launch-roadmap.md`

- [ ] **Step 1: Add the release checklist**

Create:

```markdown
# RC-1 Release Checklist

## Scope

- Daily A-share stocks, ETFs, and macro data.
- Research and backtest production readiness.
- Manual trading signals only.
- No real broker live trading.

## Required Evidence

- `pixi run -e dev check` passes.
- ETF golden E2E passes.
- Stock-selection golden E2E passes.
- Stock-selection signal package E2E passes.
- Real-data E2E passes in the release acceptance environment.
- Promotion evidence exists for `stock_basic`, `stock_daily`, `balance_sheet`, `income_statement`, `valuation_metrics`, ETF/index daily data, industry mapping, and required macro indicators.
- `strategy publish-signals` creates persisted `TradeIntent` records readable from `/trade/signals/latest`.
- Manual fill recording recomputes positions and deviation report.

## Release Command

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py --real-data --require-promoted --output artifacts/acceptance/rc1-report.json
```

## Go Criteria

- The release command exits with code 0.
- The generated acceptance report has `"passed": true`.
- Dataset maturity gates do not require `--allow-experimental-data` for RC-1 production runs.
- The only allowed xfail is the documented cross-section expression limitation.
```

- [ ] **Step 2: Link checklist from the roadmap**

In `docs/plans/2026-06-14-production-launch-roadmap.md`, add an RC-1 section above the acceptance checklist:

```markdown
## RC-1 Acceptance Gate

RC-1 is the current release target for research/backtest production readiness without real broker live trading. The executable checklist lives in [RC-1 Release Checklist](../acceptance/rc1-release-checklist.md).

The release is not accepted until `scripts/acceptance/rc1_real_data_acceptance.py --real-data --require-promoted` exits with code 0 and writes a passing acceptance report.
```

- [ ] **Step 3: Run documentation sanity checks**

Run:

```bash
rg "RC-1" docs/acceptance/rc1-release-checklist.md docs/plans/2026-06-14-production-launch-roadmap.md
pixi run -e dev check
```

Expected: `rg` finds both references and `check` passes.

- [ ] **Step 4: Commit**

```bash
git add docs/acceptance/rc1-release-checklist.md docs/plans/2026-06-14-production-launch-roadmap.md
git commit -m "docs: define rc1 release acceptance gate"
```

## Task 8: Full Verification Pass

**Files:**
- No source edits.

- [ ] **Step 1: Run focused unit and integration tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/execution/test_position_reader_unit.py packages/application/tests/unit/process/execution/test_signal_package_unit.py packages/apps/tests/unit/cli/commands/test_strategy_unit.py packages/apps/tests/registry/test_strategy_bundle_public_surface_unit.py packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py -q --no-cov
```

Expected: all selected tests pass.

- [ ] **Step 2: Run existing golden coverage**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/integration/test_golden_e2e.py packages/apps/tests/integration/test_stock_selection_golden_e2e.py packages/application/tests/integration/test_restored_run_replay_execution_golden.py -q --no-cov
```

Expected: all selected tests pass.

- [ ] **Step 3: Run architecture and full local gate**

Run:

```bash
pixi run -e dev arch-check
pixi run -e dev check
```

Expected: import contracts pass; `check` reports lint, format, type, and fast tests all green.

- [ ] **Step 4: Run release acceptance smoke**

Run:

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py --output artifacts/acceptance/rc1-smoke.json
```

Expected: exit code 0 and JSON report has `"passed": true`.

- [ ] **Step 5: Run real-data acceptance in the configured environment**

Run this only where Tushare/FRED credentials and real data access are configured:

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py --real-data --require-promoted --output artifacts/acceptance/rc1-report.json
```

Expected: exit code 0 and JSON report has `"passed": true`.

- [ ] **Step 6: Commit verification artifact references**

Do not commit raw `artifacts/` outputs. Update only the release checklist with the generated report path and timestamp:

```bash
git add docs/acceptance/rc1-release-checklist.md
git commit -m "docs: record rc1 acceptance evidence"
```

## Self-Review

- Spec coverage: the plan covers data promotion evidence, real-data E2E, stock-selection signal publication, manual-trading read path, PIT/leakage acceptance, CI-style synthetic coverage, and release acceptance reporting.
- Placeholder scan: the plan contains no placeholder markers and no open-ended test tasks.
- Type consistency: `SignalPackagePublisher.publish()` consumes `TargetPortfolioLike`, persists `TradeIntent` through `IntentDataPort`, and keeps transport changes in `apps`.
