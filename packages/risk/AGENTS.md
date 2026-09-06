# Risk 包指南

## 定位与依赖

盘前/盘后风控、约束、暴露与回撤能力。允许依赖 kernel、portfolio 和 import-linter 明确的 execution order 窄合同；禁止依赖其他业务平面或 platform。

## 关键不变量

- 风控是安全网，不承担策略或交易决策。
- 正常 risk finding 用返回值表达；仅配置失败和契约误用抛异常。
- 约束可组合、可配置，并对边界值提供测试证据。

## 验证与参考

- `pixi run -e dev pytest packages/risk/tests`
- `pixi run -e dev arch-check`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [测试指南](../../docs/engineering/testing.md)
