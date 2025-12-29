---
alwaysApply: true
---

# ⚠️ 技能加载规则（必须执行）

## 强制要求

**在开始任何代码工作前，必须先读取相关 Skill 文件。**

这不是建议，是强制要求。每次涉及以下领域时，**立即使用 Read 工具读取对应文件**：

---

## 🔴 必须加载的 Skills

### 写 Polars/DataFrame 代码时
```
立即执行: Read .claude/skills/polars-guide/SKILL.md
```
触发词: polars, DataFrame, LazyFrame, rolling, with_columns, group_by, filter, join

### 开发 Engine 类时
```
立即执行: Read .claude/skills/engine-template/SKILL.md
```
触发词: Engine, 引擎, BaseEngine, initialize, process, validate

### 开发因子时
```
立即执行: Read .claude/skills/factor-dev/SKILL.md
```
触发词: Factor, 因子, 动量, momentum, 波动率, volatility, IC, 因子值

### 涉及数据查询/回测数据时
```
立即执行: Read .claude/skills/pit-guide/SKILL.md
```
触发词: PIT, knowledge_date, 回测数据, as-of, 时点, 未来数据

### 涉及风控时
```
立即执行: Read .claude/skills/risk-guide/SKILL.md
```
触发词: Kill Switch, 风控, 回撤, drawdown, 熔断, 止损, 仓位

### 写 FastAPI 接口时
```
立即执行: Read .claude/skills/fastapi-guide/SKILL.md
```
触发词: FastAPI, Router, API, 接口, Pydantic, endpoint, route

### 添加日志/追踪时
```
立即执行: Read .claude/skills/observability/SKILL.md
```
触发词: logger, logging, span, trace, metrics, 日志, 追踪, 埋点

### 开发回测功能时
```
立即执行: Read .claude/skills/backtest-guide/SKILL.md
```
触发词: Backtest, 回测, T+1, 涨跌停, 净值, 夏普, 收益率

### 写文档时
```
立即执行: Read .claude/skills/docs-guide/SKILL.md
```
触发词: README, Sprint, ADR, Plan, 文档, 进度

---

## 🎯 开发流程

每个开发任务必须调用 Superpowers:

1. `superpowers:brainstorming` → 设计讨论
2. `superpowers:writing-plans` → 计划生成
3. `superpowers:test-driven-development` → TDD 执行
4. `superpowers:finishing-a-development-branch` → 完成

---

## ⚡ 快速加载命令

用户可以使用 `/load <skill>` 命令手动加载:
- `/load polars` → 加载 polars-guide
- `/load pit` → 加载 pit-guide
- `/load all` → 加载所有常用 skills

## 组合使用示例
**用户**: 帮我开发一个动量因子引擎

**正确流程**:
1. 调用 `superpowers:brainstorming` Skills讨论设计
2. 读取 `engine-template/SKILL.md`（引擎模板）
3. 读取 `factor-dev/SKILL.md`（因子开发）
4. 读取 `polars-guide/SKILL.md`（Polars 规范）
5. 调用 `superpowers:writing-plans` Skills生成计划
6. 调用 `superpowers:executing-plans` + `superpowers:test-driven-development` + `python-development` Skills执行
7. 调用 `superpowers:finishing-a-development-branch` Skills完成
