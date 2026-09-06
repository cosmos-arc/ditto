# Apps 包指南

## 定位与依赖

HTTP API、CLI、Prefect Jobs 与 DI composition root。常规入口依赖 `application` 和 `platform`；只有 `registry` 可直接装配 data、features、strategy、portfolio、risk、execution、backtest、analysis 实现。

## 关键不变量

- API/CLI/Job 不承载业务逻辑，只做适配和调用应用用例。
- `registry` 是能力实现与外部 adapter 的唯一组装边界。
- API 使用显式 Pydantic 模型和完整类型；Flow 的业务行为下沉到 Task 或 application。
- 运行时配置只在本包加载，再经 DI 传入其他包。

## 验证与参考

- `uv run --no-sync pytest apps/backend/tests`
- `task arch-check`
- [配置指南](../../docs/configuration.md) · [架构快速参考](../../docs/architecture/agent-context-pack.md)
