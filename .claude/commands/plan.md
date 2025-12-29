---
name: plan
description: 基于当前 Sprint Phase 或用户描述，生成结构化的开发任务规划
---

# /plan 命令

基于当前 Sprint Phase 或用户描述，生成结构化的开发任务规划。

## 输入参数

$ARGUMENTS

## 执行流程

### Step 1: 需求理解与澄清

首先调用 `superpowers:brainstorming` skill 进行需求讨论：

1. **解析输入**：理解用户提供的 Sprint Phase 或需求描述
2. **上下文收集**：
   - 查看相关的 `docs/sprints/` 目录了解 Sprint 规划
   - 检查 `docs/architecture/` 了解系统架构约束
   - 查看 `CLAUDE.md` 确认项目规范和约定
3. **需求澄清**：如有不明确之处，向用户提问确认
4. **可行性分析**：评估技术可行性和潜在风险

### Step 2: 生成开发计划

确认需求后，调用 `superpowers:writing-plans` skill 生成计划：

1. **任务拆解**：将需求拆分为可执行的原子任务
2. **依赖分析**：识别任务间的依赖关系
3. **优先级排序**：按依赖关系和重要性排序
4. **估算复杂度**：为每个任务标注复杂度等级 (S/M/L)

## 输出格式

生成的计划保存到 `docs/plans/` 目录，命名格式：`{date}-{feature-name}.md`

```markdown
# 开发计划: {feature_name}

## 概述
- **Sprint**: {sprint_id}
- **Phase**: {phase_name}
- **创建时间**: {timestamp}
- **预估工作量**: {total_estimate}

## 背景与目标
{需求背景描述}

## 技术方案
{关键技术决策和架构考虑}

## 任务清单

### Phase 1: {phase_name}
- [ ] **Task 1.1**: {task_description} `[S]`
  - 验收标准: {acceptance_criteria}
  - 相关文件: {related_files}
- [ ] **Task 1.2**: {task_description} `[M]`
  ...

### Phase 2: {phase_name}
...

## 风险与依赖
- **风险**: {identified_risks}
- **外部依赖**: {external_dependencies}

## 验收标准
{overall_acceptance_criteria}
```

## 注意事项

1. **Point-in-Time 安全**：确保所有数据操作计划都考虑 PIT 约束
2. **三层风控**：涉及交易逻辑时必须考虑 Kill Switch 机制
3. **测试优先**：每个任务都应包含对应的测试要求
4. **增量交付**：计划应支持增量开发和验证
