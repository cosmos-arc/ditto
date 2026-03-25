---
name: ditto-app-dev
description: 基于 TDD 的前端开发
---

# /ditto-app-dev 命令

基于计划文档执行 TDD 开发。

## 规范参考

- **流程规范**: [workflow.md](../rules/workflow.md)
- **架构规范**: [architecture.md](../rules/architecture.md)

## 输入

`$ARGUMENTS` - 计划文件路径（可选）

## 执行流程

### 1. 准备
```
读取计划 → 确认任务 → 环境检查 → 询问疑问
```

### 2. TDD 开发
- 1.使用`/brainstorming`理解和深入思考
- 2.并行多个任务探索相关代码、测试、架构设计
- 3.【强制】使用 Skill tool 逐个调用以下前端开发 Skills：
    - Skill: `brainstorming`
    - Skill: `test-driven-development`
    - Skill: `subagent-driven-development`
- 4.使用`code-simplifier:code-simplifier`进行代码简化

遵循 [workflow.md](../rules/workflow.md)：
```
理解代码 → RED → GREEN → SIMPLIFIER -> REFACTOR
```

### 3. 验证完成
调用 `verification-before-completion`

### 4. 文档更新
- 更新计划文档
- 更新 README.md 文档

## 禁止

- ❌ 跳过 RED 阶段
- ❌ 连续 Edit（Read/Edit 比 < 2.0）
- ❌ 不调用 systematic-debugging 就重试
- ❌ 跳过 verification-before-completion

## 示例

```bash
/ditto-app-dev                                    # 最新计划
/ditto-app-dev docs/plans/2026-01-19-xxx.md       # 指定计划
```
