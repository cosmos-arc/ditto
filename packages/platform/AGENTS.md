# Platform 包指南

## 定位与依赖

缓存、并发、配置工具、数据库、存储基类、可观测性与通知等横切基础设施。除获准的 kernel 异常原语外，不依赖业务包。

## 关键不变量

- 零业务逻辑、零领域概念，保持可独立提取。
- 消费者从明确的 `foundation` 或 `services` 叶边界导入。
- 本包只提供配置工具；环境配置加载发生在 apps。
- 通用存储与数据库抽象不得吸收 data/execution/analysis 的领域 schema。

## 验证与参考

- `uv run --no-sync pytest packages/platform/tests`
- `task arch-check`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [边界标准](../../docs/architecture/boundaries-and-abstraction-standards.md)
