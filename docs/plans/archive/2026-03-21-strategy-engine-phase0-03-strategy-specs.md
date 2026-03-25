# Phase 0 Part 3: strategy/ 策略决策层类型定义

> **Status:** ✅ DONE (2026-03-21)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 strategy/ 模块的核心类型：StrategySpec, StrategyTemplate, StrategyVersion, StrategyRun, SignalSnapshot, TargetPortfolio, StrategyContext, DecisionStage Protocol

**Architecture:** 纯类型定义层。StrategySpec 是策略的完整语义契约（混合范式：声明式 + Callable）。所有对象为 frozen dataclass。DecisionStage 是 Protocol，Pipeline 通过它分发。

**Design Doc:** v3 §2, §6.1, §9.1, gap-design §6.1 / §15

**前置依赖:** 无（Part 3 可与 Part 1 并行）

**实施偏差记录:**
1. `test_create_full_spec` 中 `tags=["momentum", "rotation", "etf"]` 改为 `tags=("momentum", "rotation", "etf")` — frozen dataclass 不做 list→tuple 隐式转换
2. `SignalSnapshot.test_is_frozen` 修改为检查属性重赋值 — frozen dataclass 不阻止 dict 内部修改
3. `DecisionStage` 添加 `@runtime_checkable` — 支持 `isinstance()` 检查
4. `param_constraints=[...]` 注释代码替换为空列表 `param_constraints=[]`
5. `StrategySpec.template` docstring 拆行为多行以满足 88 字符行宽限制

**验证结果:** 32 tests passed, 98.07% 覆盖率, 0 type errors/warnings, lint clean

---

## Task 1: strategy/ 模块清理与脚手架 `[S]` ✅

**Files:**
- Modify: `packages/core/src/ditto_core/strategy/__init__.py`
- Create: `packages/core/tests/unit/strategy/__init__.py`

> **R10**: 旧 README.md 需归档到 `docs/archive/`，但归档操作在 Part 5 (housekeeping) 中统一处理。

**Step 1: 更新 __init__.py**

```python
# packages/core/src/ditto_core/strategy/__init__.py
"""Strategy — 策略决策层.

Phase 0: specs, models, context, protocols.
Phase 1: pipeline, builtins.
"""

__all__: list[str] = []
```

```bash
mkdir -p packages/core/tests/unit/strategy
touch packages/core/tests/unit/strategy/__init__.py
```

**Step 2: Commit**

```bash
git add packages/core/src/ditto_core/strategy/__init__.py
git commit -m "chore(core): update strategy __init__.py for Phase 0"
```

---

## Task 2: ParamConstraint / ExecutionSpec / ConstraintSpec `[M]` ✅

**Files:**
- Create: `packages/core/src/ditto_core/strategy/specs.py`
- Test: `packages/core/tests/unit/strategy/test_specs_unit.py`

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/strategy/test_specs_unit.py
"""Tests for StrategySpec and related types."""

import pytest
from dataclasses import FrozenInstanceError


class TestParamConstraint:
    def test_create_int_param(self) -> None:
        from ditto_core.strategy.specs import ParamConstraint

        param = ParamConstraint(
            name="lookback",
            dtype="int",
            min_value=10,
            max_value=500,
            step=10,
        )
        assert param.dtype == "int"
        assert param.min_value == 10
        assert param.step == 10

    def test_create_enum_param(self) -> None:
        from ditto_core.strategy.specs import ParamConstraint

        param = ParamConstraint(
            name="method",
            dtype="str",
            allowed_values=("equal_weight", "score_weight", "risk_parity"),
        )
        assert param.allowed_values == ("equal_weight", "score_weight", "risk_parity")

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.specs import ParamConstraint

        param = ParamConstraint(name="k", dtype="int", min_value=1, max_value=10)
        with pytest.raises(FrozenInstanceError):
            param.max_value = 100  # type: ignore[misc]


class TestExecutionSpec:
    def test_create_calendar_trigger(self) -> None:
        from ditto_core.strategy.specs import ExecutionSpec

        spec = ExecutionSpec(frequency="M", method="calendar")
        assert spec.frequency == "M"
        assert spec.method == "calendar"

    def test_create_with_cost_model(self) -> None:
        from ditto_core.strategy.specs import CostModelSpec, ExecutionSpec

        spec = ExecutionSpec(
            frequency="W",
            method="calendar",
            cost_model=CostModelSpec(
                commission_rate=0.0003,
                slippage_bps=5.0,
            ),
        )
        assert spec.cost_model.commission_rate == 0.0003
        assert spec.cost_model.slippage_bps == 5.0

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.specs import ExecutionSpec

        spec = ExecutionSpec(frequency="M", method="calendar")
        with pytest.raises(FrozenInstanceError):
            spec.frequency = "W"  # type: ignore[misc]


class TestConstraintSpec:
    def test_create_max_weight(self) -> None:
        from ditto_core.strategy.specs import ConstraintSpec

        constraint = ConstraintSpec(
            type="max_weight_per_instrument",
            params={"value": 0.40},
            priority=1,
        )
        assert constraint.priority == 1

    def test_create_max_turnover(self) -> None:
        from ditto_core.strategy.specs import ConstraintSpec

        constraint = ConstraintSpec(
            type="max_turnover",
            params={"value": 0.50},
            priority=2,
        )
        assert constraint.priority == 2

    def test_default_priority(self) -> None:
        from ditto_core.strategy.specs import ConstraintSpec

        constraint = ConstraintSpec(type="max_drawdown", params={"value": 0.15})
        assert constraint.priority == 100  # 默认低优先级


class TestScorerSpec:
    def test_create_builtin_scorer(self) -> None:
        from ditto_core.strategy.specs import ScorerSpec

        spec = ScorerSpec(method="rank_then_combine")
        assert spec.method == "rank_then_combine"

    def test_create_with_weights(self) -> None:
        from ditto_core.strategy.specs import ScorerSpec

        spec = ScorerSpec(
            method="rank_then_combine",
            params={"signal_weights": {"momentum": 0.5, "cheapness": 0.3}},
        )
        assert spec.params["signal_weights"]["momentum"] == 0.5


class TestSelectorSpec:
    def test_create_top_k(self) -> None:
        from ditto_core.strategy.specs import SelectorSpec

        spec = SelectorSpec(method="top_k", params={"k": 5, "min_count": 1})
        assert spec.method == "top_k"


class TestStrategySpec:
    def test_create_minimal_spec(self) -> None:
        from ditto_core.strategy.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="etf_momentum_rotation",
            name="ETF Momentum Rotation",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
        )
        assert spec.strategy_id == "etf_momentum_rotation"
        assert spec.template == "etf_rotation"

    def test_create_full_spec(self) -> None:
        from ditto_core.strategy.specs import (
            ConstraintSpec,
            CostModelSpec,
            ExecutionSpec,
            ScorerSpec,
            SelectorSpec,
            StrategySpec,
        )

        spec = StrategySpec(
            strategy_id="etf_momentum_rotation",
            name="ETF Momentum Rotation",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
            scorer=ScorerSpec(method="rank_then_combine"),
            selector=SelectorSpec(method="top_k", params={"k": 5}),
            execution=ExecutionSpec(
                frequency="M",
                method="calendar",
                cost_model=CostModelSpec(commission_rate=0.0003, slippage_bps=5.0),
            ),
            constraints=[
                ConstraintSpec(type="max_weight_per_instrument", params={"value": 0.40}, priority=1),
                ConstraintSpec(type="max_turnover", params={"value": 0.50}, priority=2),
            ],
            benchmark="000300.SH",
            params={"lookback": 252, "vol_window": 60},
            param_constraints=[
                # ParamConstraint(name="lookback", dtype="int", min_value=60, max_value=500),
            ],
            tags=["momentum", "rotation", "etf"],
        )
        assert len(spec.constraints) == 2
        assert spec.tags == ("momentum", "rotation", "etf")

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="test",
            name="Test",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
        )
        with pytest.raises(FrozenInstanceError):
            spec.name = "Changed"  # type: ignore[misc]
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/core/tests/unit/strategy/test_specs_unit.py -v
```

**Step 3: Write implementation**

```python
# packages/core/src/ditto_core/strategy/specs.py
"""StrategySpec — 策略定义的核心语义契约.

混合范式：信号用表达式，编排用 Pipeline，风险用约束。
每个阶段通过 Protocol 接受声明式或命令式输入。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "ConstraintSpec",
    "CostModelSpec",
    "ExecutionSpec",
    "ParamConstraint",
    "ScorerSpec",
    "SelectorSpec",
    "StrategySpec",
]


@dataclass(frozen=True)
class ParamConstraint:
    """参数约束 — 为参数扫描 UI 和 Walk-Forward 提供元数据。

    Attributes:
        name: 参数名
        dtype: 数据类型 (int / float / str)
        min_value: 最小值
        max_value: 最大值
        step: 步长
        allowed_values: 枚举型参数的可选值
    """

    name: str
    dtype: str
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class CostModelSpec:
    """成本模型配置。"""

    commission_rate: float = 0.0003
    slippage_bps: float = 5.0
    impact_model: str = "linear"


@dataclass(frozen=True)
class ExecutionSpec:
    """执行层配置。

    Attributes:
        frequency: 换仓频率 (D / W / M / Q)
        method: 触发方法 (calendar / signal_change_pct / composite)
        cost_model: 成本模型
    """

    frequency: str = "M"
    method: str = "calendar"
    cost_model: CostModelSpec = field(default_factory=CostModelSpec)


@dataclass(frozen=True)
class ConstraintSpec:
    """单条风险约束。

    Attributes:
        type: 约束类型
        params: 约束参数
        priority: 优先级（数字小优先，默认 100）
    """

    type: str
    params: dict[str, object] = field(default_factory=dict)
    priority: int = 100


@dataclass(frozen=True)
class ScorerSpec:
    """评分器定义。"""

    method: str = "equal_weight"
    params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectorSpec:
    """标的选取器定义。"""

    method: str = "top_k"
    params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategySpec:
    """策略完整定义 — 一等语义对象。

    Attributes:
        strategy_id: 策略唯一 ID
        name: 策略名称
        template: 策略模板 (etf_rotation / etf_trend_swing / stock_selection_trend / stock_sector_rotation)
        universe: Universe ID
        asset_class: 资产类别
        scorer: 评分器配置
        selector: 选取器配置
        execution: 执行配置
        constraints: 风险约束列表
        benchmark: 基准代码
        params: 策略参数（运行时可覆盖）
        param_constraints: 参数约束元数据
        tags: 标签
    """

    strategy_id: str
    name: str
    template: str
    universe: str
    asset_class: str
    scorer: ScorerSpec = field(default_factory=ScorerSpec)
    selector: SelectorSpec = field(default_factory=SelectorSpec)
    execution: ExecutionSpec = field(default_factory=ExecutionSpec)
    constraints: tuple[ConstraintSpec, ...] = ()
    benchmark: str | None = None
    params: dict[str, object] = field(default_factory=dict)
    param_constraints: tuple[ParamConstraint, ...] = ()
    tags: tuple[str, ...] = ()
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/strategy/test_specs_unit.py -v
```

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/strategy/ packages/core/tests/unit/strategy/
git commit -m "feat(core): add StrategySpec and related configuration types"
```

---

## Task 3: StrategyRun / StrategyTemplate / StrategyVersion `[M]` ✅

**Files:**
- Create: `packages/core/src/ditto_core/strategy/models.py`
- Test: `packages/core/tests/unit/strategy/test_models_unit.py`

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/strategy/test_models_unit.py
"""Tests for StrategyRun / StrategyTemplate / StrategyVersion."""

import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime


class TestStrategyVersion:
    def test_create_version(self) -> None:
        from ditto_core.strategy.models import StrategyVersion

        ver = StrategyVersion(
            version=1,
            strategy_id="etf_momentum_rotation",
            spec_json={"name": "v1 spec"},
            created_at="2026-01-15T10:00:00Z",
            status="draft",
        )
        assert ver.version == 1
        assert ver.status == "draft"

    def test_published_version(self) -> None:
        from ditto_core.strategy.models import StrategyVersion

        ver = StrategyVersion(
            version=1,
            strategy_id="etf_momentum_rotation",
            spec_json={"name": "v1 spec"},
            created_at="2026-01-15T10:00:00Z",
            status="published",
        )
        assert ver.status == "published"

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.models import StrategyVersion

        ver = StrategyVersion(
            version=1,
            strategy_id="test",
            spec_json={},
            created_at="2026-01-15T10:00:00Z",
        )
        with pytest.raises(FrozenInstanceError):
            ver.version = 2  # type: ignore[misc]


class TestStrategyTemplate:
    def test_create_template(self) -> None:
        from ditto_core.strategy.models import StrategyTemplate

        tpl = StrategyTemplate(
            template_id="etf_rotation",
            name="ETF Rotation",
            description="ETF 轮动策略模板",
            asset_class="etf",
            required_signals=("momentum", "volatility"),
            built_in_constraints=("max_weight_per_instrument", "max_turnover"),
        )
        assert tpl.template_id == "etf_rotation"
        assert tpl.required_signals == ("momentum", "volatility")


class TestStrategyRun:
    def test_create_run(self) -> None:
        from ditto_core.strategy.models import StrategyRun

        run = StrategyRun(
            run_id="RUN-20260115-001",
            strategy_id="etf_momentum_rotation",
            spec_version=1,
            start="2025-01-01",
            end="2025-12-31",
            status="pending",
            parameters={"lookback": 252},
            baseline_run_id=None,
        )
        assert run.run_id == "RUN-20260115-001"
        assert run.status == "pending"
        assert run.parameters["lookback"] == 252

    def test_create_with_baseline(self) -> None:
        from ditto_core.strategy.models import StrategyRun

        run = StrategyRun(
            run_id="RUN-20260115-002",
            strategy_id="etf_momentum_rotation",
            spec_version=1,
            start="2025-01-01",
            end="2025-12-31",
            status="completed",
            parameters={"lookback": 126},
            baseline_run_id="RUN-20260115-001",
        )
        assert run.baseline_run_id == "RUN-20260115-001"

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.models import StrategyRun

        run = StrategyRun(
            run_id="RUN-001",
            strategy_id="test",
            spec_version=1,
            start="2025-01-01",
            end="2025-12-31",
        )
        with pytest.raises(FrozenInstanceError):
            run.status = "completed"  # type: ignore[misc]


class TestSignalSnapshot:
    def test_create_signal_snapshot(self) -> None:
        from ditto_core.strategy.models import SignalSnapshot

        snapshot = SignalSnapshot(
            trade_date="2026-01-15",
            strategy_id="etf_momentum_rotation",
            run_id="RUN-001",
            signals={
                "159915.SZ": 0.85,
                "510300.SH": 0.62,
                "159949.SZ": 0.41,
            },
        )
        assert snapshot.trade_date == "2026-01-15"
        assert len(snapshot.signals) == 3
        assert snapshot.signals["159915.SZ"] == pytest.approx(0.85)

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.models import SignalSnapshot

        snapshot = SignalSnapshot(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
            signals={"A": 0.5},
        )
        with pytest.raises(FrozenInstanceError):
            snapshot.signals["B"] = 0.3  # type: ignore[index]


class TestTargetPortfolio:
    def test_create_target_portfolio(self) -> None:
        from ditto_core.strategy.models import TargetPortfolio

        target = TargetPortfolio(
            trade_date="2026-01-15",
            strategy_id="etf_momentum_rotation",
            run_id="RUN-001",
            positions={
                "159915.SZ": 0.35,
                "510300.SH": 0.35,
                "159949.SZ": 0.30,
            },
            cash_target=0.0,
        )
        assert target.cash_target == 0.0
        assert sum(target.positions.values()) == pytest.approx(1.0)

    def test_with_cash_reserve(self) -> None:
        from ditto_core.strategy.models import TargetPortfolio

        target = TargetPortfolio(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
            positions={"A": 0.40, "B": 0.40},
            cash_target=0.20,
        )
        assert target.cash_target == 0.20
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/core/tests/unit/strategy/test_models_unit.py -v
```

**Step 3: Write implementation**

```python
# packages/core/src/ditto_core/strategy/models.py
"""StrategyRun / StrategyTemplate / StrategyVersion / SignalSnapshot / TargetPortfolio.

策略运行期的核心对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "SignalSnapshot",
    "StrategyRun",
    "StrategyTemplate",
    "StrategyVersion",
    "TargetPortfolio",
]


@dataclass(frozen=True)
class StrategyVersion:
    """策略版本 — 每次修改 Spec 产生新版本。

    Attributes:
        version: 版本号
        strategy_id: 关联策略 ID
        spec_json: Spec 的 JSON 快照
        created_at: 创建时间 (RFC3339)
        status: 状态 (draft / published)
    """

    version: int
    strategy_id: str
    spec_json: dict[str, object]
    created_at: str
    status: str = "draft"


@dataclass(frozen=True)
class StrategyTemplate:
    """策略模板 — 预配置的策略蓝图。

    Attributes:
        template_id: 模板 ID
        name: 模板名称
        description: 描述
        asset_class: 资产类别
        required_signals: 必需的信号列表
        built_in_constraints: 内置约束类型
    """

    template_id: str
    name: str
    description: str = ""
    asset_class: str = "etf"
    required_signals: tuple[str, ...] = ()
    built_in_constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyRun:
    """一次策略运行。

    Attributes:
        run_id: 运行唯一 ID
        strategy_id: 关联策略 ID
        spec_version: 使用的 Spec 版本
        start: 开始日期
        end: 结束日期
        status: 状态 (pending / running / completed / failed)
        parameters: 参数覆盖
        baseline_run_id: 对比基线运行 ID
        mode: 运行模式 (research / backtest / recommendation)
    """

    run_id: str
    strategy_id: str
    spec_version: int
    start: str
    end: str
    status: str = "pending"
    parameters: dict[str, object] = field(default_factory=dict)
    baseline_run_id: str | None = None
    mode: str = "research"


@dataclass(frozen=True)
class SignalSnapshot:
    """某日策略的信号快照。

    Attributes:
        trade_date: 交易日期
        strategy_id: 策略 ID
        run_id: 运行 ID
        signals: instrument_id → signal value
    """

    trade_date: str
    strategy_id: str
    run_id: str
    signals: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TargetPortfolio:
    """目标持仓 — 策略决策层的最终输出。

    Attributes:
        trade_date: 交易日期
        strategy_id: 策略 ID
        run_id: 运行 ID
        positions: instrument_id → weight
        cash_target: 目标现金比例
    """

    trade_date: str
    strategy_id: str
    run_id: str
    positions: dict[str, float] = field(default_factory=dict)
    cash_target: float = 0.0
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/strategy/test_models_unit.py -v
```

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/strategy/ packages/core/tests/unit/strategy/
git commit -m "feat(core): add StrategyRun/Template/Version/SignalSnapshot/TargetPortfolio"
```

---

## Task 4: StrategyContext / DecisionStage Protocol `[S]` ✅

**Files:**
- Create: `packages/core/src/ditto_core/strategy/context.py`
- Create: `packages/core/src/ditto_core/strategy/protocols.py`
- Modify: `packages/core/src/ditto_core/strategy/__init__.py`
- Test: `packages/core/tests/unit/strategy/test_context_unit.py`

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/strategy/test_context_unit.py
"""Tests for StrategyContext and DecisionStage Protocol."""

import pytest


class TestStrategyContext:
    def test_create_context(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext()
        assert ctx.risk_locked_instruments == {}

    def test_lock_and_unlock(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext()
        ctx.lock_instrument("159915.SZ", "max_drawdown")
        assert ctx.is_locked("159915.SZ")
        assert not ctx.is_locked("510300.SH")
        assert ctx.risk_locked_instruments["159915.SZ"] == "max_drawdown"

    def test_clear_locks(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext()
        ctx.lock_instrument("159915.SZ", "max_drawdown")
        ctx.lock_instrument("510300.SH", "single_loss_limit")
        ctx.clear_locks()
        assert ctx.risk_locked_instruments == {}

    def test_lock_instrument_overwrite(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext()
        ctx.lock_instrument("159915.SZ", "max_drawdown")
        ctx.lock_instrument("159915.SZ", "single_loss_limit")  # 覆盖
        assert ctx.risk_locked_instruments["159915.SZ"] == "single_loss_limit"


class TestDecisionStageProtocol:
    def test_protocol_is_defined(self) -> None:
        from ditto_core.strategy.protocols import DecisionStage

        # Protocol 存在且有 process 方法签名
        assert hasattr(DecisionStage, "process")

    def test_concrete_stage_implements_protocol(self) -> None:
        import polars as pl
        from ditto_core.strategy.context import StrategyContext
        from ditto_core.strategy.protocols import DecisionStage

        class DummyStage:
            def process(
                self, frame: pl.DataFrame, context: StrategyContext,
            ) -> pl.DataFrame:
                return frame

        stage = DummyStage()
        assert isinstance(stage, DecisionStage)
```

**Step 2: Run test to verify it fails**

**Step 3: Write implementation**

```python
# packages/core/src/ditto_core/strategy/context.py
"""StrategyContext — 策略运行时上下文."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["StrategyContext"]


@dataclass
class StrategyContext:
    """策略运行时上下文 — EngineLoop 持有。

    Attributes:
        risk_locked_instruments: 被风控锁定的标的 {instrument_id: reason}
    """

    risk_locked_instruments: dict[str, str] = field(default_factory=dict)

    def lock_instrument(self, instrument_id: str, reason: str) -> None:
        """锁定标的。"""
        self.risk_locked_instruments[instrument_id] = reason

    def is_locked(self, instrument_id: str) -> bool:
        """检查标的是否被锁定。"""
        return instrument_id in self.risk_locked_instruments

    def clear_locks(self) -> None:
        """清除所有锁定（每个 step 开始时调用）。"""
        self.risk_locked_instruments.clear()
```

```python
# packages/core/src/ditto_core/strategy/protocols.py
"""DecisionStage Protocol — Pipeline 阶段接口."""

from __future__ import annotations

from typing import Protocol

import polars as pl

from ditto_core.strategy.context import StrategyContext

__all__ = ["DecisionStage"]


class DecisionStage(Protocol):
    """Pipeline 阶段 — 每个 Stage 实现此接口。

    输入 DecisionFrame (pl.DataFrame)，输出处理后的 DecisionFrame。
    """

    def process(
        self, frame: pl.DataFrame, context: StrategyContext,
    ) -> pl.DataFrame: ...
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/strategy/test_context_unit.py -v
```

**Step 5: Update __init__.py and commit**

```python
# packages/core/src/ditto_core/strategy/__init__.py
from ditto_core.strategy.context import StrategyContext
from ditto_core.strategy.models import (
    SignalSnapshot,
    StrategyRun,
    StrategyTemplate,
    StrategyVersion,
    TargetPortfolio,
)
from ditto_core.strategy.protocols import DecisionStage
from ditto_core.strategy.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)

__all__ = [
    "ConstraintSpec",
    "CostModelSpec",
    "DecisionStage",
    "ExecutionSpec",
    "ParamConstraint",
    "ScorerSpec",
    "SelectorSpec",
    "SignalSnapshot",
    "StrategyContext",
    "StrategyRun",
    "StrategySpec",
    "StrategyTemplate",
    "StrategyVersion",
    "TargetPortfolio",
]
```

```bash
git add packages/core/src/ditto_core/strategy/ packages/core/tests/unit/strategy/
git commit -m "feat(core): add StrategyContext and DecisionStage Protocol"
```

---

## Task 5: strategy/ 模块完整验证 `[S]` ✅

```bash
pixi run -e dev pytest packages/core/tests/unit/strategy/ -v
pixi run -e dev check
```
