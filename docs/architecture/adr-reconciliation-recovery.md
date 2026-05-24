# ADR: Reconciliation Recovery Policy

**状态**: Accepted
**日期**: 2026-05-18
**上下文**: `packages/execution/src/ditto_execution/reconciliation/reconciler.py`

## 背景

执行对账（reconciliation）是将期望状态（如策略信号推导的目标持仓）与实际状态（如券商回报的实际持仓）进行比对的过程。当检测到差异时，系统需要决定如何处理：是自动修复、人工介入，还是仅记录告警。

在量化交易系统中，自动修复引入的风险较高（错误修复可能导致更大的偏离），而检测逻辑本身是确定性且无副作用的。因此需要明确区分"检测"与"恢复"两个关注点。

## 决策

对账模块仅负责 **检测** 期望与实际之间的差异。
它 **不会** 自动修复或更新任何状态。
恢复（repair）是一个独立的关注点，留给未来的实现。

这意味着：
- `reconcile()` 是纯函数，无副作用
- 输出 `ReconciliationReport` 仅描述"发生了什么偏差"
- 调用方决定如何处理差异（告警、人工干预、或未来的自动修复流程）

## 后果

**正面**：
- 对账逻辑保持简单、可测试（纯函数，无副作用）
- 恢复策略可以独立演化，不影响检测逻辑
- 调用方拥有完全的处理自主权

**负面**：
- 差异处理目前完全依赖调用方实现，缺乏统一的恢复框架
- 人工干预场景下，操作员需要自行理解 diff 条目的含义

**权衡**：当前阶段以检测准确性为优先，将恢复策略的复杂度推迟到有明确需求时再设计。

## 参考

- `packages/execution/src/ditto_execution/reconciliation/reconciler.py` — 对账核心逻辑
- `packages/execution/src/ditto_execution/reconciliation/types.py` — `ReconciliationReport` / `DiffEntry` 类型定义
