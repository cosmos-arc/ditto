---
name: sprint
description: Sprint 规划
---

# /sprint 命令

规划和管理 Sprint 任务。

## 流程

1. 收集待办任务
2. 评估复杂度和依赖
3. 拆分为可执行的开发任务
4. 为每个任务生成 TDD 计划

## Sprint 模板

### 任务拆分原则

- **单一职责**：每个任务只做一件事
- **可测试**：任务完成标准明确
- **时间盒**：单任务 ≤ 4 小时
- **独立性**：尽量减少任务间依赖

### 任务格式

```markdown
## Task: [任务名称]

**目标**: 一句话描述
**验收标准**:
- [ ] 标准 1
- [ ] 标准 2

**涉及 Skills**:
- polars-guide（如涉及 DataFrame）
- engine-template（如涉及引擎开发）

**TDD 计划**:
1. RED: 写什么测试
2. GREEN: 实现什么功能
3. REFACTOR: 优化什么
```

## 使用

```
/sprint 本周要完成动量因子引擎和回测 API
/sprint --list  查看当前任务
/sprint --next  开始下一个任务
```

## 与 Superpowers 集成

每个 Sprint 任务执行时：
1. `/dev [任务描述]` 启动开发流程
2. 自动触发 `superpowers:brainstorming`
3. 按 TDD 流程执行
