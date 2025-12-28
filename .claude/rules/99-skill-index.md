---
alwaysApply: true
---

# 技能触发索引

> **Superpowers 负责开发流程，Ditto Skills 负责领域知识**

---

## 🎯 开发流程 → Superpowers

| 阶段 | 必须调用 |
|------|----------|
| 设计 | `superpowers:brainstorming` |
| 计划 | `superpowers:writing-plans` |
| 执行 | `superpowers:executing-plans` + `superpowers:test-driven-development` |
| 审查 | `superpowers:requesting-code-review` |
| 完成 | `superpowers:finishing-a-development-branch` |

---

## 🔧 领域知识 → Ditto Skills

| 触发条件 | 必须读取 |
|----------|----------|
| 写 Polars 代码 | `.claude/skills/polars-guide/SKILL.md` |
| 开发 Engine 类 | `.claude/skills/engine-template/SKILL.md` |
| 开发因子 | `.claude/skills/factor-dev/SKILL.md` |
| 数据查询/回测 | `.claude/skills/pit-guide/SKILL.md` |
| 风控逻辑 | `.claude/skills/risk-guide/SKILL.md` |
| FastAPI 接口 | `.claude/skills/fastapi-guide/SKILL.md` |
| 日志/追踪 | `.claude/skills/observability/SKILL.md` |
| 回测开发 | `.claude/skills/backtest-guide/SKILL.md` |

---

## 关键词匹配

```
Polars / DataFrame / LazyFrame   → polars-guide
Engine / 引擎 / BaseEngine       → engine-template
Factor / 因子 / IC               → factor-dev
PIT / knowledge_date             → pit-guide
Kill Switch / 风控 / 回撤        → risk-guide
FastAPI / Router / API           → fastapi-guide
logger / span / metrics          → observability
回测 / Backtest / T+1            → backtest-guide
```
