# Port 层架构设计

**版本：v1.0**

**日期：2025-01-11**

---

## 1. 概述

### 1.1 设计目标

`interfaces/` 是 ditto 项目的统一入口层，提供多种对外接口：
- **HTTP API**：Web 应用和外部系统集成
- **CLI**：命令行工具，支持数据摄取和管理
- **Jobs**：定时任务调度（基于 Prefect）

### 1.2 核心原则

1. **入口与业务分离**：api/cli/jobs 只负责接口适配，业务逻辑在 services 层
2. **无框架依赖的服务层**：services/ 不依赖任何框架（FastAPI/CLI/Prefect）
3. **统一调用路径**：所有入口通过 services 层访问核心业务逻辑

---

## 2. 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                    Entry Points (入口层)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐  │
│  │   API    │  │   CLI    │  │         Jobs             │  │
│  │ (FastAPI)│  │  (Typer) │  │  (Prefect Flows/Tasks)   │  │
│  └────┬─────┘  └────┬─────┘  └───────────┬──────────────┘  │
└───────┼────────────┼────────────────────┼────────────────────┘
        │            │                    │
        └────────────┴────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  Services Layer (业务服务层)                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │            services/ingestion/                         │ │
│  │  - coordinator.py  (摄取协调逻辑)                      │ │
│  │  - backfill.py     (回补管理逻辑)                      │ │
│  │  - config/         (配置和注册表)                       │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              Core Engines & DataHub (核心层)                │
│  packages/ditto-engine/    packages/ditto-data/             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 目录结构

```
interfaces/
├── pyproject.toml                      # 包配置
└── src/ditto_interfaces/
    ├── __init__.py
    ├── main.py                         # FastAPI 应用入口
    │
    ├── api/                            # HTTP API 入口
    │   ├── __init__.py
    │   └── routes/                     # FastAPI 路由定义
    │       ├── __init__.py
    │       ├── ingestion.py            # 摄取相关 API
    │       └── ...
    │
    ├── cli/                            # CLI 入口
    │   ├── __init__.py
    │   ├── main.py                     # Typer 应用入口
    │   ├── executor.py                 # CLI 执行器
    │   ├── commands/                   # 命令实现
    │   │   ├── __init__.py
    │   │   ├── stock.py                # 股票相关命令
    │   │   ├── etf.py                  # ETF 相关命令
    │   │   ├── calendar.py             # 交易日历命令
    │   │   └── adj.py                  # 复权因子命令
    │   └── utils/                      # CLI 工具函数
    │       ├── __init__.py
    │       ├── output.py               # 输出格式化
    │       └── validation.py           # 参数验证
    │
    ├── jobs/                           # 定时任务入口
    │   ├── __init__.py
    │   ├── flows/                      # Prefect Flow 定义
    │   │   ├── __init__.py
    │   │   ├── daily.py                # 每日摄取流程
    │   │   ├── backfill.py             # 回补流程
    │   │   ├── repair.py               # 修补流程
    │   │   └── deploy.py               # Flow 部署脚本
    │   └── tasks/                      # Prefect Task 定义
    │       ├── __init__.py
    │       ├── t0_meta.py              # T0 元数据任务
    │       ├── t1_bars.py              # T1 行情任务
    │       ├── t1_adj_factor.py        # T1 复权因子任务
    │       └── dq_batch.py             # 数据质量检查任务
    │
    └── services/                       # 业务服务层（无框架依赖）
        ├── __init__.py
        └── ingestion/                  # 摄取业务服务
            ├── __init__.py
            ├── coordinator.py          # 摄取协调器
            ├── backfill.py             # 回补管理器
            ├── retry.py                # 重试管理器
            ├── metadata.py             # 元数据管理器
            └── config/                 # 配置
                ├── __init__.py
                ├── datasets.py         # 数据集注册表
                └── config.py           # 配置模型
```

---

## 4. 层级职责

### 4.1 Entry Points（入口层）

**职责**：
- 接收外部请求（HTTP/命令行/调度触发）
- 参数验证和转换
- 调用 services 层完成业务逻辑
- 返回格式化结果

**特点**：
- **薄层**：只做适配，不包含业务逻辑
- **框架绑定**：每个入口使用各自的框架（FastAPI/Typer/Prefect）
- **可独立测试**：通过 mock services 层进行单元测试

### 4.2 Services Layer（业务服务层）

**职责**：
- 实现核心业务逻辑
- 协调 Core Engines 和 DataHub
- 提供统一的业务接口

**特点**：
- **无框架依赖**：不依赖 FastAPI/Typer/Prefect
- **可复用**：被多个入口共享
- **易测试**：纯 Python 逻辑，易于单元测试

**关键服务**：
- `IngestionCoordinator`：摄取协调器，负责单日数据摄取
- `BackfillManager`：回补管理器，负责历史数据回补
- `RetryManager`：重试管理器，负责失败重试逻辑

### 4.3 依赖方向

```
api/ → services/ → packages/
cli/ → services/ → packages/
jobs/ → services/ → packages/
```

**禁止**：
- services/ 依赖 api/cli/jobs/
- services/ 依赖 FastAPI/Typer/Prefect
- 入口层直接调用 packages/（必须通过 services/）

---

## 5. 关键设计决策

### 5.1 为什么分离 services 层？

**问题**：
- 如果业务逻辑写在 api/cli/jobs 中，会导致代码重复
- 业务逻辑难以测试（需要启动整个框架）
- 无法被多个入口共享

**解决方案**：
- 提取 services 层，包含纯业务逻辑
- 入口层只负责参数转换和结果格式化

### 5.2 为什么 jobs 包含 flows 和 tasks？

**问题**：
- flows 和 tasks 是 Prefect 框架组件
- 它们不应该与业务逻辑混合

**解决方案**：
- flows/tasks 放在 jobs/ 下，明确它们是调度相关
- 业务逻辑在 services/ 中，flows 只负责编排

### 5.3 CLI 为什么需要 executor？

**问题**：
- CLI 直接调用 services 可能导致代码重复
- 错误处理和输出格式化逻辑分散

**解决方案**：
- 创建 `CLIExecutor` 封装 services 调用
- 统一错误处理和结果格式化

---

## 6. 数据流示例

### 6.1 CLI 数据摄取流程

```
用户命令
  │
  ▼
┌─────────────────┐
│  CLI Command    │  stock daily --date 2024-01-02
│  (stock.py)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  CLIExecutor    │  ingest_daily("stock_daily", "2024-01-02")
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  IngestionCoordinator   │  ingest_date(dataset, date)
│  (services/ingestion/)  │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  DataHub + Core Engine  │
└─────────────────────────┘
         │
         ▼
    返回结果
         │
         ▼
┌─────────────────┐
│  CLI Output      │  格式化输出
└─────────────────┘
```

### 6.2 Job 调度流程

```
Prefect Scheduler
  │
  ▼
┌─────────────────┐
│  Flow           │  daily_ingestion_flow()
│  (jobs/flows/)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  IngestionCoordinator   │  ingest_date(dataset, date)
│  (services/ingestion/)  │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  DataHub + Core Engine  │
└─────────────────────────┘
```

---

## 7. 测试策略

### 7.1 入口层测试

- **API**：使用 FastAPI TestClient
- **CLI**：使用 Typer CliRunner
- **Jobs**：使用 Prefect 测试工具

### 7.2 Services 层测试

- **单元测试**：直接测试服务类，mock DataHub
- **集成测试**：使用真实 DataHub（test_settings_session）

### 7.3 测试覆盖要求

- 入口层：≥ 60%（主要是参数验证和格式化）
- 服务层：≥ 80%（核心业务逻辑）

---

## 8. 迁移路径

### 8.1 从 apps/server 迁移

1. **重命名**：`apps/server` → `apps/port`
2. **包名**：`ditto_interfaces` → `ditto_interfaces`
3. **目录重组**：
   - 创建 `services/` 和 `jobs/`
   - 移动业务逻辑到 `services/ingestion/`
   - 移动 Prefect 组件到 `jobs/`

### 8.2 兼容性

- 保留现有的 HTTP API 接口
- 新增 CLI 入口点
- 保持 jobs 调度配置不变

---

## 9. 未来扩展

### 9.1 新增入口类型

如果需要新增入口（如 gRPC），只需：
1. 在 `interfaces/` 下创建新目录
2. 调用 `services/` 层的服务

### 9.2 新增业务服务

如果需要新增服务（如回测服务），只需：
1. 在 `services/` 下创建新目录
2. 实现服务接口
3. 各入口调用新服务

---

## 10. 参考资料

- 系统设计文档：`docs/design/01_system_design.md`
- 数据摄取设计：`docs/design/10_data_ingestion_scheduler_design.md`
- CLI 实施计划：`docs/plans/2025-01-11-cli-entry.md`
