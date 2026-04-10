# Ditto Runtime Convergence Phase A Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不引入新依赖、不破坏当前 Phase 4 稳定性的前提下，收口 Ditto 的回测 runtime 主链路，消除 `EngineLoop` 中的跨层拼装与文档漂移，为后续多策略和实盘统一演进建立可靠边界。

**Architecture:** 保持 `EngineLoop` 为 concrete engine，继续把多态放在 `DataFeed`、`Brokerage`、`FillModel`、`SettlementModel` 等适配器边界上，而不是在本阶段新增一个“万能 TradingLoop Protocol”。Phase A 重点做 5 件事：输入组装 seam 外提、DecisionFrame 合约强化、stateful 风控 run-scope 化、模板参数 schema 校验、源码文档与真实实现对齐。

**Tech Stack:** Python 3.13, polars, pytest, basedpyright, ruff, Dishka, Pixi

---

## Scope

- 收口回测主链路，去掉 `EngineLoop._build_input_bundle()` 中的硬编码信号拼装
- 为 `DecisionFrame` 引入低成本、可测试的 schema 常量与校验辅助
- 修复 `MaxDrawdownRule` 一类 stateful guard 的跨 run 泄漏隐患
- 在 `StrategyRuntimeBuilder` 层提前做模板参数名/类型校验
- 清理 `TradingOrchestrator` / `BacktestTradingOrchestrator` 等失真文档

## Non-Goals

- 不接入 `LiveBrokerage` / WebSocket / 实时行情
- 不实现 `StrategyInstance` / `StrategyRegistry` / 多策略预算分配
- 不新增 `cvxpy`、券商 SDK、状态机框架等依赖
- 不做顶层包重命名，不改 `.importlinter` 分层边界

## Preconditions

- 以 [runtime-main-path-convergence-design.md](/home/chevy/projects/ditto/docs/plans/2026-04-06-runtime-main-path-convergence-design.md) 和 [ditto-future-architecture-design.md](/home/chevy/projects/ditto/docs/plans/2026-03-31-ditto-future-architecture-design.md) 为设计输入
- 开工前确认当前分支 `pixi run -e dev check` 与 `pixi run -e dev arch-check` 为绿
- 严格遵循 TDD：先写失败测试，再做最小实现，再重构

---

### Task 1: 注入 StrategyInputAssembler seam，移除 EngineLoop 硬编码输入拼装

**Files:**
- Create: `packages/engine/src/ditto_engine/backtest/input_contracts.py`
- Modify: `packages/engine/src/ditto_engine/backtest/engine.py`
- Modify: `packages/app/src/ditto_app/process/backtest_service.py`
- Modify: `packages/app/src/ditto_app/builders/service_factory.py`
- Test: `packages/engine/tests/unit/backtest/test_engine_loop_unit.py`
- Test: `packages/app/tests/unit/process/strategy/test_backtest_service_unit.py`
- Test: `packages/app/tests/unit/process/strategy/test_strategy_service_factory_unit.py`

**Step 1: Write the failing tests**

```python
class _RecordingAssembler:
    def __init__(self, bundle: StrategyInputBundle) -> None:
        self.bundle = bundle
        self.calls: list[tuple[str, str | None]] = []

    def assemble(
        self,
        trade_date: str,
        slice_: Slice,
        *,
        valid_until: str | None = None,
        run_id: str | None = None,
    ) -> StrategyInputBundle:
        self.calls.append((trade_date, run_id))
        return self.bundle


def test_engine_loop_uses_injected_input_assembler(...) -> None:
    assembler = _RecordingAssembler(bundle=sample_bundle)
    loop = EngineLoop(
        ...,
        input_assembler=assembler,
    )

    loop.run()

    assert assembler.calls == [("2026-01-06", "run-001")]


def test_backtest_service_passes_input_assembler_into_engine_loop(...) -> None:
    assembler = MagicMock(spec=StrategyInputAssembler)
    service = BacktestService(..., input_assembler=assembler)
    service.run()
    engine_loop_cls.assert_called_once()
    assert engine_loop_cls.call_args.kwargs["input_assembler"] is assembler
```

**Step 2: Run tests to verify they fail**

Run: `pixi run -e dev pytest packages/engine/tests/unit/backtest/test_engine_loop_unit.py -k input_assembler -v`

Expected: FAIL with `EngineLoop.__init__()` not accepting `input_assembler`, or assembler never called.

Run: `pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_backtest_service_unit.py -k input_assembler -v`

Expected: FAIL because `BacktestService` does not carry any input assembler dependency.

**Step 3: Write minimal implementation**

```python
class StrategyInputAssemblerLike(Protocol):
    def assemble(
        self,
        trade_date: str,
        slice_: Slice,
        *,
        valid_until: str | None = None,
        run_id: str | None = None,
    ) -> StrategyInputBundle: ...


class EngineLoop:
    def __init__(..., input_assembler: StrategyInputAssemblerLike) -> None:
        self._input_assembler = input_assembler

    def _build_input_bundle(self, date: str, slice_: Slice) -> StrategyInputBundle:
        return self._input_assembler.assemble(
            date,
            slice_,
            run_id=self._config.strategy_run_id,
        )
```

`StrategyServiceFactory` 复用现有 `_build_input_assembler()`，在构造 `BacktestService` 时显式注入，不再让 `EngineLoop` 自己拼 `signal_value`。

**Step 4: Run tests to verify they pass**

Run: `pixi run -e dev pytest packages/engine/tests/unit/backtest/test_engine_loop_unit.py -k input_assembler -v`

Expected: PASS

Run: `pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_backtest_service_unit.py -k input_assembler -v`

Expected: PASS

Run: `pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_strategy_service_factory_unit.py -k backtest_service_from_catalog -v`

Expected: PASS

**Step 5: Commit**

```bash
git add \
  packages/engine/src/ditto_engine/backtest/input_contracts.py \
  packages/engine/src/ditto_engine/backtest/engine.py \
  packages/app/src/ditto_app/process/backtest_service.py \
  packages/app/src/ditto_app/builders/service_factory.py \
  packages/engine/tests/unit/backtest/test_engine_loop_unit.py \
  packages/app/tests/unit/process/strategy/test_backtest_service_unit.py \
  packages/app/tests/unit/process/strategy/test_strategy_service_factory_unit.py
git commit -m "refactor(runtime): inject strategy input assembler into backtest loop"
```

---

### Task 2: 为 DecisionFrame 引入列常量与必需列校验辅助

**Files:**
- Create: `packages/engine/src/ditto_engine/alpha/frame_schema.py`
- Modify: `packages/engine/src/ditto_engine/alpha/pipeline.py`
- Modify: `packages/engine/src/ditto_engine/alpha/protocols.py`
- Test: `packages/engine/tests/unit/alpha/test_frame_schema_unit.py`
- Test: `packages/engine/tests/unit/alpha/test_pipeline_unit.py`

**Step 1: Write the failing tests**

```python
def test_require_columns_raises_for_missing_instrument_id() -> None:
    frame = pl.DataFrame({"signal_value": [0.1]})

    with pytest.raises(ValueError, match="instrument_id"):
        require_columns(frame, {"instrument_id"}, stage_name="pipeline:init")


def test_pipeline_rejects_frame_without_required_columns() -> None:
    bundle = StrategyInputBundle(
        trade_date="2026-01-06",
        strategy_id="demo",
        run_id="run-001",
        instruments=pl.DataFrame({"ticker": ["510300.SH"]}),
        market_data=pl.DataFrame(),
    )

    with pytest.raises(ValueError, match="instrument_id"):
        StrategyPipeline(stages=()).run(StrategyContext(), bundle)
```

**Step 2: Run tests to verify they fail**

Run: `pixi run -e dev pytest packages/engine/tests/unit/alpha/test_pipeline_unit.py -k required_columns -v`

Expected: FAIL because there is no `require_columns()` helper and pipeline silently accepts malformed frame.

**Step 3: Write minimal implementation**

```python
DECISION_COL_INSTRUMENT_ID = "instrument_id"
DECISION_COL_SIGNAL_VALUE = "signal_value"
DECISION_COL_SCORE = "score"
DECISION_COL_WEIGHT = "weight"
DECISION_COL_REASON_CODES = "reason_codes"


def require_columns(
    frame: pl.DataFrame,
    required: Collection[str],
    *,
    stage_name: str,
) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{stage_name} 缺少必要列: {missing}")
```

在 `StrategyPipeline.run()` 入口和 `_build_target_portfolio()` 前调用 `require_columns()`；`DecisionStage` 文档改为引用共享常量，而不是散落的字符串约定。

**Step 4: Run tests to verify they pass**

Run: `pixi run -e dev pytest packages/engine/tests/unit/alpha/test_frame_schema_unit.py -v`

Expected: PASS

Run: `pixi run -e dev pytest packages/engine/tests/unit/alpha/test_pipeline_unit.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add \
  packages/engine/src/ditto_engine/alpha/frame_schema.py \
  packages/engine/src/ditto_engine/alpha/pipeline.py \
  packages/engine/src/ditto_engine/alpha/protocols.py \
  packages/engine/tests/unit/alpha/test_frame_schema_unit.py \
  packages/engine/tests/unit/alpha/test_pipeline_unit.py
git commit -m "refactor(alpha): add decision frame schema helpers"
```

---

### Task 3: 将 stateful PostTrade guard 明确为 run-scoped，并提供 reset 语义

**Files:**
- Modify: `packages/engine/src/ditto_engine/risk/post_trade.py`
- Modify: `packages/app/src/ditto_app/process/backtest_service.py`
- Test: `packages/engine/tests/unit/backtest/test_post_trade_unit.py`
- Test: `packages/app/tests/unit/process/strategy/test_backtest_service_unit.py`

**Step 1: Write the failing tests**

```python
def test_max_drawdown_rule_reset_clears_peak_nav() -> None:
    rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
    rule.scan(account_view_with_nav(1.2), sample_slice())
    rule.reset()

    assert rule.scan(account_view_with_nav(1.0), sample_slice()) == []


def test_backtest_service_resets_post_trade_guard_before_run(...) -> None:
    guard = MagicMock()
    service = make_service(options=BacktestServiceOptions(post_trade_guard=guard))

    service.run()

    guard.reset.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `pixi run -e dev pytest packages/engine/tests/unit/backtest/test_post_trade_unit.py -k reset -v`

Expected: FAIL because `MaxDrawdownRule` has no `reset()`.

Run: `pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_backtest_service_unit.py -k post_trade_guard -v`

Expected: FAIL because `BacktestService` never resets guard state before `EngineLoop.run()`.

**Step 3: Write minimal implementation**

```python
class MaxDrawdownRule:
    def reset(self) -> None:
        self._peak_nav = 0.0


class CompositePostTradeGuard:
    def reset(self) -> None:
        for rule in self._rules:
            if hasattr(rule, "reset"):
                rule.reset()
```

在 `BacktestService._execute_backtest()` 中，构造 `EngineLoop` 前先对 `post_trade_guard` 做一次 `reset()`，确保所有 stateful guard 都以 run 为生命周期边界。

**Step 4: Run tests to verify they pass**

Run: `pixi run -e dev pytest packages/engine/tests/unit/backtest/test_post_trade_unit.py -k "MaxDrawdownRule or reset" -v`

Expected: PASS

Run: `pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_backtest_service_unit.py -k post_trade_guard -v`

Expected: PASS

**Step 5: Commit**

```bash
git add \
  packages/engine/src/ditto_engine/risk/post_trade.py \
  packages/app/src/ditto_app/process/backtest_service.py \
  packages/engine/tests/unit/backtest/test_post_trade_unit.py \
  packages/app/tests/unit/process/strategy/test_backtest_service_unit.py
git commit -m "fix(risk): reset stateful post-trade guards per backtest run"
```

---

### Task 4: 在 StrategyRuntimeBuilder 层加入模板参数 schema 校验

**Files:**
- Create: `packages/app/src/ditto_app/builders/template_param_schema.py`
- Modify: `packages/app/src/ditto_app/builders/runtime_builder.py`
- Test: `packages/app/tests/unit/process/strategy/test_runtime_builder_unit.py`
- Test: `packages/app/tests/unit/process/strategy/test_backtest_runtime_builder_unit.py`

**Step 1: Write the failing tests**

```python
def test_runtime_builder_rejects_unknown_template_param() -> None:
    record = make_record(
        spec_json={"template": "etf_rotation", "params": {"top_k": 3, "typo_k": 5}, ...}
    )
    builder = StrategyRuntimeBuilder(catalog_service=mock_catalog(record))

    with pytest.raises(ValueError, match="typo_k"):
        builder.build_published_runtime("momentum-etf", 1)


def test_runtime_builder_rejects_wrong_template_param_type() -> None:
    record = make_record(
        spec_json={"template": "etf_rotation", "params": {"top_k": "three"}, ...}
    )
    builder = StrategyRuntimeBuilder(catalog_service=mock_catalog(record))

    with pytest.raises(ValueError, match="top_k"):
        builder.build_published_runtime("momentum-etf", 1)
```

**Step 2: Run tests to verify they fail**

Run: `pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_runtime_builder_unit.py -k template_param -v`

Expected: FAIL because runtime builder currently accepts arbitrary `dict[str, object]` and only fails later, or silently carries bad keys.

**Step 3: Write minimal implementation**

```python
ETF_ROTATION_PARAM_SCHEMA = {
    "top_k": int,
    "cash_target": float,
    "signal_column": str,
    "max_weight": float,
    "max_positions": int,
}


def validate_template_params(
    template: str,
    params: Mapping[str, object],
) -> dict[str, object]:
    ...
```

在 `StrategyRuntimeBuilder._deserialize_strategy_spec()` 之后、`_build_pipeline()` 之前执行模板参数校验。Phase A 不改 catalog 存储格式，只做“早失败 + 清晰报错”。

**Step 4: Run tests to verify they pass**

Run: `pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_runtime_builder_unit.py -v`

Expected: PASS

Run: `pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_backtest_runtime_builder_unit.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add \
  packages/app/src/ditto_app/builders/template_param_schema.py \
  packages/app/src/ditto_app/builders/runtime_builder.py \
  packages/app/tests/unit/process/strategy/test_runtime_builder_unit.py \
  packages/app/tests/unit/process/strategy/test_backtest_runtime_builder_unit.py
git commit -m "refactor(app): validate template params during runtime assembly"
```

---

### Task 5: 对齐 engine 文档与源码事实，消除 TradingOrchestrator 漂移

**Files:**
- Modify: `packages/engine/src/ditto_engine/README.md`
- Modify: `packages/engine/README.md`
- Modify: `packages/engine/CLAUDE.md`
- Modify: `packages/engine/AGENTS.md`
- Modify: `README.md`

**Step 1: Write the failing checks**

```bash
rg -n "TradingOrchestrator|BacktestTradingOrchestrator|orchestrator/" \
  packages/engine/src/ditto_engine/README.md \
  packages/engine/README.md \
  packages/engine/CLAUDE.md \
  packages/engine/AGENTS.md \
  README.md
```

Expected: existing matches prove current docs are stale.

**Step 2: Run checks to verify drift exists**

Run the `rg` command above.

Expected: non-empty output referencing nonexistent `orchestrator/` module and `BacktestTradingOrchestrator` alias.

**Step 3: Write minimal implementation**

```md
### backtest/
回测引擎。`EngineLoop` 是当前唯一 concrete runtime loop；
扩展点在 `DataFeed`、`Brokerage`、`FeeModel`、`FillModel`、`SettlementModel`。

### runtime seam
策略输入由 app 层 assembler 组装后注入，Engine 不再内建 signal 拼装逻辑。
```

同步删掉不存在的 `orchestrator/` 目录说明，把 `DecisionFrame` 文字描述更新为“列常量 + 校验辅助”，而不是“纯文档约定”。

**Step 4: Run checks to verify they pass**

Run: `rg -n "TradingOrchestrator|BacktestTradingOrchestrator|orchestrator/" packages/engine/src/ditto_engine/README.md packages/engine/README.md packages/engine/CLAUDE.md packages/engine/AGENTS.md README.md`

Expected: no output

Run: `pixi run -e dev pytest interfaces/tests/registry/test_strategy_provider_unit.py -v`

Expected: PASS, proving doc-aligned provider wiring still works.

**Step 5: Commit**

```bash
git add \
  packages/engine/src/ditto_engine/README.md \
  packages/engine/README.md \
  packages/engine/CLAUDE.md \
  packages/engine/AGENTS.md \
  README.md
git commit -m "docs(engine): align runtime architecture docs with source"
```

---

## Final Verification

### Verification 1: Focused suites after each task

```bash
pixi run -e dev pytest packages/engine/tests/unit/backtest/test_engine_loop_unit.py -v
pixi run -e dev pytest packages/engine/tests/unit/alpha/test_pipeline_unit.py -v
pixi run -e dev pytest packages/engine/tests/unit/backtest/test_post_trade_unit.py -v
pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_runtime_builder_unit.py -v
pixi run -e dev pytest packages/app/tests/unit/process/strategy/test_backtest_service_unit.py -v
```

### Verification 2: Architecture guards

```bash
pixi run -e dev arch-check
```

Expected: all contracts green.

### Verification 3: Full fast gate

```bash
pixi run -e dev check
```

Expected: lint + fmt + type + fast tests all pass.

---

## Follow-Up Epics After Phase A

这些内容重要，但不放进本计划执行范围，避免一次性重构过大：

1. **EngineLoop 内部 Step Chain 化**
   - 目标：把 `_step()` 拆为 `risk_scan / rebalance / process_pending / audit` 四段纯函数或 handler
   - 前提：Task 1 的输入 assembler seam 已稳定

2. **多策略 runtime**
   - 目标：引入 `StrategyInstance`、`PortfolioSupervisor`、预算分配与策略级状态隔离
   - 前提：单策略 runtime contract 已固定

3. **统一历史 / 实时事件模型**
   - 目标：`HistoricalDataProvider` / `StreamingDataProvider` 共享事件 envelope
   - 前提：当前 backtest runtime 收口完成

4. **LiveBrokerage 与 OMS**
   - 目标：订单生命周期、撤改单、部分成交、paper/live 共用 execution contract
   - 前提：统一 runtime 和数据事件模型

---

## Suggested Commit Sequence

```bash
git commit -m "refactor(runtime): inject strategy input assembler into backtest loop"
git commit -m "refactor(alpha): add decision frame schema helpers"
git commit -m "fix(risk): reset stateful post-trade guards per backtest run"
git commit -m "refactor(app): validate template params during runtime assembly"
git commit -m "docs(engine): align runtime architecture docs with source"
```
