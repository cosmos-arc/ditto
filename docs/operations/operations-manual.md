# Ditto 量化系统运维手册

> **版本**: v1.0
> **日期**: 2026-01-22
> **适用范围**: Ditto 量化系统本地部署

---

## 目录

1. [项目架构概览](#1-项目架构概览)
2. [启动命令与脚本](#2-启动命令与脚本)
3. [配置文件结构](#3-配置文件结构)
4. [环境变量优先级](#4-环境变量优先级)
5. [配置项详细说明](#5-配置项详细说明)
6. [可观测性与 DQ 配置](#6-可观测性与-dq-配置)
7. [常用运维命令汇总](#7-常用运维命令汇总)
8. [故障排查与日志](#8-故障排查与日志)

---

## 1. 项目架构概览

### 1.1 应用类型

| 应用 | 入口文件 | 用途 |
|------|----------|------|
| **API Server** | [main.py](../apps/port/src/ditto_port/main.py) | REST API 服务（FastAPI + Granian） |
| **CLI** | [cli/main.py](../apps/port/src/ditto_port/cli/main.py) | 命令行工具 |
| **Prefect Flows** | [jobs/flows/](../apps/port/src/ditto_port/jobs/flows/) | 数据摄取编排 |

### 1.2 Prefect Flows 列表

| Flow | 文件 | 功能 |
|------|------|------|
| `daily_ingestion_flow` | [daily.py](../apps/port/src/ditto_port/jobs/flows/daily.py) | 每日增量摄取（T0→T1→T3） |
| `backfill_flow` | [backfill.py](../apps/port/src/ditto_port/jobs/flows/backfill.py) | 全量数据回补 |
| `backfill_missing_flow` | [backfill.py](../apps/port/src/ditto_port/jobs/flows/backfill.py) | 回补缺失数据 |
| `daily_repair_flow` | [repair.py](../apps/port/src/ditto_port/jobs/flows/repair.py) | 每日修补流程 |
| `repair_holes_flow` | [repair.py](../apps/port/src/ditto_port/jobs/flows/repair.py) | 修补数据空洞 |
| `retry_failed_flow` | [repair.py](../apps/port/src/ditto_port/jobs/flows/repair.py) | 重试失败任务 |

### 1.3 包结构

```
ditto/
├── packages/infra/         # 基础设施层（配置、日志、路径、Runtime）
├── packages/data/       # 数据访问层（存储、数据源）
├── packages/engine/          # 核心引擎层（DQ、业务逻辑）
└── apps/port/              # 应用层（API、CLI、Flows）
```

### 1.4 双层环境架构

| 层级 | 变量 | 有效值 | 说明 |
|------|------|--------|------|
| **Pixi 环境** | 选择环境 | `default`, `dev` | 依赖管理层 |
| **运行时环境** | `ENVIRONMENT` | `development`, `testing`, `production` | 行为控制层 |

> **注意**：`DITTO_ENV` 已弃用，请使用 `ENVIRONMENT`。代码中应使用 `get_environment()` 统一入口。

---

## 2. 启动命令与脚本

### 2.1 Pixi 任务命令

参考：[pixi.toml:149-214](../pixi.toml#L149-L214)

| 命令 | 用途 | 执行方式 |
|------|------|----------|
| **`pixi run dev`** | 开发服务器（热重载） | Granian 单进程，监听文件变化 |
| **`pixi run server`** | 生产服务器 | Granian 多进程（4 workers） |
| **`pixi run test`** | 运行测试 | 支持参数：`--unit`, `--integration`, `--fast`, `--cov` |
| **`pixi run check`** | 快速验证 | lint + fmt + type |
| **`pixi run ci`** | CI 完整检查 | lint + fmt-check + type-all + test-cov-xml |

### 2.2 Prefect 完整启动流程

根据部署文档，Prefect 需要**两个组件**同时运行：

| 组件 | 命令 | 端口 | 说明 |
|------|------|------|------|
| **Prefect Server** | `prefect server start --host 0.0.0.0` | 4200 (UI) | 管理界面和 API |
| **Prefect Worker** | `prefect worker start -p <work-pool>` | - | 执行任务的工作进程 |

### 2.3 完整启动顺序

**方式一：手动启动（开发调试）**

```bash
# 终端 1: 启动 Prefect Server
prefect server start --host 0.0.0.0

# 终端 2: 启动 Prefect Worker
prefect worker start -p my-work-pool

# 终端 3: 启动 API Server
pixi run dev
```

**方式二：使用脚本（生产环境）**

```powershell
# 一键启动所有服务
.\scripts\start_all.ps1

# 或单独启动 Prefect
.\scripts\start_prefect.ps1
```

### 2.4 验证服务状态

| 服务 | URL | 检查命令 |
|------|-----|----------|
| API Server | http://localhost:8000/docs | `curl http://localhost:8000/healthz` |
| Prefect UI | http://localhost:4200 | 浏览器访问 |
| 健康检查 | http://localhost:8000/api/v1/status | `curl http://localhost:8000/api/v1/status` |

---

## 3. 配置文件结构

### 3.1 配置目录结构

```
config/
├── development/          # 开发环境
│   ├── system.env        # 系统配置
│   ├── observability.env # 可观测性配置
│   ├── data_store.env    # 数据根路径配置
│   ├── database.env      # 数据库配置
│   ├── data_source.env   # 数据源配置
│   ├── dq.env            # 数据质量配置
│   ├── notification.env  # 通知配置
│   ├── api.env           # API 配置
│   └── performance.env   # 性能配置
├── testing/              # 测试环境（同上）
├── production/           # 生产环境（同上）
└── default/              # 默认配置（DQ 规则）
    └── dq_rules/         # DQ 规则文件
```

### 3.2 配置加载流程

1. 根据 `ENVIRONMENT` 环境变量确定环境（通过 `get_environment()` 统一入口）
2. `ConfigLoader` 仅读取 `config/{environment}/` 下的 `.env` 文件并统一 key
3. `ConfigProvider` 通过 `model_validate` 构造配置模型（纯 BaseModel）
4. 通过 DI 容器注入到各个模块

### 3.3 配置类与文件映射

| 配置类 | 来源 | 配置文件 | 定义位置 |
|--------|------|----------|----------|
| `SystemSettings` | 字段名（大小写不敏感） | `system.env` | [settings.py:12-33](../packages/infra/src/ditto_infra/foundation/config/settings.py) |
| `ObservabilitySettings` | 字段名（大小写不敏感） | `observability.env` | [settings.py:36-76](../packages/infra/src/ditto_infra/foundation/config/settings.py) |
| `DataRootConfig` | 字段名（大小写不敏感） | `data_store.env` | [data_root.py:10-170](../packages/data/src/ditto_data/config/data_root.py) |
| `DatabaseSettings` | 字段名（大小写不敏感） | `database.env` | [database.py:10-31](../packages/data/src/ditto_data/config/database.py) |
| `DataSourceSettings` | 字段名（大小写不敏感） | `data_source.env` | [data_source.py:7-34](../packages/data/src/ditto_data/config/data_source.py) |
| `DQSettings` | 字段名（大小写不敏感） | `dq.env` | [config.py:9-100](../packages/engine/src/ditto_engine/quality/config.py) |
| `NotificationSettings` | 字段名（大小写不敏感） | `notification.env` | [config.py:1-45](../packages/infra/src/ditto_infra/foundation/notification/config.py) |
| `FileStorageSettings` | 由 `DataRootConfig` 派生 | `data_store.env` | [storage.py:1-26](../packages/data/src/ditto_data/config/storage.py) |

---

## 4. 环境变量优先级

配置权威来源为 `config/{environment}/*.env`，环境变量仅用于选择环境（`ENVIRONMENT`）。

优先级（从高到低）：
1. `config/{environment}/*.env` 文件
2. BaseModel 默认值（缺省字段）

不再支持 `DITTO_*_DIR` / `XDG_*_HOME` 等路径覆盖。

## 5. 配置项详细说明

### 5.1 系统配置 (system.env)

| 键名 | 类型 | 默认值 | 说明 | 建议 |
|----------|------|--------|------|------|
| `ENVIRONMENT` | Enum | `development` | 运行环境 | 必须与目录名一致 |
| `TIMEZONE` | string | `Asia/Shanghai` | 系统时区 | 保持默认 |
| `DEBUG` | boolean | `false` | 调试模式 | 开发环境 `true`，生产环境 `false` |

**各环境建议值**：
```bash
# development
ENVIRONMENT=development
DEBUG=true

# testing
ENVIRONMENT=testing
DEBUG=false

# production
ENVIRONMENT=production
DEBUG=false
```

### 5.2 API 配置 (api.env)

| 键名 | 类型 | 默认值 | 说明 | 建议 |
|----------|------|--------|------|------|
| `API_HOST` | string | `0.0.0.0` | 监听地址 | 保持默认监听所有接口 |
| `API_PORT` | int | `8000` | 监听端口 | 避免冲突即可 |
| `API_WORKERS` | int | `1` (dev) / `4` (prod) | Worker 进程数 | CPU 核心数 |

### 5.3 数据库路径配置（data_store.env + database.env）

数据库路径由 `DataRootConfig` + `DatabaseSettings` 组合决定：

- `data_store.env` 的 `DATA_ROOT` 提供默认根目录
- `database.env` 可选覆盖 `SQLITE_PATH` / `DUCKDB_PATH`（未配置则由 data_root 派生）

示例：
```bash
# data_store.env
DATA_ROOT=data

# database.env（可选覆盖）
SQLITE_PATH=data/metadata/metadata.sqlite
DUCKDB_PATH=data/db/duckdb/ditto.duckdb
```

### 5.4 数据源配置 (data_source.env)

| 键名 | 类型 | 默认值 | 说明 | 建议 |
|----------|------|--------|------|------|
| `TUSHARE_TOKEN` | string | `""` | Tushare API Token | 必填 |
| `HTTP_BASE_URL` | string | `http://api.tushare.pro` | API 基础 URL | 保持默认 |
| `HTTP_TIMEOUT` | float | `30.0` | 请求超时（秒） | 1.0-300.0 |
| `RETRY_MAX_ATTEMPTS` | int | `3` | 最大重试次数 | 1-10 |
| `RETRY_MULTIPLIER` | float | `1.0` | 重试倍数 | 0.1-10 |
| `RETRY_MIN_WAIT` | float | `1.0` | 最小等待 | 0.1-10 |
| `RETRY_MAX_WAIT` | float | `10.0` | 最大等待 | 1-60 |
| `RATE_LIMIT_PROFILE` | string | `free` | 限流配置档 | `free`/`pro` |
| `TDX_PATH` | string | `""` | 通达信路径 | 可选 |

Token 仅来自 `data_source.env`，由应用层注入，不读取环境变量/Keyring。

---

## 6. 可观测性与 DQ 配置

### 6.1 可观测性配置 (observability.env)

键名：字段名（大小写不敏感）

| 键名 | 类型 | 默认值 | 说明 | 建议值 |
|----------|------|--------|------|--------|
| **日志配置** ||||||
| `LOG_LEVEL` | string | `INFO` | 日志级别 | dev: `DEBUG`, prod: `INFO` |
| `LOG_FORMAT` | string | `console` | 日志格式 | `console`/`json` |
| `LOG_TO_CONSOLE` | boolean | `true` | 控制台输出 | 保持默认 |
| `LOG_TO_FILE` | boolean | `true` | 文件输出 | 生产环境 `true` |
| **追踪配置** ||||||
| `TRACING_ENABLED` | boolean | `true` | 启用追踪 | dev: `true`, prod: `true` |
| `TRACING_EXPORTER` | string | `otlp` | 导出器 | `otlp`/`none` |
| `TRACING_SAMPLE_RATE` | float | `1.0` | 采样率 | dev: `1.0`, prod: `0.1` |
| **指标配置** ||||||
| `METRICS_ENABLED` | boolean | `true` | 启用指标 | dev: `true`, test: `false` |
| `METRICS_EXPORTER` | string | `otlp` | 导出器 | `otlp`/`none` |
| `VM_ENDPOINT` | string | `http://localhost:8428/opentelemetry/v1/metrics` | VM 端点 | 根据实际部署调整 |

未设置时按 environment 预设值生效（development/testing/production）。

### 6.2 DQ 数据质量配置 (dq.env)

键名：字段名（大小写不敏感）

| 键名 | 类型 | 默认值 | 说明 | 建议 |
|----------|------|--------|------|------|
| **开关配置** ||||||
| `L1_ENABLED` | boolean | `true` | L1 技术检查 | 保持开启 |
| `L2_ENABLED` | boolean | `true` | L2 业务检查 | 保持开启 |
| `L3_ENABLED` | boolean | `true` | L3 统计检查 | 保持开启 |
| **规则目录** ||||||
| `RULES_DIR` | string | `config/default/dq_rules` | DQ 规则目录 | 环境特定可覆盖 |
| **隔离区配置** ||||||
| `QUARANTINE_ENABLED` | boolean | `true` | 启用隔离区 | 保持开启 |
| **报告配置** ||||||
| `REPORT_ENABLED` | boolean | `true` | 启用报告 | 保持开启 |
| `REPORT_PATH` | string | `data/reports/dq` | 报告输出路径 | 相对路径 |

### 6.3 性能配置 (performance.env)

当前为空文件，保留用于未来扩展。

---

## 7. 常用运维命令汇总

### 7.1 服务管理

| 操作 | 命令 |
|------|------|
| **启动开发服务** | `pixi run dev` |
| **启动生产服务** | `pixi run server` |
| **启动 Prefect Server** | `prefect server start --host 0.0.0.0` |
| **启动 Prefect Worker** | `prefect worker start -p my-work-pool` |
| **一键启动所有** | `.\scripts\start_all.ps1` |

### 7.2 代码质量检查

| 命令 | 功能 |
|------|------|
| `pixi run check` | 快速验证（lint + fmt + type） |
| `pixi run lint` | 代码检查 |
| `pixi run lint --fix` | 自动修复 |
| `pixi run fmt` | 格式化代码 |
| `pixi run type` | 类型检查（源码） |
| `pixi run type --all` | 完整类型检查 |

### 7.3 测试命令

| 命令 | 功能 |
|------|------|
| `pixi run test` | 默认：单元测试（并行） |
| `pixi run test --unit` | 只运行单元测试 |
| `pixi run test --integration` | 只运行集成测试 |
| `pixi run test --fast` | 快速测试（跳过慢速） |
| `pixi run test --cov` | 带覆盖率报告 |
| `pixi run ci` | CI 完整检查 |

### 7.4 Prefect 运维命令

| 操作 | 命令 |
|------|------|
| **列出所有 Deployments** | `prefect deployment ls` |
| **查看最近运行** | `prefect flow-run ls --limit 10` |
| **手动触发 Flow** | `prefect deployment run "daily-ingestion/daily-ingestion-scheduled"` |
| **查看 Flow 日志** | `prefect flow-run logs <run-id>` |
| **取消运行** | `prefect flow-run cancel <run-id>` |
| **部署所有 Flows** | `python -m ditto_port.jobs.flows.deploy` |
| **列出可用 Flows** | `python -m ditto_port.jobs.flows.deploy list` |

### 7.5 配置文件管理

| 操作 | 命令 |
|------|------|
| **查看环境配置** | `Get-Content config/{env}/*.env` |
| **查看指定配置** | `Get-Content config/development/data_source.env` |
| **修改配置** | 使用文本编辑器修改 `config/{env}/*.env` |

### 7.6 健康检查

| 端点 | URL | 说明 |
|------|-----|------|
| 存活检查 | http://localhost:8000/healthz | 简单响应 |
| 详细状态 | http://localhost:8000/api/v1/status | 包含环境信息 |
| Prefect UI | http://localhost:4200 | Flow 管理界面 |
| API 文档 | http://localhost:8000/docs | Swagger UI |

---

## 8. 故障排查与日志

### 8.1 日志位置

| 日志类型 | 路径（Windows） | 路径（Linux/macOS） |
|----------|-----------------|---------------------|
| 应用日志 | `DATA_ROOT/logs/` | `DATA_ROOT/logs/` |
| Prefect 日志 | `~\.prefect\prefect.log` | `~/.prefect/prefect.log` |
| 测试日志 | 控制台输出（带 `--log-cli`） | 同左 |

### 8.2 常见问题排查

| 问题 | 排查步骤 |
|------|----------|
| **API 无法访问** | 1. 检查端口占用 `netstat -ano \| findstr 8000`<br>2. 查看日志中的错误<br>3. 确认 `ENVIRONMENT` 正确 |
| **Prefect Flow 失败** | 1. 访问 http://localhost:4200 查看 Flow 详情<br>2. 检查 Task 级别错误<br>3. 验证 Tushare Token |
| **Token 无效** | 1. 检查 `config/{env}/data_source.env` 中 `TUSHARE_TOKEN`<br>2. 确认 Tushare 积分余额<br>3. 重启服务后再试 |
| **数据库连接失败** | 1. 检查数据目录权限<br>2. 确认 `data_store.env`/`database.env` 路径存在<br>3. 查看 SQLite WAL 模式是否启用 |

### 8.3 数据备份

| 备份类型 | 路径 | 频率 |
|----------|------|------|
| Parquet 数据 | `D:\data\ditto\data\` | 每日 |
| SQLite 数据库 | `D:\data\ditto\data\db\sqlite\` | 每日 |
| 配置文件 | `config/` | 每次修改前 |

---

## 附录

### A. 环境变量命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| Pixi 环境 | 小写，无连字符 | `default`, `dev` |
| 运行时环境 | 小写，全称 | `development`, `testing`, `production` |
| 配置键名 | 大写下划线（大小写不敏感） | `LOG_LEVEL`, `DATA_ROOT` |
| 配置文件 | 小写，下划线 | `observability.env`, `database.env` |

### B. 相关文档

- [部署拓扑文档](../design/04_deployment_topology.md)
- [可观测性设计](../design/05_observability.md)
- [Port 架构设计](../design/11_port_architecture.md)

---

**文档维护**: 请在系统架构变更时及时更新此手册。
