# Application 包指南

## 定位与依赖

CQRS 应用编排层，协调 data 与各 capability package。允许依赖 kernel/platform/data/features/strategy/portfolio/risk/execution/backtest/analysis 的获准合同；禁止依赖 `apps`。

## 关键不变量

- 只做用例与流程编排，不放核心领域逻辑。
- queries 只读，commands 写入，processes 可协调读写；互斥边界由 import-linter 强制。
- builders/providers 负责运行时组装，但配置加载仍在 `apps`。
- 公共 facade 或契约变化使用 `ditto-architecture-change` 与 `ditto-test-first`。

## 验证与参考

- `pixi run -e dev pytest packages/application/tests`
- `pixi run -e dev arch-check`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [边界标准](../../docs/architecture/boundaries-and-abstraction-standards.md)
