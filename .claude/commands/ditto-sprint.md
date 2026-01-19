---
name: ditto-sprint
description: Sprint 规划与任务管理
---

# /ditto-sprint 命令

使用 `superpowers:brainstorming` + `superpowers:writing-plans` 管理 Sprint。

## 规范参考

- **流程规范**: [`.claude/rules/workflow.md`](.claude/rules/workflow.md)
- **架构规范**: [`.claude/rules/architecture.md`](.claude/rules/architecture.md)
- **SKILLS**: [`.claude/CLAUDE.md`](.claude/CLAUDE.md#⚠️-skills-执行规则)

## 子命令

| 命令 | 说明 |
|------|------|
| `/ditto-sprint [描述]` | 创建新 Sprint |
| `/ditto-sprint --list` | 查看任务状态 |
| `/ditto-sprint --next` | 下一个任务（自动调用 /ditto-plan） |
| `/ditto-sprint --status` | 进度报告 |

## 创建流程

### 1. 目标澄清
```
理解目标 → 明确验收 → 询问疑问
```

### 2. 任务拆分
- INVEST 原则
- 复杂度 S/M/L（XL 必须拆）
- 依赖关系

### 3. 复杂度速查

| 等级 | 文件 | 代码行 | 特征 |
|------|------|--------|------|
| S | 1 | <50 | 单文件 |
| M | 2-3 | 50-150 | 有模式 |
| L | 4-6 | 150-400 | 跨模块 |
| XL | >6 | >400 | **必须拆** |

**风险加权 +1 级**：PIT、Kill Switch、Schema 变更、外部 API

### 4. 输出
`docs/sprints/sprint-{name}.md`

## 工作流

```
/ditto-sprint → /ditto-plan → /ditto-dev → --next (循环)
```
