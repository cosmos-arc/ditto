# ditto-apps

> 包级约束见 [AGENTS.md](AGENTS.md)；全局边界见 [架构快速参考](../../docs/architecture/agent-context-pack.md)。

**版本**: v0.14.0 | **日期**: 2026-05-06 | **状态**: 稳定

## 概要

应用边界层（Application Boundary Layer）— Ditto 系统的唯一入口。提供 HTTP API、CLI 命令、Prefect 任务调度和 DI 容器组装，不含业务逻辑（业务逻辑在 `ditto_application` 包中）。

## 核心功能

| 功能 | 技术 | 说明 |
|------|------|------|
| REST API | FastAPI | CORS / ORJSON / Dishka DI |
| CLI 命令 | Typer | `ditto init / ingest / backfill / query` |
| 任务调度 | Prefect 3 | Flows / Tasks |
| DI 容器 | Dishka | Composition Root（container.py） |

## 快速开始

```bash
# 开发模式（热重载）
pixi run -e dev dev

# 生产模式（4 workers）
pixi run server

# 健康检查
curl http://localhost:8000/healthz
```

## 相关文档

- [Apps 层规范](AGENTS.md) — 目录结构、架构规则和依赖约束、业务逻辑迁移规则、CLI 命令详情
- [Application 层规范](../application/AGENTS.md)

## 变更记录

### v0.14.0 (2026-05-06)
- 文档同步：更新 routes/flows/tasks/models 列表，移除已废弃的 portfolio 路由和 identifier 模型
- 新增 backtest/strategy/trade/universe 路由；shared_bars 辅助路由
- 新增 backtest/eod flows；aliases task；ops CLI 命令
- 新增 backtest/ingestion/lineage/strategy/trade/universe 模型
- registry/infra 新增 signal_delivery

### v0.6.0 (2026-04-04)
- 旧入口包重命名为 `ditto-apps`
- 业务逻辑迁移至 `ditto_application` 包，Apps 层变为纯编排层
- 目录结构扁平化，移除 services/ 子目录
- DI 容器简化为 container.py + init_providers.py

### v0.5.0 (2026-03-24)
- 新增策略运行服务（BacktestService、StrategyRunService）
- 新增衍生数据服务（MaterializationOrchestrator、QueryFacade）
- Typer CLI 命令、Dishka DI 容器

### v0.1.0 (2025-12-27)
- 初始版本，FastAPI 基础框架
