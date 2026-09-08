# Features 包指南

## 定位与依赖

因子、表达式、衍生数据、物化与评估平面。允许依赖 kernel/platform；禁止直接依赖 data 或 strategy/portfolio/risk/execution/backtest/analysis/application/apps。

## 关键不变量

- expression 不依赖 materialization；因子定义依赖 expression/spec，不依赖编排层。
- 市场输入由 application/backtest 注入，不通过直接依赖 data 获取。
- feature-owned storage/runtime 通过本包 contracts/Protocols 交互。
- rolling、shift、join、因子可见性与发布截止改动使用 `ditto-pit-safety`。

## 验证与参考

- `uv run --no-sync pytest packages/features/tests`
- `uv run --no-sync pytest -m pit`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [PIT skill](../../.agents/skills/ditto-pit-safety/SKILL.md)
