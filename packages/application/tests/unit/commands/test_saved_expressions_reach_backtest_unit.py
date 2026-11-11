"""Saved strategy-version expressions are exactly what a backtest run compiles.

Closes the controlled-formula editing loop: what the create command persists
(signal expressions + weights) is what the backtest command hands to the
factor bridge, and the production safety guard keeps rejecting unsafe
cross-sectional/time-series nesting without introducing any free-form code.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from ditto_application.commands.backtest import BacktestRunCommand, BacktestRunHandler
from ditto_application.commands.strategy import (
    CreateStrategyCommand,
    CreateStrategyHandler,
)
from ditto_application.exceptions import AppCommandError
from ditto_application.processes.execution.factor_bridge import FactorBridge
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_platform.foundation import SQLitePool
from ditto_strategy.alpha.specs import ScorerSpec, SelectorSpec, StrategySpec
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)


def _services(tmp_path: Path) -> tuple[GovernanceService, StrategyCatalogService]:
    pool = SQLitePool(str(tmp_path / "strategy.db"))
    SQLiteStrategySpecWriter(pool).init_schema()
    governance_store = SQLiteStrategyGovernanceStore(pool)
    governance_store.init_schema()
    catalog = StrategyCatalogService(
        reader=SQLiteStrategySpecReader(pool),
        writer=SQLiteStrategySpecWriter(pool),
        active_pointer_reader=governance_store,
        version_state_reader=governance_store,
    )
    return GovernanceService(governance_store), catalog


def _spec_json(strategy_id: str) -> dict[str, object]:
    spec = StrategySpec(
        strategy_id=strategy_id,
        name=strategy_id,
        template="stock_selection",
        universe="csi_a_share",
        asset_class="stock",
        scorer=ScorerSpec(method="rank"),
        selector=SelectorSpec(method="top_k", params={"k": 5}),
        params={"top_k": 5},
        signal_expressions=("momentum_1m", "value_pe"),
        signal_weights=(0.6, 0.4),
        required_datasets=("stock_daily", "adj_factor"),
    )
    return asdict(spec)


class _RecordingBridge(FactorBridge):
    """Capture the exact expressions/weights the run compiles."""

    def __init__(self) -> None:
        super().__init__(compiler=Mock())
        self.compiled: list[tuple[tuple[str, ...], tuple[float, ...]]] = []

    def compile_and_validate(
        self, expressions: tuple[str, ...], weights: tuple[float, ...]
    ) -> object:
        self.compiled.append((expressions, weights))
        return Mock()


def _backtest_handler(record: StrategySpecRecord, bridge: _RecordingBridge):
    catalog = Mock(spec=StrategyCatalogService)
    catalog.get_active_published.return_value = record
    catalog.get_spec.return_value = record
    runs = Mock(spec=RunLifecycleService)
    runs.create_run.return_value = None
    return BacktestRunHandler(
        catalog_service=catalog,
        run_service=runs,
        factor_bridge=bridge,
    )


def test_saved_version_expressions_are_what_the_backtest_compiles(
    tmp_path: Path,
) -> None:
    governance, catalog = _services(tmp_path)
    create = CreateStrategyHandler(governance)

    saved = create.handle(
        CreateStrategyCommand(
            strategy_id="formula-loop",
            name="formula-loop",
            spec_json=_spec_json("formula-loop"),
        )
    )

    # 重读持久化版本：保存的表达式/权重与提交内容逐字一致。
    record = catalog.get_spec("formula-loop", saved.version)
    assert record is not None
    persisted = record.spec_json
    assert persisted["signal_expressions"] == ["momentum_1m", "value_pe"]
    assert persisted["signal_weights"] == [0.6, 0.4]

    bridge = _RecordingBridge()
    handler = _backtest_handler(record, bridge)
    result = handler.handle(
        BacktestRunCommand(
            strategy_id="formula-loop",
            strategy_version=saved.version,
            start_date="2024-01-01",
            end_date="2024-02-01",
            initial_cash=1_000_000.0,
        )
    )

    assert result.strategy_version == saved.version
    # 运行编译的就是保存的表达式与权重：合法表达式保存后实际用于运行。
    assert bridge.compiled == [(("momentum_1m", "value_pe"), (0.6, 0.4))]


def test_create_duplicate_strategy_raises_structured_conflict_code(
    tmp_path: Path,
) -> None:
    governance, _catalog = _services(tmp_path)
    create = CreateStrategyHandler(governance)
    spec_json = _spec_json("dup-strategy")

    create.handle(
        CreateStrategyCommand(
            strategy_id="dup-strategy",
            name="dup-strategy",
            spec_json=spec_json,
        )
    )

    # 同名再创建：结构化冲突码（HTTP 层映射 409），不靠消息关键词。
    with pytest.raises(AppCommandError) as error:
        create.handle(
            CreateStrategyCommand(
                strategy_id="dup-strategy",
                name="dup-strategy",
                spec_json=spec_json,
            )
        )
    assert error.value.details["code"] == "STRATEGY_ALREADY_EXISTS"
    assert error.value.details["reason"] == "strategy_already_exists"
    assert error.value.details["strategy_id"] == "dup-strategy"


def test_create_rejects_unsafe_production_formula_fail_closed(tmp_path: Path) -> None:
    governance, _catalog = _services(tmp_path)
    create = CreateStrategyHandler(governance)

    unsafe = _spec_json("unsafe-formula")
    unsafe["signal_expressions"] = ["cs_rank(ts_mean(close, 5))"]
    unsafe["signal_weights"] = [1.0]
    unsafe["tags"] = ["production"]

    with pytest.raises(StrategySpecError) as error:
        create.handle(
            CreateStrategyCommand(
                strategy_id="unsafe-formula",
                name="unsafe-formula",
                spec_json=cast("dict[str, object]", unsafe),
                tags=("production",),
            )
        )
    # 受控守卫保持：截面算子内联时间序列在保存前即被拒绝，理由可读
    # （错误定位于 signal_expressions 字段）。
    assert error.value.details["reason"] == "unsafe_production_factor_expression"
    assert error.value.details["field_name"] == "signal_expressions"
