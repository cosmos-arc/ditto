# ADR: Reconciliation Recovery Policy

**状态**: Accepted
**日期**: 2026-05-18
**上下文**: `packages/execution/src/ditto_execution/reconciliation/reconciler.py`

## 决策

对账模块仅负责 **检测** 期望与实际之间的差异。
它 **不会** 自动修复或更新任何状态。
恢复（repair）是一个独立的关注点，留给未来的实现。

## 理由

这意味着：
- `reconcile()` 是纯函数，无副作用
- 输出 `ReconciliationReport` 仅描述"发生了什么偏差"
- 调用方决定如何处理差异（告警、人工干预、或未来的自动修复流程）

## 影响

- 对账逻辑保持简单、可测试
- 恢复策略可以独立演化，不影响检测逻辑
- 调用方拥有完全的处理自主权
