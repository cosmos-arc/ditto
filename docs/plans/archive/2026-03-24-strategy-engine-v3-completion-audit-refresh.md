# 策略引擎 v3 完成度审计（刷新版）

**日期**: 2026-03-24
**审计范围**:
- `docs/plans/2026-03-21-strategy-engine-system-design-v3.md`
- `docs/plans/2026-03-24-strategy-engine-v3-completion-analysis.md`
- `docs/plans/2026-03-24-strategy-engine-v3-remaining-tasks.md`
- `docs/plans/2026-03-24-strategy-engine-v3-audit-fixes.md`
- 当前工作树实现与测试

**结论一句话**:
策略引擎 v3 在“功能闭环”层面已接近完成，但在“治理闭环、artifact 落盘、控制面收口、架构门禁”层面仍未收尾，不能视为 fully complete。

---

## 一、刷新后的总体判断

### 1.1 当前状态

| 维度 | 结论 | 说明 |
|------|------|------|
| 功能闭环 | **大体完成** | 决策、执行、回测、审计收集、A 股规则、4 个模板均已落地 |
| 测试状态 | **基本稳定** | `pixi run -e dev test --fast` 通过，3959 tests passed |
| 治理闭环 | **未完成** | RunManifest 仍是骨架版，artifact 持久化链路不完整 |
| 控制面 | **部分完成** | spec/artifact record 有了，但 strategy version/run 治理未完整落地 |
| 架构门禁 | **未通过** | `pixi run -e dev arch-check` 失败，`pixi run -e dev check` 非零退出 |

### 1.2 与 3 月 24 日旧分析文档的关系

旧文档已经出现两类漂移：

1. **低估已完成功能**
   - `Account.apply_fill()` 已实现
   - `FlatToFlatTradeBuilder` 已实现
   - `audit/` 子目录已拆分
   - `ExecutionAuditService` 已实现
   - `BacktestReport.risk_log / pre_trade_log` 已补齐
   - `BacktestService / StrategyRunService / StrategyInputAssembler` 已实现

2. **高估治理收口程度**
   - `RunManifest + RuleRefs` 只完成了“收集和序列化骨架”，未完成设计稿要求的完整治理字段和真实落盘
   - `StrategyArtifactService` 只持久化了少量 metadata，未形成设计稿定义的完整 artifact 目录与文件链路
   - `arch-check` 实际失败，旧文档中的“门禁通过”结论已不成立

---

## 二、已完成项（以当前代码为准）

### 2.1 核心功能已落地

- `accounting/` 核心契约已完成，且 `Account.apply_fill()` 已从 brokerage 中抽出
- `strategy/` 决策层已完成，4 个模板全部存在，`RiskLockFilter` 和 cooldown 语义均已落地
- `execution/` 已具备 pending-aware planner、完整 A 股规则、FillOutcome、FIFO 与 FLAT_TO_FLAT
- `backtest/` 已具备 EngineLoop、rolling pre-trade、post-trade risk、audit collector、三层统计
- `datahub/services/audit/ExecutionAuditService` 已完成 SQLite 持久化
- `apps/port/services/strategy/` 三个 service 已存在并有单元测试

### 2.2 已完成但旧文档仍标记为待办的项

| 项目 | 当前状态 | 证据 |
|------|---------|------|
| `Account.apply_fill()` | 已完成 | `packages/core/src/ditto_core/accounting/account.py` |
| `FlatToFlatTradeBuilder` | 已完成 | `packages/core/src/ditto_core/execution/trade_builder.py` |
| `audit/` 拆分 | 已完成 | `packages/core/src/ditto_core/backtest/audit/` |
| `ExecutionAuditService` | 已完成 | `packages/datahub/src/ditto_datahub/services/audit/execution_audit_service.py` |
| `BacktestReport` 审计字段 | 已完成 | `packages/core/src/ditto_core/backtest/statistics.py` |
| `StrategyInputAssembler` | 已完成 | `apps/port/src/ditto_port/services/strategy/input_assembler.py` |
| `BacktestService` | 已完成骨架 | `apps/port/src/ditto_port/services/strategy/backtest_service.py` |
| `StrategyRunService` | 已完成骨架 | `apps/port/src/ditto_port/services/strategy/strategy_run_service.py` |

---

## 三、仍未完成或只完成一半的部分

### 3.1 P0: 架构门禁未过

当前最大的现实阻塞不是功能缺失，而是**架构边界没有收口**。

本次验证结果：

```bash
pixi run -e dev test --fast   # 通过，3959 passed
pixi run -e dev arch-check    # 失败
pixi run -e dev check         # 非零退出
```

`arch-check` 暴露了三类问题：

1. **DataHub -> Core 违规**
   - `ditto_datahub.services.audit.execution_audit_service`
   - 直接依赖 `ditto_core.backtest.audit.records`

2. **Core 内循环依赖**
   - `.execution -> .strategy`
   - `.portfolio -> .backtest`

3. **已有老问题仍在**
   - `ditto_datahub.errors -> ditto_core.engine.errors`

其中第 1 类和策略引擎 v3 新增审计服务直接相关；第 2 类会影响长期演进，属于设计稿里“清晰边界、低耦合”尚未兑现。

### 3.2 P0: RunManifest 只做了骨架，不是设计稿完成态

`packages/core/src/ditto_core/backtest/manifest.py` 已定义 `RuleRef`、`RunManifest`、`serialize_manifest`，但和 v3 §12.4 仍有明显差距：

- `strategy_version` 仍是 `str`，不是设计中的版本化治理字段
- `rule_resolution_policy` 默认值为 `"first_observed"`，而 v3 设计要求 V1 使用 `"as_of_date"`
- `RunManifest` 的 `input_refs` / `parameter_overrides` / `artifacts` / `config_hash` / `engine_version` 虽然有字段，但引擎运行时并未真实构建完整值
- `engine.py` 当前生成 manifest 时仅填了 `run_id`、`strategy_id`、`rule_refs`、`created_at` 等少量字段

因此它目前更像“可序列化的 manifest 原型”，不是“治理平面完整落地”。

### 3.3 P0: Artifact 持久化链路没有真正打通

v3 §8.5 / §12 明确要求一整套 artifact 目录和文件：

- `manifest.json`
- `decision_frame.parquet`
- `signal_snapshot.parquet`
- `target_portfolio.parquet`
- `rebalance_plan.parquet`
- `order_log.parquet`
- `fill_log.parquet`
- `nav.parquet`
- `trade_log.parquet`
- `risk_log.parquet`
- `pre_trade_log.parquet`
- `backtest_report.json`

当前真实状态：

- `BacktestService` 只调用 `StrategyArtifactService.save_artifact(...)`
- 保存的仅是一条 `StrategyArtifactRecord`
- `file_path` 仍是空字符串
- 没有真正把上述 artifact 序列化到磁盘
- 没有把它们反写回 manifest 的 artifact 清单

这意味着“artifact-first”设计思想只落了一层 metadata，没有落到文件级闭环。

### 3.4 P1: 控制面只做了部分模型，没有形成完整治理

设计稿要求的控制面是：

- `strategy_version`
- `strategy_run`
- `strategy_artifact`

当前情况更接近：

- 有 `StrategySpecRecord`
- 有 `StrategyArtifactRecord`
- Core 里有 `StrategyVersion` / `StrategyRun` 数据类
- 但 DataHub schema / service 层没有形成完整的 strategy run/version 生命周期治理

所以“策略可定义/版本化/存储”只实现了前半段，没有完整跑通“版本发布 -> run 执行 -> artifact 关联”的控制面闭环。

### 3.5 P1: Port 层 service 已有骨架，但尚未成为真正的应用编排层

`BacktestService`、`StrategyRunService`、`StrategyInputAssembler` 已存在，这是实打实进展。

但和 v3 文档中的 Port 层定位相比仍有差距：

- `BacktestService` 仍要求外部直接注入 `pipeline / planner / brokerage / pre_trade_check / data_feed`
- `StrategyRunService` 仍直接接收 `Slice`
- 没有完整 control-plane orchestration
- 没有 strategy version/run 的服务级编排
- artifact 只存 metadata，不存实体文件

因此它们当前更像“可测试的 service skeleton”，而不是“产品化编排服务”。

### 3.6 P1: Signal 生命周期只做了模型和输入过滤，没有形成全链路

已完成部分：

- `SignalSnapshot.valid_until` 已在模型层存在
- `StrategyInputAssembler` 已支持 `valid_until < trade_date` 时让信号失效

未完成部分：

- 没有真正的 `SignalSnapshot` 生成、持久化、回放链路
- `StrategyRunService` 没有把 `valid_until` 驱动到 artifact 生命周期
- 设计稿里的“调仓日未执行自动过期”只实现了概念的一小部分

### 3.7 P1: StrategyComparisonReport 还是基础版

当前 `portfolio/comparison.py` 已有：

- 两次回测报告对比
- 指标 delta
- improved / degraded 判定

但还缺：

- 统计显著性检验
- 结构化改进建议
- artifact 展示闭环
- 与 `baseline_run_id` 的产品化使用方式

所以它已可用，但还没达到 v3 §2.4 的设计目标。

---

## 四、合理偏离与不合理偏离

### 4.1 合理偏离

以下偏离我认为是合理的，不必强行回到文档字面：

- `orders.py` 采用 re-export，而不是把 `Order` 真迁出去
- `MappingProxyType` 比文档里的一般 `Mapping` 更严格
- cooldown 语义提前落地
- 统计和审计拆为 `statistics.py + audit/`，而不是完全照文档示例

### 4.2 不合理或至少未收口的偏离

以下偏离会影响 v3 是否真正完成：

- `ExecutionAuditService` 放在 DataHub，却直接依赖 Core 审计记录类型
- `RunManifest` 设计字段已声明，但运行时只填了骨架
- artifact 目录设计已写清，但实际没有真实产物落盘
- Port / DataHub 控制面只做了 record/service 一部分，没有治理闭环
- `arch-check` 失败但旧文档仍写“通过”

---

## 五、刷新后的待办清单

### P0: 必须先做，否则 v3 不能收口

1. **修复架构门禁**
   - 解掉 `ExecutionAuditService -> ditto_core.backtest.audit.records`
   - 处理 `.execution -> .strategy`
   - 处理 `.portfolio -> .backtest`
   - 最终通过 `pixi run -e dev arch-check`

2. **补全 RunManifest**
   - 对齐 v3 §12.4 字段语义
   - 真实填充 `input_refs / parameter_overrides / artifacts / config_hash / engine_version`
   - 修正 `rule_resolution_policy` 语义
   - 让 manifest 不只是“能序列化”，而是真正可回放

3. **打通 artifact 实体落盘**
   - 至少先完成 `manifest.json / backtest_report.json / nav / trade_log / fill_log / risk_log / pre_trade_log`
   - 再补 pipeline / planner / brokerage 侧 parquet

### P1: 功能已存在，但要补成治理闭环

4. **补 strategy run/version 控制面**
   - strategy version 的持久化治理
   - run 记录与 artifact 的完整关联

5. **把 Port service 从 skeleton 补成真正的编排入口**
   - strategy spec/version/run 装配
   - artifact 实体写盘与索引
   - recommendation / backtest 的统一 run 语义

6. **补 StrategyComparisonReport 增强版**
   - baseline 管理
   - artifact 化
   - 统计解释与改进方向

### P2: 文档与收尾

7. **更新过时分析文档**
   - 旧的“剩余任务”文档应标记为已过时
   - 新增 superseded 说明，避免后续误判

8. **处理 README 归档漂移**
   - 决定是否按 v3 文档归档旧 README
   - 或者反向更新设计文档，承认 README 保留为源码旁文档

---

## 六、推荐执行顺序

建议不要再按旧思路继续“补零散功能”，而应切换为以下顺序：

1. **先修边界**
   - 这是当前唯一会直接阻塞“完成声明”的现实问题

2. **再补治理平面**
   - RunManifest
   - artifact 清单
   - strategy run/version 控制面

3. **最后做产品化补全**
   - Port service 完整编排
   - StrategyComparisonReport 增强
   - 文档归档整理

---

## 七、最终判断

### 7.1 完成度描述

如果用一句更准确的话描述现在的状态：

> **v3 的“运行内核”已经基本建成，但“治理与交付外壳”还没有完全封口。**

### 7.2 不建议再使用的旧结论

以下结论已经不准确，不建议后续继续引用：

- “ExecutionAuditService 未实现”
- “FlatToFlatTradeBuilder 未实现”
- “BacktestReport 缺审计字段”
- “Port 层 service 未实现”
- “RunManifest 已完整实现”
- “arch-check 已通过”

### 7.3 可以继续引用的结论

- 4 个策略模板已存在
- A 股规则核心实现已具备
- 快速测试可以通过
- v3 已有较高实现覆盖度

---

## 八、附：本次审计使用的最新验证结果

### 8.1 通过

```bash
pixi run -e dev test --fast
```

结果：

- `3959 passed in 46.49s`

### 8.2 失败

```bash
pixi run -e dev arch-check
pixi run -e dev check
```

结果：

- `arch-check` 失败
- `check` 非零退出
- 失败核心集中在分层边界和循环依赖，而不是策略引擎功能测试本身
