# Strategy 包指南

## 定位与依赖

策略规格、Alpha pipeline、运行与信号能力。允许依赖 kernel/platform；禁止直接依赖 data/features/portfolio/risk/execution/backtest/analysis/application/apps。

## 关键不变量

- 市场输入由 application/backtest 通过 `StrategyInputBundle` 注入。
- 信号持久化通过 `SignalStore` Protocol 注入，不持有具体 adapter。
- 策略只产出信号和规格；组合、风控与执行由编排层负责。
- DecisionFrame 列契约变化属于公共行为变化，先 RED 并检查 PIT 安全。

## 验证与参考

- `pixi run -e dev pytest packages/strategy/tests`
- `pixi run -e dev arch-check`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [PIT skill](../../.agents/skills/ditto-pit-safety/SKILL.md)
