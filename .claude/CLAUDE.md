# Ditto - 量化交易系统

> ETF 轮动 + A股智能选股

## ⚠️ 重要：开始工作前必读

**在写任何代码前，必须先读取相关的 Skill 文件！**

使用 `/load <skill>` 命令或直接 Read 对应文件：
- 写 Polars 代码 → `/load polars` 或 Read `.claude/skills/polars-guide/SKILL.md`
- 涉及数据查询 → `/load pit` 或 Read `.claude/skills/pit-guide/SKILL.md`
- 涉及风控 → `/load risk` 或 Read `.claude/skills/risk-guide/SKILL.md`

## 快速开始

1. **开发流程**：遵循 Superpowers 工作流
2. **领域知识**：查阅 `.claude/skills/` 下的 Skill 文件
3. **硬性规则**：查阅 `.claude/rules/` 下的 Rule 文件

## 核心约束

### 必须遵守

- **语言**：尽量使用中文用于回复、文档、Commit及PR内容
- **分支规范**：从main分支拉取开发分支开发，完成想main分支提交PR
- **TDD**：先写测试，再实现
- **PIT 安全**：`closed="left"`，knowledge_date
- **Kill Switch**：三级风控机制
- **六核心依赖**：polars / duckdb / sqlite / fastapi / prefect / opentelemetry

### 禁止

- `import pandas`
- `rolling_mean(20)` 不指定 closed
- 跳过风控检查
- 直接在 main 分支开发
- 直接提交 main

## 开发流程

```
superpowers:brainstorming     → 设计讨论
superpowers:writing-plans     → 计划生成
superpowers:test-driven-development → TDD 执行
superpowers:finishing-a-development-branch → 完成
```

## 领域 Skills

| 场景 | Skill |
|------|-------|
| Polars 代码 | `.claude/skills/polars-guide/SKILL.md` |
| Engine 开发 | `.claude/skills/engine-template/SKILL.md` |
| 因子开发 | `.claude/skills/factor-dev/SKILL.md` |
| PIT 数据 | `.claude/skills/pit-guide/SKILL.md` |
| 风控 | `.claude/skills/risk-guide/SKILL.md` |
| FastAPI | `.claude/skills/fastapi-guide/SKILL.md` |
| 可观测性 | `.claude/skills/observability/SKILL.md` |
| 回测 | `.claude/skills/backtest-guide/SKILL.md` |
| 文档规范 | `.claude/skills/docs-guide/SKILL.md` |

## 文档更新

| 触发条件 | 必须更新 |
|----------|----------|
| 新建/修改模块 | `packages/xxx/README.md` |
| 任务状态变更 | `docs/sprints/sprint-XX.md` |
| 复杂任务开始 | `docs/plans/YYYY-MM-DD-name.md` |
| 架构决策 | `docs/adr/NNNN-title.md` |

## 常用命令

```bash
pixi run -e dev test-unit #单元测试（快速，无覆盖率）
pixi run -e dev quick-check # 快速检查（开发时用，自动修复）
pixi run -e dev pre-push-check # 提交前检查（比 quick-check 更严格）
pixi run -e dev ci-check # CI 完整检查（模拟 CI 流程）
```
