# 任务规划文档

> 复杂任务的详细拆解和实施计划

## 目录结构

```
plans/
├── sprint-01/
│   ├── task1-runtime-layer.md
│   └── task2-store-layer.md
├── sprint-02/
│   └── ...
└── sprint-03/
    └── ...
```

## 何时需要 Plan 文件？

| 情况 | 需要 Plan 文件？ | 说明 |
|------|-----------------|------|
| 简单任务 (S) | ❌ | Superpowers 即时规划 |
| 中等任务 (M)，单 Session 完成 | ❌ | Superpowers 即时规划 |
| 复杂任务 (L) | ✅ | 保存规划，便于跨 Session |
| 跨多天的任务 | ✅ | 保存规划，便于恢复上下文 |
| 架构设计决策 | ✅ | 作为 ADR 保存 |

## Plan 文件内容

一个好的 Plan 文件应该包含：

1. **任务概述** - 做什么、为什么
2. **依赖关系** - 前置条件
3. **实施步骤** - 详细拆解的 TaskItem
4. **验收标准** - 如何判断完成
5. **完成状态** - 进度追踪

## 与 Superpowers 的关系

```
Superpowers writing-plans 生成的计划
         ↓
  可以直接执行（简单任务）
         或
  保存到 plans/ 目录（复杂任务）
```

## 命名规范

```
{date}-{sprint}-task{n}-{name}.md

示例：
2025-12-22-sprint1-task1-runtime-layer.md
2025-12-26-sprint2-task1-regime-engine.md
```

或简化为：

```
task{n}-{name}.md

示例：
task1-runtime-layer.md
task2-store-layer.md
```
