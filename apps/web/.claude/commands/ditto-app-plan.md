---
name: ditto-app-plan
description: 生成结构化开发任务规划
---

# /ditto-app-plan 命令

基于输入需求分析并生成开发计划。

## 规范参考

- **流程规范**: [workflow.md](../rules/workflow.md)
- **架构规范**: [architecture.md](../rules/architecture.md)

## 输入

`$ARGUMENTS` - Sprint Phase 或需求描述

## 执行流程

### 1. 需求理解
使用`/brainstorming`理解和深入思考 → 询问疑问并要求用户澄清

### 2. 任务拆解
- 原子任务（单一职责）
- 复杂度 S/M/L（XL 必须拆）
- 依赖关系 + 执行顺序
- 明确验收标准

#### 2.1 复杂度速查

| 等级 | 文件 | 代码行 | 特征 |
|------|------|--------|------|
| S | 1 | <50 | 单文件 |
| M | 2-3 | 50-150 | 有模式 |
| L | 4-6 | 150-400 | 跨模块 |
| XL | >6 | >400 | **必须拆** |

### 3. 生成计划
使用`/writing-plans`输出到 `docs/plans/{date}-{feature}.md`

```markdown
# {feature}

## 概述
- Sprint: {id} | Phase: {name}
- 创建: {timestamp}

## 技术方案
{关键决策}

## 任务清单
- [ ] Task: {desc} `[S]`
  - 验收: {标准}
  - 文件: {files}
```

## 硬性规则

- 每个任务 → 测试要求
- API 集成 → MSW mock 要求
- 新组件 → 检查 shadcn/ui 是否已有
