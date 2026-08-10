# Backtest 包指南

## 定位与依赖

回测模拟运行时，负责主循环、step chain、数据回放、模拟成交、统计与报告。允许依赖 kernel/data/strategy/portfolio/risk/execution；禁止依赖 features/analysis/application/apps/platform。

## 关键不变量

- 只使用模拟执行，禁止导入真实券商 gateway。
- step chain 各阶段职责单一、可替换、可独立测试。
- 统计计算独立于主循环，不从报告层反向影响执行语义。
- 回放、窗口和数据可见性改动必须使用 `ditto-pit-safety` 与未来哨兵测试。

## 验证与参考

- `pixi run -e dev pytest packages/backtest/tests`
- `pixi run -e dev pytest -m pit`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [测试指南](../../docs/engineering/testing.md)
