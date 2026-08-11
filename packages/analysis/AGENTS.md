# Analysis 包指南

## 定位与依赖

研究分析平面，负责研究数据集契约、experiments 领域与持久化合同和独立研究存储。允许依赖 `kernel`、`platform`；禁止依赖 data/features/strategy/portfolio/risk/execution/backtest，生产能力包也不得依赖 analysis。

## 关键不变量

- 研究 SQLite 与生产存储隔离。
- `experiments` 只拥有领域与持久化合同，不负责调度；`application` 在 research query 与 experiment 编排路径消费合同，`apps` 经 application facade/composition 使用。
- storage adapter 留在 `storage/sqlite/*` 叶模块，不从 experiments barrel 暴露。
- `reports`、`diagnostics`、`screeners` 是 reserved namespace，不得作为现有行为依赖。

## 验证与参考

- `pixi run -e dev pytest packages/analysis/tests`
- `pixi run -e dev arch-check`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [边界标准](../../docs/architecture/boundaries-and-abstraction-standards.md)
