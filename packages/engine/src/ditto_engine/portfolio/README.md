# 组合构建模块 (portfolio/)

**版本**: v3.0
**最后更新**: 2026-03-24
**状态**: 核心功能已完成，比较报告为基础版

## 概要

投资组合构建层，提供权重分配、约束检查和回测报告比较能力。
当前 `compare_reports()` 已覆盖指标 delta 与 improved/degraded 基础输出；
统计显著性检验与更强解释型报告仍属于后续 backlog。

## 架构

```
portfolio/
├── allocation.py        # WeightAllocator Protocol + 内置实现
│                        #   EqualWeightAllocator / ScoreWeightAllocator / InverseVolAllocator
├── constraints.py       # ConstraintChecker + 内置约束
│                        #   MaxWeight / MinWeight / MaxPositions
├── stages.py            # AllocationStage / ConstraintStage (DecisionStage 适配器)
├── comparison.py        # compare_reports() — 回测报告比较
└── report_views.py      # ReportView — comparison 所需最小视图
```

## 核心概念

- **WeightAllocator**: Protocol，将得分转化为目标权重
- **ConstraintChecker**: 按 priority 升序执行约束列表
- **AllocationStage / ConstraintStage**: DecisionStage 适配器，可在 StrategyPipeline 中使用
- **compare_reports()**: 比较两次回测的 NAV 演变差异

## 依赖

- 上游: `ditto_data` (数据访问)
- 下游: 被 EngineLoop 消费

## 相关文档

- [v3 系统设计](../../../../docs/plans/2026-03-21-strategy-engine-system-design-v3.md)
- [治理收口计划](../../../../docs/plans/2026-03-24-strategy-engine-v3-governance-closeout-plan.md)
