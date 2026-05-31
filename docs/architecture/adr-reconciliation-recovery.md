# ADR: Reconciliation Recovery Policy

**状态**: Accepted, updated with pure repair planning, persisted workflow state, and executor orchestration
**日期**: 2026-05-18；更新: 2026-05-31
**上下文**: `packages/execution/src/ditto_execution/reconciliation/`

## 背景

执行对账（reconciliation）是将期望状态（如策略信号推导的目标持仓）与实际状态（如券商回报的实际持仓）进行比对的过程。当检测到差异时，系统需要决定如何处理：是自动修复、人工介入，还是仅记录告警。

在量化交易系统中，自动修复引入的风险较高（错误修复可能导致更大的偏离），而检测逻辑本身是确定性且无副作用的。因此需要明确区分"检测"与"恢复"两个关注点。

## 决策

对账检测模块仅负责 **检测** 期望与实际之间的差异。
它 **不会** 自动修复或更新任何状态。

恢复（repair）分为四层：

1. `plan_repair()`：纯函数，把 `ReconciliationReport.diffs` 转换为 typed repair actions。
2. `SQLiteRepairWorkflowStore`：持久化 action、审批状态和执行记录，不直接修复交易状态。
3. `RepairActionExecutor`：消费 `ready` / `approved` action，执行状态门禁、handler dispatch、执行结果落库和可选 audit sink。
4. Repair handlers：面向具体动作的执行器。当前默认实现只有 read-only `BrokerRefreshRepairHandler`；真正修改本地订单/成交/账户状态的 handler 仍需显式实现和注入。

当前实现第 1、2、3 层，以及 read-only broker refresh handler。它们定义恢复语义、审批状态和执行编排，但不默认执行交易状态变更。

这意味着：
- `reconcile()` 是纯函数，无副作用
- 输出 `ReconciliationReport` 仅描述"发生了什么偏差"
- `plan_repair()` 也是纯函数，无副作用
- `SQLiteRepairWorkflowStore` 给 action 分配确定性 ID，并保存 `ready` / `pending_review` / `approved` / `rejected` / `executed` 状态
- 读操作类动作（如 broker refresh）可进入 `ready` 状态，并可由 `RepairActionExecutor` 通过 `BrokerRefreshRepairHandler` 查询 broker fills 后记录为 executed
- 写操作类动作（如导入额外成交、修正本地 fill、调整 order status）默认标记为 `requires_manual_review=True`
- 未审批的写操作不会被 executor dispatch；被拒绝的 action 也不会执行
- 写操作需要调用方显式注入 action handler，避免 reconciliation 包隐式绑定某个存储或 broker mutation 语义

## 后果

**正面**：
- 对账逻辑保持简单、可测试（纯函数，无副作用）
- 恢复策略可以独立演化，不影响检测逻辑
- repair action 为 executor、审计和人工审批提供统一语言
- 审批状态和执行结果已有 SQLite 持久化主干，可跨进程恢复
- executor 已有状态门禁、handler dispatch 和 audit sink 端口
- 调用方仍拥有完全的处理自主权

**负面**：
- 差异处理目前仍依赖调用方为写操作注入具体 mutating handler
- 人工干预场景下，操作员仍需要理解 action 的影响范围

**权衡**：当前阶段以检测准确性、审批安全和可审计恢复编排为优先，将真正修改订单/成交/账户状态的 handler 推迟到 broker conformance 扩展之后。

## 参考

- `packages/execution/src/ditto_execution/reconciliation/reconciler.py` — 对账核心逻辑
- `packages/execution/src/ditto_execution/reconciliation/repair.py` — 无副作用 repair planning
- `packages/execution/src/ditto_execution/reconciliation/executor.py` — repair action executor / handler / audit sink 端口
- `packages/execution/src/ditto_execution/reconciliation/types.py` — `ReconciliationReport` / `ReconciliationDiff` / `RepairPlan` / `RepairActionRecord` / `RepairExecutionResult` 类型定义
- `packages/execution/src/ditto_execution/storage/sqlite/reconciliation.py` — repair workflow SQLite 持久化
