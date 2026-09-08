# Portfolio 包指南

## 定位与依赖

账户、持仓、现金、购买力、订单簿与调仓的纯领域能力。只允许依赖 `kernel`；禁止依赖 platform 和其他业务能力包。

## 关键不变量

- 会计系统是显式状态机，所有状态变化通过领域方法发生。
- 调仓只计算目标权重和约束结果，不执行交易。
- 不反向依赖 risk 或 execution；交互由 application/backtest 编排。

## 验证与参考

- `uv run --no-sync pytest packages/portfolio/tests`
- `task arch-check`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [测试指南](../../docs/engineering/testing.md)
