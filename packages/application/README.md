# ditto-application

**版本**: v0.4.0
**最后更新**: 2026-05-01
**状态**: 应用编排层（CQRS）

## 概要

应用编排层 -- 采用 CQRS 模式组织 Use Case，协调 capability packages（领域计算）与 Data（数据服务）。

目录结构详见 [CLAUDE.md](CLAUDE.md)。

架构规则和依赖约束详见 [CLAUDE.md](CLAUDE.md)。

CQRS 互斥规则详见 [CLAUDE.md](CLAUDE.md)。

## 使用示例

### DI 注册

```python
from ditto_application.providers import get_app_providers

providers = get_app_providers()  # [AppMarketQueryProvider, AppStrategyQueryProvider, AppPortfolioQueryProvider, ...]
```

### 查询服务

```python
from ditto_application.queries.market import MarketQueryFacade

facade = container.get(MarketQueryFacade)
bars = facade.list_bars(code="159915.SZ", start="2024-01-01", end="2024-12-31")
```

## 相关文档

- [Application 层规范](CLAUDE.md)
- [架构规则](../../.claude/rules/architecture.md)
