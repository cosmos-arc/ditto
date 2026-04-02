# 策略引擎 v3 治理收口计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将策略引擎 v3 从“功能基本完成”推进到“治理闭环、artifact 落盘、控制面成型、架构门禁通过”的可收口状态。

**Architecture:** 先解决边界违规和循环依赖，再补齐 RunManifest 与 artifact 实体落盘，最后补完 strategy run/version 控制面与 Port 编排闭环。所有任务都以最小增量推进，避免为了“重构美观”打断现有可运行主链。

**Tech Stack:** Python 3.13, polars, orjson, pytest, basedpyright, ruff, import-linter, pixi

---

## 概述

- 范围：v3 设计稿里尚未真正收口的治理面与交付面
- 基线：`docs/plans/2026-03-24-strategy-engine-v3-completion-audit-refresh.md`
- 核心约束：
  - 先过边界，再谈“完成”
  - TDD 驱动
  - 每个任务保持 2-5 分钟颗粒度
  - 每阶段结束都跑 `pixi run -e dev check`

### 当前真实阻塞

1. `pixi run -e dev arch-check` 失败
2. `RunManifest` 仍是骨架版
3. artifact 只存 metadata，未落实体文件
4. strategy version/run 控制面未形成闭环

---

## Task 1: 修复 DataHub -> Core 审计依赖

**Files:**
- Modify: `packages/data/src/ditto_data/services/audit/execution_audit_service.py`
- Create: `packages/data/src/ditto_data/models/strategy_audit.py`
- Modify: `packages/data/src/ditto_data/models/__init__.py`
- Modify: `packages/data/tests/unit/services/test_execution_audit_service_unit.py`
- Test: `packages/data/tests/unit/services/test_execution_audit_service_unit.py`

**Step 1: 写失败测试，锁定 DataHub 审计服务不再依赖 Core 记录类型**

- 在 `test_execution_audit_service_unit.py` 中新增测试，改为使用 DataHub 本地 DTO 或 dict payload 创建记录
- 明确测试 `save_risk_log()` / `save_pre_trade_log()` 的输入契约

**Step 2: 运行单测确认当前契约不满足**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/services/test_execution_audit_service_unit.py -v
```

Expected:

- 现有测试需要调整或新增测试失败

**Step 3: 在 DataHub 定义本地审计 DTO**

- 在 `strategy_audit.py` 中新增：
  - `AuditRecordType`
  - `RiskScanPayload`
  - `PreTradeDecisionPayload`
- DTO 只保留持久化所需字段，不反向依赖 Core 枚举

**Step 4: 调整 ExecutionAuditService 输入契约**

- 让 `ExecutionAuditService` 接收：
  - DataHub 本地 DTO
  - 或规范化后的 `dict[str, object]`
- 服务内部只做序列化与查询，不 import `ditto_core.backtest.audit.records`

**Step 5: 调整测试与序列化断言**

- 更新 `severity` / `action_taken` 序列化断言
- 保持 SQLite schema 不变

**Step 6: 运行 DataHub 单测**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/services/test_execution_audit_service_unit.py -v
```

Expected:

- 全部通过

**Step 7: 运行架构检查确认该违规消失**

Run:

```bash
pixi run -e dev arch-check
```

Expected:

- `ditto_data.services.audit.execution_audit_service -> ditto_core.backtest.audit.records` 相关违规消失

**Step 8: Commit**

```bash
git add packages/data/src/ditto_data/models/strategy_audit.py
git add packages/data/src/ditto_data/models/__init__.py
git add packages/data/src/ditto_data/services/audit/execution_audit_service.py
git add packages/data/tests/unit/services/test_execution_audit_service_unit.py
git commit -m "refactor: decouple execution audit persistence from core records"
```

---

## Task 2: 打破 `.execution -> .strategy` 依赖

**Files:**
- Modify: `packages/core/src/ditto_core/execution/planner.py`
- Create: `packages/core/src/ditto_core/execution/targets.py`
- Modify: `packages/core/src/ditto_core/execution/__init__.py`
- Modify: `packages/core/tests/unit/execution/test_planner_unit.py`
- Test: `packages/core/tests/unit/execution/test_planner_unit.py`

**Step 1: 写失败测试，锁定 planner 只依赖 execution 边界对象**

- 为 planner 输入引入 execution 本地 target DTO，例如 `ExecutionTargetPortfolio`
- 单测覆盖：
  - 正常调仓
  - pending-aware diff
  - lock 阻止买入

**Step 2: 运行 planner 单测确认需要改造**

Run:

```bash
pixi run -e dev pytest packages/core/tests/unit/execution/test_planner_unit.py -v
```

**Step 3: 提取 execution 边界对象**

- 在 `execution/targets.py` 定义 execution 所需最小 target 结构
- 让 `planner.py` 依赖本地 DTO，而不是直接 import `TargetPortfolio`

**Step 4: 在调用层做转换**

- EngineLoop 或 Port 编排层将 `TargetPortfolio` 映射为 execution target DTO
- 保持 planner 算法逻辑不变

**Step 5: 跑 execution 单测**

Run:

```bash
pixi run -e dev pytest packages/core/tests/unit/execution/test_planner_unit.py -v
```

**Step 6: 跑架构检查**

Run:

```bash
pixi run -e dev arch-check
```

Expected:

- `.execution -> .strategy` 循环源头消失

**Step 7: Commit**

```bash
git add packages/core/src/ditto_core/execution/targets.py
git add packages/core/src/ditto_core/execution/planner.py
git add packages/core/src/ditto_core/execution/__init__.py
git add packages/core/tests/unit/execution/test_planner_unit.py
git commit -m "refactor: remove execution dependency on strategy target model"
```

---

## Task 3: 打破 `.portfolio -> .backtest` 依赖

**Files:**
- Modify: `packages/core/src/ditto_core/portfolio/comparison.py`
- Create: `packages/core/src/ditto_core/portfolio/report_views.py`
- Modify: `packages/core/src/ditto_core/portfolio/__init__.py`
- Modify: `packages/core/tests/unit/portfolio/test_comparison_unit.py`
- Test: `packages/core/tests/unit/portfolio/test_comparison_unit.py`

**Step 1: 写失败测试，锁定 comparison 只依赖组合分析视图**

- 为 `compare_reports()` 提供本地 report view 或 protocol
- 单测覆盖 run_id、delta、improved/degraded

**Step 2: 运行 comparison 单测**

Run:

```bash
pixi run -e dev pytest packages/core/tests/unit/portfolio/test_comparison_unit.py -v
```

**Step 3: 提取 portfolio 本地 report view**

- 在 `report_views.py` 定义 comparison 所需最小视图
- 只保留：
  - `run_id`
  - `final_nav`
  - `alpha_stats`
  - `aggregated_trade_stats`

**Step 4: 调整 comparison 入口**

- `compare_reports()` 接收本地 view/protocol
- 若需要，对 `BacktestReport` 在调用侧做适配

**Step 5: 跑 portfolio 单测**

Run:

```bash
pixi run -e dev pytest packages/core/tests/unit/portfolio/test_comparison_unit.py -v
```

**Step 6: 跑架构检查**

Run:

```bash
pixi run -e dev arch-check
```

Expected:

- `.portfolio -> .backtest` 循环源头消失

**Step 7: Commit**

```bash
git add packages/core/src/ditto_core/portfolio/report_views.py
git add packages/core/src/ditto_core/portfolio/comparison.py
git add packages/core/src/ditto_core/portfolio/__init__.py
git add packages/core/tests/unit/portfolio/test_comparison_unit.py
git commit -m "refactor: decouple portfolio comparison from backtest report"
```

---

## Task 4: 补全 RunManifest 真实治理字段

**Files:**
- Modify: `packages/core/src/ditto_core/backtest/manifest.py`
- Modify: `packages/core/src/ditto_core/backtest/engine.py`
- Modify: `packages/core/tests/unit/backtest/test_manifest_unit.py`
- Modify: `packages/core/tests/integration/backtest/test_reproducibility.py`
- Test: `packages/core/tests/unit/backtest/test_manifest_unit.py`
- Test: `packages/core/tests/integration/backtest/test_reproducibility.py`

**Step 1: 写失败测试，锁定 manifest 真实字段**

- 新增断言：
  - `engine_version` 从 `EngineConfig` 透传
  - `rule_resolution_policy == "as_of_date"`
  - `input_refs` 非空
  - `artifacts` 非空
  - `config_hash` 非空

**Step 2: 运行 manifest 相关测试确认失败**

Run:

```bash
pixi run -e dev pytest packages/core/tests/unit/backtest/test_manifest_unit.py packages/core/tests/integration/backtest/test_reproducibility.py -v
```

**Step 3: 调整 RunManifest 模型**

- 明确字段语义
- 将默认 `rule_resolution_policy` 改为 `"as_of_date"`
- 如无必要，不强推大规模类型升级；先对齐设计关键治理字段

**Step 4: 在 EngineLoop 中真实构建 manifest**

- 生成 `config_hash`
- 收集 `input_refs`
- 记录 `engine_version`
- 初始化 `artifacts`

**Step 5: 维持 canonical JSON 稳定性**

- 保证旧稳定性测试仍通过
- 不引入非确定性字段排序

**Step 6: 跑 manifest 与 reproducibility 测试**

Run:

```bash
pixi run -e dev pytest packages/core/tests/unit/backtest/test_manifest_unit.py packages/core/tests/integration/backtest/test_reproducibility.py -v
```

**Step 7: Commit**

```bash
git add packages/core/src/ditto_core/backtest/manifest.py
git add packages/core/src/ditto_core/backtest/engine.py
git add packages/core/tests/unit/backtest/test_manifest_unit.py
git add packages/core/tests/integration/backtest/test_reproducibility.py
git commit -m "feat: complete v3 run manifest governance fields"
```

---

## Task 5: 打通最小 artifact 实体落盘链路

**Files:**
- Modify: `apps/port/src/ditto_port/services/strategy/backtest_service.py`
- Create: `apps/port/src/ditto_port/services/strategy/artifact_writer.py`
- Modify: `apps/port/tests/unit/services/strategy/test_backtest_service_unit.py`
- Test: `apps/port/tests/unit/services/strategy/test_backtest_service_unit.py`

**Step 1: 写失败测试，锁定 artifact 不再只保存空 file_path**

- 验证 `BacktestService.run()` 后：
  - `StrategyArtifactRecord.file_path` 非空
  - 至少存在 `backtest_report.json`
  - 可选增加 `manifest.json`

**Step 2: 运行 BacktestService 单测**

Run:

```bash
pixi run -e dev pytest apps/port/tests/unit/services/strategy/test_backtest_service_unit.py -v
```

**Step 3: 实现最小 artifact writer**

- 新增 `artifact_writer.py`
- 先只支持：
  - `backtest_report.json`
  - `manifest.json`
  - `risk_log.json` 或 parquet 的最小替代
  - `pre_trade_log.json`

**Step 4: 在 BacktestService 中接入 writer**

- `build_report()` 后将结果落盘
- `StrategyArtifactRecord.file_path` 指向真实路径
- metadata 保持现有字段

**Step 5: 让 manifest 反向引用已落盘 artifact**

- 把写出的文件路径补进 `artifacts`

**Step 6: 跑 BacktestService 单测**

Run:

```bash
pixi run -e dev pytest apps/port/tests/unit/services/strategy/test_backtest_service_unit.py -v
```

**Step 7: Commit**

```bash
git add apps/port/src/ditto_port/services/strategy/artifact_writer.py
git add apps/port/src/ditto_port/services/strategy/backtest_service.py
git add apps/port/tests/unit/services/strategy/test_backtest_service_unit.py
git commit -m "feat: persist minimal strategy engine artifacts to disk"
```

---

## Task 6: 补 strategy version/run 控制面最小闭环

**Files:**
- Create: `packages/data/src/ditto_data/models/strategy_run.py`
- Create: `packages/data/src/ditto_data/services/strategy/strategy_run_service.py`
- Modify: `packages/data/src/ditto_data/services/strategy/__init__.py`
- Modify: `packages/data/src/ditto_data/scripts/schema.sql`
- Create: `packages/data/tests/unit/services/strategy/test_strategy_run_service_unit.py`
- Test: `packages/data/tests/unit/services/strategy/test_strategy_run_service_unit.py`

**Step 1: 写失败测试，定义 run 生命周期最小能力**

- `create_run()`
- `mark_running()`
- `mark_completed()`
- `mark_failed()`

**Step 2: 运行新单测确认失败**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/services/strategy/test_strategy_run_service_unit.py -v
```

**Step 3: 定义 DataHub 侧 strategy run record**

- 最小字段：
  - `run_id`
  - `strategy_id`
  - `strategy_version`
  - `mode`
  - `status`
  - `started_at`
  - `completed_at`
  - `error_message`

**Step 4: 增加最小 schema 与 service**

- 先不做过度抽象
- 用最小读写闭环支撑 Backtest / Recommendation 编排

**Step 5: 跑 DataHub 单测**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/services/strategy/test_strategy_run_service_unit.py -v
```

**Step 6: Commit**

```bash
git add packages/data/src/ditto_data/models/strategy_run.py
git add packages/data/src/ditto_data/services/strategy/strategy_run_service.py
git add packages/data/src/ditto_data/services/strategy/__init__.py
git add packages/data/src/ditto_data/scripts/schema.sql
git add packages/data/tests/unit/services/strategy/test_strategy_run_service_unit.py
git commit -m "feat: add minimal strategy run control plane"
```

---

## Task 7: 将 Port service 补成真正的控制面入口

**Files:**
- Modify: `apps/port/src/ditto_port/services/strategy/backtest_service.py`
- Modify: `apps/port/src/ditto_port/services/strategy/strategy_run_service.py`
- Modify: `apps/port/src/ditto_port/services/strategy/input_assembler.py`
- Create: `apps/port/tests/unit/services/strategy/test_backtest_orchestration_unit.py`
- Test: `apps/port/tests/unit/services/strategy/test_backtest_orchestration_unit.py`

**Step 1: 写失败测试，锁定 Port 编排职责**

- Backtest:
  - 创建 run
  - 运行引擎
  - 写 artifact
  - 更新 run 状态
- Recommendation:
  - 校验 spec
  - 生成 target
  - 写 signal artifact
  - 更新 run 状态

**Step 2: 运行 Port 单测确认失败**

Run:

```bash
pixi run -e dev pytest apps/port/tests/unit/services/strategy/test_backtest_orchestration_unit.py -v
```

**Step 3: 接入 DataHub run service**

- `BacktestService` / `StrategyRunService` 使用统一 run 生命周期
- 失败时写 `failed`
- 成功时写 `completed`

**Step 4: 保持现有 service API 尽量稳定**

- 避免一次性大改调用方
- 优先在内部接入新依赖

**Step 5: 跑 Port 单测**

Run:

```bash
pixi run -e dev pytest apps/port/tests/unit/services/strategy/test_backtest_orchestration_unit.py apps/port/tests/unit/services/strategy/test_backtest_service_unit.py apps/port/tests/unit/services/strategy/test_strategy_run_service_unit.py -v
```

**Step 6: Commit**

```bash
git add apps/port/src/ditto_port/services/strategy/backtest_service.py
git add apps/port/src/ditto_port/services/strategy/strategy_run_service.py
git add apps/port/src/ditto_port/services/strategy/input_assembler.py
git add apps/port/tests/unit/services/strategy/test_backtest_orchestration_unit.py
git commit -m "feat: wire strategy engine services into control plane lifecycle"
```

---

## Task 8: 文档收尾与 superseded 标记

**Files:**
- Modify: `docs/plans/2026-03-24-strategy-engine-v3-completion-analysis.md`
- Modify: `docs/plans/2026-03-24-strategy-engine-v3-remaining-tasks.md`
- Modify: `docs/plans/2026-03-24-strategy-engine-v3-audit-fixes.md`
- Modify: `packages/core/src/ditto_core/strategy/README.md`
- Modify: `packages/core/src/ditto_core/portfolio/README.md`

**Step 1: 给旧分析文档增加 superseded 说明**

- 明确指出：
  - 哪些条目已完成
  - 哪些结论过时
  - 应优先参考新的刷新版审计

**Step 2: 决定 README 策略**

- 二选一：
  - 真归档
  - 保留源码旁 README，并在设计文档中承认该偏离

推荐：

- **保留 README，更新设计文档承认偏离**

因为源码旁文档通常比归档更利于维护。

**Step 3: 跑最小检查**

Run:

```bash
pixi run -e dev test --fast
```

**Step 4: Commit**

```bash
git add docs/plans/2026-03-24-strategy-engine-v3-completion-analysis.md
git add docs/plans/2026-03-24-strategy-engine-v3-remaining-tasks.md
git add docs/plans/2026-03-24-strategy-engine-v3-audit-fixes.md
git add packages/core/src/ditto_core/strategy/README.md
git add packages/core/src/ditto_core/portfolio/README.md
git commit -m "docs: refresh strategy engine v3 completion status and rollout plan"
```

---

## 执行顺序

```text
Task 1  DataHub 审计解耦
  ↓
Task 2  去掉 execution -> strategy
  ↓
Task 3  去掉 portfolio -> backtest
  ↓
Task 4  补全 RunManifest
  ↓
Task 5  打通 artifact 实体落盘
  ↓
Task 6  strategy run 控制面
  ↓
Task 7  Port 编排收口
  ↓
Task 8  文档收尾
```

### 关键路径

```text
Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5 -> Task 6 -> Task 7
```

### 并行机会

- Task 4 与 Task 6 可在 Task 1-3 完成后并行
- Task 8 可在 Task 5 之后由独立会话并行整理

---

## 验收门禁

每个主要阶段后运行：

```bash
pixi run -e dev check
pixi run -e dev arch-check
```

### 最终验收标准

- [ ] `pixi run -e dev test --fast` 通过
- [ ] `pixi run -e dev arch-check` 通过
- [ ] `pixi run -e dev check` 通过
- [ ] `ExecutionAuditService` 不再依赖 Core 审计记录
- [ ] `.execution -> .strategy` 循环解除
- [ ] `.portfolio -> .backtest` 循环解除
- [ ] `RunManifest` 包含真实治理字段
- [ ] 至少一套最小 artifact 文件真实落盘
- [ ] strategy run 生命周期可追踪
