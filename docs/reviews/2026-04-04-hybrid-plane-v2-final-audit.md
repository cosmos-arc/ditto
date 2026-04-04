# Hybrid Plane V2 — 最终架构审计

> **日期**: 2026-04-04
> **审计者**: Claude (**状态**: ✅ 架构完成

**结论**: Hybrid Plane v2 迁移已全面完成，架构稳定，所有门禁通过，不建议继续大规模重构。

---

## 1. 已完成目标

| 目标 | 状态 | 说明 |
|------|------|------|
| 5 包核心包 (kernel/infra/data/engine/analytics/app) + 应用层 (interfaces) | ✅ | 全部落地 |
| 分层架构 + CQRS + DI | ✅ | 工作正常 |
| Import Linter 18 合约全通过 | ✅ | 0 broken, 0 warnings |
| 零 `ditto_core`/`ditto_datahub`/`ditto_port` 残留 | ✅ | 完全清除 |
| 零 `AnyFrame` 残留 | ✅ | 完全消除 |

## 2. 已接受偏差（ADR-0006)

| 编号 | 偏差 | 接受理由 |
|------|------|----------|
| D1 | `interfaces/api/` 而非 `http/` | FastAPI routes 是 REST API handlers |
| D2 | DI 命名分化 | 不同层 DI 粒度需要不同命名（data.di/app.providers/interfaces.registry.container） |
| D3 | Analytics→Data.errors | 仅 import `ditto_data.errors` | 将 errors 移入 Kernel 违反零业务行为原则 |
| D4 | DataProvider 在 Data | `BarQuery` 需要 polars；Kernel 禁止 polars |
| D5 | `packages/app/` 非 `apps/app/` | App 是编排层，非独立部署 |
| D6 | App 扁平结构 | CQRS 4 模块，4 子目录 | 代码量不足以嵌套 |
| D7 | AlphaOutput/PortfolioOutput 已删除 | 仅测试使用，主流程用 DecisionFrame 列约定 |

## 3. 事件模型状态

| 事件 | 状态 | 说明 |
|------|------|------|
| OrderSubmitted | ✅ 已接入 | engine/backtest/engine.py |
| OrderFilled | ✅ 已接入 | engine/backtest/engine.py |
| RiskGuardTriggered | ✅ 已接入 | engine/backtest/engine.py |
| OrderCanceled | 🔮 预留 | 仅定义，未在主流程发布 |
| PositionChanged | 🔮 预留 | 仅定义，未在主流程发布 |
| DataIngested | 🔮 预留 | 仅定义，未在 ingestion 流程发布 |
| QualityCheckCompleted | 🔮 预留 | 仅定义，未在 quality 流程发布 |

## 4. DI 实际结构

```
ditto_infra.foundation (3 Providers)
    ↓
ditto_data.di (10 Providers)
    ↓
ditto_app.providers (3 Providers: Query/Process/BuilderFactory)
    ↓
ditto_interfaces.registry.container (Composition Root)
```

`ditto_engine.di` 和 `ditto_analytics.di` **不存在**。且无计划创建。
 仅当 Engine/Analytics 出现真实 Provider 聚合需求时才补独立 `di.py`。

## 5. Registry 豁免边界

`ditto_interfaces.registry.**` 是 Composition Root 豁免区，允许直接导入 Data services/quality/config。
由 importlinter `port-service-isolation` 合约显式配置，非 registry 代码禁止直接访问 Data services/models。

## 6. 剩余非阻塞项

| 项 | 说明 | 建议 |
|------|------|------|
| 预留事件接入 | 当 ingestion/quality 流程需要事件驱动时接入 | 否则保留 docstring 标注 |
| Data 内部 storage/sources 边界 | 已由 importlinter 强制 | 当前无需额外措施 |
| `ditto_core`/`ditto_datahub`/`ditto_port` 历史命名 | 已完全清除（源码 + 测试 + 文档） |

## 关键指标

| 指标 | 值 |
|------|------|
| 测试数量 | 4367+ |
| Import Linter 合约 | 18 (0 broken) |
| 分支覆盖率 | ≥ 80% |
| `from ditto_engine` | 576 夬 / 133 文件 |
| `from ditto_analytics` | 173 次从 / 71 文件 |
| `from ditto_data` | 710 次从 / 250 文件 |
| `from ditto_app` | 116 次从 / 74 文件 |
