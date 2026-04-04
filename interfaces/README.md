# ditto-interfaces

**版本**: v0.6.0 | **日期**: 2026-04-04 | **状态**: 稳定

## 概要

应用边界层（Application Boundary Layer）— Ditto 系统的唯一入口。提供 HTTP API、CLI 命令、Prefect 任务调度和 DI 容器组装，不含业务逻辑（业务逻辑在 `ditto_app` 包中）。

## 目录结构

```
interfaces/
├── src/ditto_interfaces/
│   ├── api/            # FastAPI 路由
│   ├── cli/            # Typer CLI（main.py, context.py, executor.py）
│   ├── config/         # 配置加载
│   ├── jobs/           # Prefect 任务（context.py）
│   ├── models/         # API Pydantic 模型（market, capital, fundamental, macro 等）
│   ├── registry/       # Dishka DI Composition Root（container.py, init_providers.py）
│   ├── main.py         # FastAPI 入口
│   ├── middleware.py
│   ├── errors.py
│   ├── exceptions.py
│   └── testing.py
└── tests/
    ├── unit/
    └── integration/
```

## 架构定位

```
interfaces → app ✅       （query / process / command / builders）
interfaces → engine ✅
interfaces → data ✅      （services / sources，通过 DI 注入）
interfaces → analytics ✅
interfaces → infra ✅
```

Interfaces 是依赖图的末端，禁止被任何其他 ditto 包依赖。

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

## CLI 命令

```bash
ditto init config          # 配置初始化
ditto ingest metadata      # 元数据摄取
ditto ingest market        # 行情数据摄取
ditto backfill metadata    # 历史回填
ditto query market         # 数据查询
```

## 业务逻辑去向

业务逻辑已迁入 `ditto_app` 包：

| 原位置 | 新位置 |
|--------|--------|
| services/ingestion/ | ditto_app.process.ingestion |
| services/strategy/ | ditto_app.process.strategy |
| services/derived/ | ditto_app.process.materialization / query.derived |
| models/config | ditto_app.config |

## 相关文档

- [Interfaces 层规范](CLAUDE.md)
- [App 层规范](../packages/app/CLAUDE.md)

## 变更记录

### v0.6.0 (2026-04-04)
- 包名从 `ditto-port` 重命名为 `ditto-interfaces`
- 业务逻辑迁移至 `ditto_app` 包，Interfaces 层变为纯编排层
- 目录结构扁平化，移除 services/ 子目录
- DI 容器简化为 container.py + init_providers.py

### v0.5.0 (2026-03-24)
- 新增策略运行服务（BacktestService、StrategyRunService）
- 新增衍生数据服务（MaterializationOrchestrator、QueryFacade）
- Typer CLI 命令、Dishka DI 容器

### v0.1.0 (2025-12-27)
- 初始版本，FastAPI 基础框架
