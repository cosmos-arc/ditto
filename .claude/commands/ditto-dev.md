---
name: ditto-dev
description: 基于计划执行 TDD 开发
---

# /ditto-dev 命令

基于计划文档执行 TDD 开发。

## 规范参考

- **流程规范**: [`.claude/rules/workflow.md`](.claude/rules/workflow.md)
- **检查清单**: [`.claude/checklists/code-change.md`](.claude/checklists/code-change.md)
- **SKILLS**: [`.claude/CLAUDE.md`](.claude/CLAUDE.md#⚠️-skills-执行规则)

## 输入

`$ARGUMENTS` - 计划文件路径（可选）

## 执行流程

### 1. 准备
```
读取计划 → 确认任务 → 环境检查 → 询问疑问
```

### 2. 执行决策
调用 `superpowers:brainstorming` 决定：
- 单任务 → `subagent-driven-development`
- 多独立任务 → `dispatching-parallel-agents`（谨慎）

### 3. TDD 开发
遵循 [`.claude/rules/workflow.md`](.claude/rules/workflow.md)：
```
理解代码 → RED → GREEN → REFACTOR
```

### 4. 验证完成
调用 `verification-before-completion`

### 5. 文档更新
-更新计划文档
-更新README.md文档

## 禁止

- ❌ 跳过 RED 阶段
- ❌ 连续 Edit（Read/Edit 比 < 2.0）
- ❌ 不调用 systematic-debugging 就重试
- ❌ 跳过 verification-before-completion

## 示例

```bash
/ditto-dev                                    # 最新计划
/ditto-dev docs/plans/2026-01-19-xxx.md       # 指定计划
```
