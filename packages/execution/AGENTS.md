# Execution 包指南

## 定位与依赖

交易执行平面，负责 OMS、券商 gateway、成交、A 股执行现实、审计与对账。允许依赖 kernel/platform/portfolio；禁止依赖 data/features/strategy/risk/backtest/analysis/application/apps。

## 关键不变量

- Broker Gateway 只表达 Paper 模拟与 recording wrapper；本产品不实现或装配真实券商 adapter。
- 订单、成交和审计状态变化必须可追踪，不允许静默吞错。
- A 股 T+1、涨跌停、费用与滑点语义集中在 execution reality。
- 交易语义变化使用 `ditto-test-first`；高风险 diff 完成后使用 `ditto-change-review`。

## 验证与参考

- `pixi run -e dev pytest packages/execution/tests`
- `pixi run -e dev arch-check`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [测试指南](../../docs/engineering/testing.md)
