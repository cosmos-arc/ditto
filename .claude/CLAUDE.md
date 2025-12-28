# Ditto - 量化交易系统

> ETF 轮动 + A股智能选股

## 快速开始

1. **开发流程**：遵循 Superpowers 工作流
2. **领域知识**：查阅 `.claude/skills/` 下的 Skill 文件
3. **硬性规则**：查阅 `.claude/rules/` 下的 Rule 文件

## 核心约束

### 必须遵守

- **TDD**：先写测试，再实现
- **PIT 安全**：`closed="left"`，knowledge_date
- **Kill Switch**：三级风控机制
- **六核心依赖**：polars / duckdb / sqlite / fastapi / prefect / opentelemetry

### 禁止

- `import pandas`
- `rolling_mean(20)` 不指定 closed
- 跳过风控检查
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

## 常用命令

```bash
pixi run -e dev quick-check # 快速检查（开发时用，自动修复）
pixi run -e dev test-unit # 单元测试（快速，无覆盖率）
pixi run -e dev pre-push-check # 提交前检查（比 quick-check 更严格）
pixi run -e dev ci-check # CI 完整检查（模拟 CI 流程）
```
