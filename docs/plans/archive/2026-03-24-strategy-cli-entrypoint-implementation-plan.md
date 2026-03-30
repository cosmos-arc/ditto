# Strategy CLI EntryPoint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为已完成的 catalog-backed strategy facade 补上最小 CLI 外层入口，让策略运行与回测可以从 `ditto` 命令直接触发。

**Architecture:** 保持 CLI 只做参数解析、bundle 创建和结果输出，所有业务编排继续委托给 `StrategyFacade`。新增 `StrategyBundle` / `create_strategy_bundle()` 作为上下文组合根，再由 `strategy` 命令组调用 facade 的 `research`、`recommendation`、`backtest` 入口。

**Tech Stack:** Python 3.13, typer, pytest, dishka, pixi

---

### Task 1: 锁定 strategy CLI 对外契约

**Files:**
- Create: `apps/port/tests/unit/cli/commands/test_strategy_unit.py`
- Modify: `apps/port/tests/unit/cli/test_market_commands.py`

**Step 1: 写失败测试**

- 验证 `ditto strategy --help`、`ditto strategy research --help`、`ditto strategy recommend --help`、`ditto strategy backtest --help` 可见。
- 验证三个命令分别调用：
  - `StrategyFacade.run_strategy_for_date_from_catalog(...)`
  - `StrategyFacade.run_backtest_from_catalog(...)`

**Step 2: 运行测试确认失败**

Run:

```bash
pixi run -e dev pytest apps/port/tests/unit/cli/commands/test_strategy_unit.py apps/port/tests/unit/cli/test_market_commands.py --no-cov -q
```

### Task 2: 实现 strategy 上下文与命令组

**Files:**
- Modify: `apps/port/src/ditto_port/registry/contexts/bundle.py`
- Create: `apps/port/src/ditto_port/registry/contexts/strategy.py`
- Modify: `apps/port/src/ditto_port/registry/contexts/__init__.py`
- Modify: `apps/port/src/ditto_port/registry/__init__.py`
- Create: `apps/port/src/ditto_port/cli/commands/strategy.py`
- Modify: `apps/port/src/ditto_port/cli/main.py`

**Step 1: 实现最小 StrategyBundle**

- `StrategyBundle` 仅暴露 `StrategyFacade`。
- `create_strategy_bundle()` 使用单个 app container 获取 facade，并负责关闭容器。

**Step 2: 实现 CLI 命令组**

- `strategy research`
- `strategy recommend`
- `strategy backtest`

三个命令统一支持：
- `strategy-id`
- `trade-date` / `start-date` / `end-date`
- `version`
- `source`

输出先保持轻量，打印 run_id / artifact_dir / final_nav 等关键信息即可。

### Task 3: 绿测与总体验证

**Files:**
- Test: `apps/port/tests/unit/cli/commands/test_strategy_unit.py`
- Test: `apps/port/tests/unit/cli/test_market_commands.py`

**Step 1: 跑定向测试**

Run:

```bash
pixi run -e dev pytest apps/port/tests/unit/cli/commands/test_strategy_unit.py apps/port/tests/unit/cli/test_market_commands.py --no-cov -q
```

**Step 2: 跑全量门禁**

Run:

```bash
pixi run -e dev check
```
