# Ditto 架构规范索引

> 本目录记录跨包架构规则、命名词典、抽象层级和扩展放置标准。它面向后续 agent 与个人开发者，回答"新代码应该放哪里、叫什么、依赖谁、不能做什么"。

## 当前架构与放置

[Agent 快速参考](agent-context-pack.md) 是当前依赖方向、包归属和放置规则的单一阅读入口；
[`.importlinter`](../../.importlinter) 与各包 AGENTS 是机器边界和局部约束来源。
Python 包含 `agent` 在内共 13 个 distribution，Web 独立构建。
能力包是并列平面，不能把 import-linter 的技术排序理解为业务依赖链。

新增概念或调整抽象时使用[边界与抽象标准](boundaries-and-abstraction-standards.md)。
命令和按风险验证见[测试指南](../engineering/testing.md)，JSON 例外与跨栈不变量见
[根 AGENTS](../../AGENTS.md)。

## 架构文档

| 文档 | 状态 | 用途 |
|---|---|---|
| [agent-context-pack.md](agent-context-pack.md) | Active | Agent 快速参考：依赖图、边界规则、关键路径 |
| [boundaries-and-abstraction-standards.md](boundaries-and-abstraction-standards.md) | Active | 分层、模块化、命名、抽象层级一致性与扩展方式规范 |
| [capability-maturity.md](capability-maturity.md) | Active | 能力成熟度分级（initial-focus / experimental / infrastructure / debug）|
| [public-api-and-guard-backlog.md](public-api-and-guard-backlog.md) | Active | Public API 收敛与架构门禁 backlog |
| [public-api-maturity.md](public-api-maturity.md) | Active | Public API 成熟度登记（kernel/features/application stable/candidate/internal 三级） |
| [2026-05-31-current-architecture-review.md](archive/2026-05-31-current-architecture-review.md) | 📦 Historical | 一次性源码全局/分模块架构 review 快照（已归档） |

### ADR（架构决策记录）

| 文档 | 主题 |
|---|---|
| [adr-eventname-vs-event-type.md](adr-eventname-vs-event-type.md) | EventName catalog vs 硬编码 event_type |
| [adr-kernel-trading-types.md](adr-kernel-trading-types.md) | Kernel trading 域类型归属 |
| [adr-reconciliation-recovery.md](adr-reconciliation-recovery.md) | 对账修复策略 |
| [adr-research-artifact-manifest.md](adr-research-artifact-manifest.md) | 研究 artifact manifest 设计 |
| [adr-runtime-spine.md](adr-runtime-spine.md) | 运行时 spine 架构 |

## 各包规范索引

| 包 | AGENTS.md | 定位 |
|---|---|---|
| kernel | [packages/kernel/AGENTS.md](../../packages/kernel/AGENTS.md) | 共享内核（类型 + Protocol） |
| platform | [packages/platform/AGENTS.md](../../packages/platform/AGENTS.md) | 横切基础设施 |
| data | [packages/data/AGENTS.md](../../packages/data/AGENTS.md) | 数据平台 |
| features | [packages/features/AGENTS.md](../../packages/features/AGENTS.md) | 因子与表达式 |
| strategy | [packages/strategy/AGENTS.md](../../packages/strategy/AGENTS.md) | 策略定义与信号 |
| portfolio | [packages/portfolio/AGENTS.md](../../packages/portfolio/AGENTS.md) | 组合构建与管理 |
| risk | [packages/risk/AGENTS.md](../../packages/risk/AGENTS.md) | 风险管理 |
| execution | [packages/execution/AGENTS.md](../../packages/execution/AGENTS.md) | 交易执行 |
| backtest | [packages/backtest/AGENTS.md](../../packages/backtest/AGENTS.md) | 回测引擎 |
| analysis | [packages/analysis/AGENTS.md](../../packages/analysis/AGENTS.md) | 研究分析 |
| application | [packages/application/AGENTS.md](../../packages/application/AGENTS.md) | 应用编排（CQRS） |
| agent | [packages/agent/AGENTS.md](../../packages/agent/AGENTS.md) | 模型运行、工具、审批与回放 |
| apps | [apps/backend/AGENTS.md](../../apps/backend/AGENTS.md) | 应用入口 |

## 使用方式

开发或审查前先阅读对应包的 `AGENTS.md`，再用本目录文档判断跨包边界和抽象层级。若两者出现冲突，以当前代码门禁和最新 `AGENTS.md` 为执行约束，并补充 ADR 或修订本文档。
