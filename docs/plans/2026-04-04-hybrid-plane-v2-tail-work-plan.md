# Hybrid Plane V2 Tail Work Implementation Plan

> **状态**: ✅ 已完成（2026-04-04）
> 8 个任务全部完成。验证结果: 4356 tests passed, 21 importlinter contracts kept, 0 type errors.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 收掉 Hybrid Plane v2 剩余的架构尾巴，消除“设计文档 / ADR / 源码现状”之间的最后不一致点。

**Architecture:** 当前架构已经稳定并通过门禁，收尾不应再做大规模重构；应优先固化最终决策、清理半完成抽象、补齐事件与文档闭环。对源码影响大的项，只有在能显著提升边界清晰度时才继续推进。

**Tech Stack:** Python 3.13, polars, Dishka, import-linter, pytest, pixi

---

## 收尾优先级

### P0 必须收尾

1. 固化最终架构决策，停止“旧设计追代码”
2. 关闭 Orchestrator 半完成抽象
3. 关闭事件模型“定义已在、接线未全”的状态
4. 清理误导性的旧文案 / 旧命名

### P1 建议收尾

5. 明确 Interfaces registry 对 Data 的豁免边界
6. 同步 DI 设计文档到真实实现

### P2 可选清理

7. 归档或修正过时的完成度审计文档
8. 追加一份最终架构审计摘要

---

### Task 1: 固化最终架构决策

**目标：** 把已经被源码证明为最终形态的偏差，正式写回文档与 ADR，避免后续继续按旧设计返工。

**Files:**
- Modify: `docs/plans/2026-03-30-architecture-hybrid-plane-design.md`
- Modify: `docs/plans/2026-03-31-hybrid-plane-v2-migration-plan.md`
- Modify: `docs/adr/0006-hybrid-plane-v2-accepted-deviations.md`
- Modify: `docs/plans/2026-04-03-hybrid-plane-v2-completion-plan.md`

**需要固化的事实：**
- `DataProvider` 已从 Kernel 移到 `ditto_data.provider`
- `packages/engine/` 已完成目录重命名，不再是 `packages/core/`
- `forward_return_service` 的最终归属是 `ditto_app.query`
- `specs.py` 的最终归属是 `ditto_kernel.specs`
- `interfaces/testing.py` 已存在
- `interfaces/api/`、`packages/app/`、`data.di + app.providers + interfaces.registry.container` 是当前接受方案

**验收：**
- 不再存在“文档说未完成，但源码已完成”的条目
- ADR 与设计文档对同一事实不再互相矛盾

**Run:**
```bash
pixi run -e dev check
```

---

### Task 2: 关闭 Orchestrator 半完成抽象

**目标：** 不再保留“既想要形式化 Orchestrator，又只落了 alias / contract 壳子”的中间状态。

**Files:**
- Modify: `packages/engine/src/ditto_engine/orchestrator/__init__.py`
- Modify: `packages/engine/src/ditto_engine/orchestrator/protocol.py`
- Modify or Delete: `packages/engine/src/ditto_engine/orchestrator/contracts.py`
- Modify: `packages/engine/src/ditto_engine/backtest/engine.py`
- Test: `packages/engine/tests/unit/orchestrator/test_protocol_unit.py`
- Test: `packages/engine/tests/unit/orchestrator/test_backtest_orchestrator_unit.py`
- Test: `packages/engine/tests/unit/orchestrator/test_contracts_unit.py`

**推荐决策：**
- 推荐直接接受 `BacktestTradingOrchestrator = EngineLoop` 为 v2 最终方案
- 如果短期不准备把 `AlphaOutput` / `PortfolioOutput` 真正接入主链路，就删除这两个未接线 contract 与对应测试
- 如果决定保留 contract，则同一批次必须把它们真实接入 `EngineLoop -> pipeline/planner` 边界，不能继续只留测试壳子

**不推荐：**
- 再拆一个没有行为差异的 `orchestrator.py` 外壳类
- 保留仅被测试使用、主流程完全不消费的 contract

**验收：**
- `orchestrator/` 下不再有“只导出不消费”的死抽象
- 设计文档对 orchestrator 的描述与源码一致

**Run:**
```bash
pixi run -e dev test packages/engine/tests/unit/orchestrator -q
pixi run -e dev check
```

---

### Task 3: 关闭事件模型的未接线部分

**目标：** 让“已实现的事件”与“真实会被发布的事件”保持一致。

**Files:**
- Modify: `packages/engine/src/ditto_engine/events.py`
- Modify: `packages/engine/src/ditto_engine/backtest/engine.py`
- Modify: `packages/engine/src/ditto_engine/execution/brokerage.py`
- Modify: `packages/data/src/ditto_data/events.py`
- Modify: `packages/app/src/ditto_app/process/ingestion.py`
- Modify: `packages/app/src/ditto_app/process/quality.py`
- Test: `packages/engine/tests/unit/backtest/test_engine_events_unit.py`
- Test: `packages/engine/tests/unit/test_events.py`
- Test: `packages/data/tests/unit/test_data_events.py`

**推荐决策：**
- Engine 侧二选一：
  - 要么给 `OrderCanceled` / `PositionChanged` 增加真实 publish 点
  - 要么把它们降级为“预留事件”，从完成度口径里移除
- Data 侧二选一：
  - 要么在 ingestion / quality 流程里真实发布 `DataIngested` / `QualityCheckCompleted`
  - 要么明确它们暂为未来扩展点

**验收：**
- 不再出现“事件类存在，但仅测试实例化”的情况
- 事件完成度表述与运行时行为一致

**Run:**
```bash
pixi run -e dev test packages/engine/tests/unit/backtest/test_engine_events_unit.py -q
pixi run -e dev test packages/data/tests/unit/test_data_events.py -q
pixi run -e dev check
```

---

### Task 4: 清理误导性旧文案 / 旧命名

**目标：** 移除会误导维护者的旧术语与过期说明。

**Files:**
- Modify: `packages/engine/src/ditto_engine/backtest/data_feed.py`
- Modify: `packages/data/src/ditto_data/query/provider.py`
- Modify: `packages/data/src/ditto_data/provider.py`
- Modify: `interfaces/src/ditto_interfaces/testing.py`

**清理重点：**
- `kernel.DataProvider` 旧表述
- `core 层` 旧表述
- `port/registry` 旧表述
- `AnyFrame` 在注释里的残留
- “Port 应用测试辅助模块” 等旧命名

**验收：**
- 关键源码注释与当前架构术语一致
- `rg -n "AnyFrame|core 层|port/registry|Port 应用" packages apps --glob '*.py'` 只剩有意保留的历史文档文本

**Run:**
```bash
pixi run -e dev check
```

---

### Task 5: 明确 Interfaces registry 的豁免边界

**目标：** 把当前仅存的 3 处 `interfaces -> data` 直连，定性为永久 Composition Root 豁免还是继续下沉。

**Files:**
- Modify: `.importlinter`
- Modify: `interfaces/src/ditto_interfaces/registry/contexts/bundle.py`
- Modify: `interfaces/src/ditto_interfaces/registry/contexts/ingestion.py`
- Modify: `interfaces/src/ditto_interfaces/registry/infra/config.py`
- Modify: `interfaces/CLAUDE.md`

**推荐决策：**
- 推荐保留 registry 范围豁免，不再为“形式上 100% 纯净”增加无价值包装层
- 但必须在 `CLAUDE.md` 和 ADR 中明确：只有 Composition Root 可以直接接触 Data service / quality 配置

**验收：**
- 团队对这 3 处依赖的性质有统一口径
- `.importlinter` 规则与文档说明一致

**Run:**
```bash
pixi run -e dev arch-check
```

---

### Task 6: 同步 DI 设计到真实实现

**目标：** 让 DI 设计文档不再描述并不存在的 `engine.di` / `analytics.di`。

**Files:**
- Modify: `docs/plans/2026-03-30-architecture-hybrid-plane-design.md`
- Modify: `docs/adr/0006-hybrid-plane-v2-accepted-deviations.md`
- Modify: `interfaces/src/ditto_interfaces/registry/container.py`
- Modify: `packages/app/src/ditto_app/providers.py`
- Modify: `packages/data/src/ditto_data/di/__init__.py`

**推荐口径：**
- 当前最终 DI 结构是：
  - `ditto_data.di`
  - `ditto_app.providers`
  - `ditto_interfaces.registry.container`
- 只有当 Engine/Analytics 未来真的出现可复用 Provider 聚合需求时，才补独立 `di.py`

**验收：**
- 文档与实现不再分叉
- 维护者不会再去找不存在的 `ditto_engine.di`

**Run:**
```bash
pixi run -e dev check
```

---

### Task 7: 修正或归档过时审计文档

**目标：** 把已经过时、会误导决策的审计文档收口。

**Files:**
- Modify or Archive: `docs/plans/2026-04-03-hybrid-plane-v2-completion-plan.md`
- Modify: `docs/plans/2026-04-03-hybrid-plane-v2-cleanup-and-decisions.md`
- Modify: `docs/plans/2026-04-02-hybrid-plane-v2-cleanup-plan.md`

**重点：**
- 删除“`packages/core/` 未改名”之类已失效结论
- 标记哪些差异已被后续提交消除
- 保留仍有效的风险项

**验收：**
- 团队读到的“最新完成度文档”不会再输出错误事实

---

### Task 8: 产出最终架构审计摘要

**目标：** 留下一份简短、可引用的最终总结，回答“v2 到底算不算完成”。

**Files:**
- Create: `docs/reviews/2026-04-04-hybrid-plane-v2-final-audit.md`

**内容结构：**
- 已完成目标
- 已接受偏差
- 剩余非阻塞项
- 最终结论：架构完成 / 待优化项 / 不建议继续大改

**验收：**
- 后续 PR / 讨论可直接引用该审计结论

---

## 推荐执行顺序

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7
8. Task 8

## 推荐 PR 划分

1. `docs: 固化 hybrid plane v2 最终决策`
2. `refactor: 收口 orchestrator 与事件模型`
3. `docs: 清理过时完成度文档并补最终审计`

## 最终验收

```bash
pixi run -e dev check
pixi run -e dev arch-check
```

Plan complete and saved to `docs/plans/2026-04-04-hybrid-plane-v2-tail-work-plan.md`.
