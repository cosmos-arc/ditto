---
name: ditto-dev
description: 基于计划执行TDD开发
---

# /dev 命令
1. Step one:
使用 `superpowers:brainstorming` 决策当前任务使用 `superpowers:subagent-driven-development` 或者 `superpowers:executing-plans` 方式进行执行
2. Step two:
任务中使用 `superpowers:test-driven-development` + `python-development:python-pro` + `superpowers:systematic-debugging` 模式进行具体开发、测试、调式工作。

**必须**：子代理严格遵循工具使用、编码规范、架构设计规约！！！

## 输入

$ARGUMENTS（计划文件路径，默认取 `docs/plans/` 最新）

## 执行流程

### 1. 准备
- 读取计划文件，确认待执行任务
- 检查环境：Python、pytest、ruff 可用

### 2. TDD循环（每个任务）

```
┌─────────────────────────────────────────┐
│  RED     写失败测试 → 运行确认失败       │
│  GREEN   最小实现 → 运行确认通过         │
│  REFACTOR 优化代码 → 确保测试仍通过      │
└─────────────────────────────────────────┘
```

### 3. 任务完成后（每个）
- 运行 pre-commit
- 更新计划文件（标记 `[x]`）
- Git 提交（原子粒度，描述清晰）

### 4. 全部完成后
- 运行 ci-check 并解决所有问题
- 更新 README（如有新模块/接口/重要设计/上下游依赖说明）
- 输出进度报告

## 注意事项

- **先测试后实现**，不要跳过RED阶段
- **小步提交**，一个任务一个commit
- 遇到阻塞及时沟通，不要死磕

## 示例

```bash
/dev                                    # 执行最新计划
/dev docs/plans/2024-01-15-momentum.md  # 指定计划
```
