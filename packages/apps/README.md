# ditto-apps

**版本**: v0.6.0 | **日期**: 2026-04-04 | **状态**: 稳定

## 概要

应用边界层（Application Boundary Layer）— Ditto 系统的唯一入口。提供 HTTP API、CLI 命令、Prefect 任务调度和 DI 容器组装，不含业务逻辑（业务逻辑在 `ditto_application` 包中）。

## 目录结构

```
packages/apps/
├── src/ditto_apps/
│   ├── api/                # FastAPI 路由
│   │   ├── errors.py       # API 层错误处理
│   │   └── routes/         # capital, commodity, debug, fundamental, fx, ingestion, macro, market, metadata, portfolio, source
│   ├── cli/                # Typer CLI（main.py, context.py, executor.py）
│   │   ├── commands/       # factory.py, init.py, strategy.py
│   │   │   ├── backfill/   # capital, fundamental, macro, market, metadata
│   │   │   ├── ingest/     # capital, fundamental, macro, market, metadata
│   │   │   └── query/      # capital, fundamental, macro, market, metadata
│   │   ├── models/         # （预留）
│   │   └── utils/          # identifier.py, output.py, params.py, validation.py
│   ├── config/             # 配置加载（loader.py）
│   ├── jobs/               # Prefect 任务（context.py）
│   │   ├── flows/          # backfill, daily, deploy, materialization, repair, research
│   │   └── tasks/          # dq_batch, monitoring, t0_meta
│   ├── models/             # API Pydantic 模型（capital, commodity, common, fundamental, fx, identifier, macro, market, metadata）
│   ├── registry/           # Dishka DI Composition Root（container.py, init_providers.py）
│   │   ├── contexts/       # bundle, ingestion, materialization, query, strategy
│   │   └── infra/          # config, notification, observability
│   ├── main.py             # FastAPI 入口
│   ├── middleware.py
│   ├── exceptions.py       # 自定义异常
│   └── testing.py
└── tests/
    ├── unit/
    └── integration/
```

## 架构定位

```
apps → application ✅     （query / process / command / builders）
apps → data ✅            （services / sources，通过 DI 注入）
apps → analysis ✅        （research / reporting 编排）
apps → platform ✅
```

Apps 是依赖图的末端，禁止被任何其他 ditto 包依赖。

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

业务逻辑已迁入 `ditto_application` 包：

| 原位置 | 新位置 |
|--------|--------|
| services/ingestion/ | ditto_application.processes.ingestion |
| services/strategy/ | ditto_application.processes.execution |
| services/derived/ | ditto_application.processes.materialization / queries.derived |
| models/config | ditto_application.config |

## 相关文档

- [Apps 层规范](CLAUDE.md)
- [Application 层规范](../application/CLAUDE.md)

## 变更记录

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
