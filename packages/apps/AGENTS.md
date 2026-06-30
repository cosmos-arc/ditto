---
last_synced: 2026-06-04
---

# Apps Agent 指南

## 定位

应用边界层 — HTTP API（FastAPI）、CLI 命令、Prefect 任务调度、DI 容器组装（Composition Root）。

## 核心模块

| 模块 | 职责 |
|------|------|
| api/ | FastAPI 路由（backtest/capital/market/metadata/strategy/trade/universe） |
| cli/ | CLI 命令入口（ingest/backfill/query/strategy） |
| jobs/ | Prefect Flow/Task（daily/backtest/materialization/research） |
| registry/ | DI 容器（Composition Root，唯一允许直接导入 Data/Capability 实现的位置） |
| config/ | 环境配置加载 |
| models/ | API 数据模型（Pydantic） |

## 依赖规则

### 允许

- apps → application ✅（commands/queries/processes）
- apps → platform ✅（foundation + services）
- apps.registry → data/features/strategy/portfolio/risk/execution/backtest/analysis ✅（DI 注册）

### 禁止

- 非 registry 代码直接导入 Data services/models ❌
- 非 registry 代码直接导入 Capability 实现 ❌
- API/CLI/Job 中包含业务逻辑 ❌

## 关键约束

- registry/ 是唯一允许直接导入能力包实现的位置（Composition Root 边界）
- API 路由必须类型注解 100%，使用 Pydantic Model
- Prefect Flow 中禁止写业务逻辑，抽取到 Task 或 ditto_application
- 配置仅在 apps 层加载，其他层通过 DI 获取

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
