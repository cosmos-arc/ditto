# ditto-port

**版本**: v0.5.0
**最后更新**: 2026-03-24
**状态**: ✅ 稳定

## 概要

Ditto 应用层（Application Layer），基于 FastAPI 的后端服务。负责用例编排、HTTP API、Prefect 任务调度和 CLI 命令入口，协调 Core 和 DataHub 层完成数据摄取、策略运行和衍生数据计算等业务流程。

## 核心功能

- **数据摄取**: 基于 Prefect 3 的 T0/T1 全矩阵数据摄取流程
- **策略运行**: BacktestService 回测编排 + StrategyRunService 策略运行管理
- **衍生数据**: MaterializationOrchestrator 物化编排 + QueryFacade 查询入口
- **CLI 命令**: Typer-based CLI（ditto init/ingest/backfill/query）
- **DI 容器**: Dishka 依赖注入容器（registry/）
- **API 层**: FastAPI 路由（market/capital/fundamental/macro/metadata/source/ingestion）
- **容错机制**: 部分失败容错、指数退避重试
- **结构化日志**: 包含 `event` 字段，便于监控和告警

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                      │
│  - API Routes (market/capital/fundamental/macro/...)       │
│  - CORS / ORJSON / Dishka DI / Lifespan                     │
└─────────────────────────────────────────────────────────────┘
                          △
┌─────────────────────────────────────────────────────────────┐
│                  Services (业务逻辑层)                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ ingestion/   │ │ strategy/    │ │ derived/     │        │
│  │ Coordinator  │ │ BacktestSvc  │ │ Materialize  │        │
│  │ Backfill     │ │ RunSvc       │ │ QueryFacade  │        │
│  │ Quality      │ │ InputAsmblr  │ │ Cascade      │        │
│  │ Retry        │ │ ArtifactWr   │ │ Evaluation   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└─────────────────────────────────────────────────────────────┘
        △                  △                  △
┌──────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ jobs/        │ │ cli/             │ │ registry/        │
│ Prefect Flows│ │ Typer commands   │ │ Dishka DI       │
│ Tasks        │ │ init/ingest/     │ │ core/datahub/   │
│              │ │ backfill/query   │ │ infra/contexts/ │
└──────────────┘ └──────────────────┘ └──────────────────┘
                          △
┌─────────────────────────────────────────────────────────────┐
│                      Core + DataHub                         │
│  EngineLoop / StrategyPipeline / MarketService / ...         │
└─────────────────────────────────────────────────────────────┘
```

**依赖规则**:
- `services/` → `models/` ✅
- `jobs/` → `services/` ✅
- `cli/` → `services/` ✅
- `models/` → 任何模块 ❌ (独立的模型层)

## 目录结构

```
apps/port/src/ditto_port/
├── api/                      # API 路由
│   └── routes/               # 业务路由
│       ├── market.py         # 行情查询
│       ├── capital.py        # 资金面查询
│       ├── fundamental.py    # 基本面查询
│       ├── macro.py          # 宏观查询
│       ├── metadata.py       # 元数据查询
│       ├── source.py         # 数据源管理
│       ├── ingestion.py      # 摄取管理
│       └── portfolio.py      # 组合管理
├── cli/                      # CLI 命令（Typer）
│   └── commands/
│       ├── ingest/           # 数据摄入命令
│       ├── backfill/         # 回填命令
│       └── query/            # 查询命令
├── jobs/                     # Prefect 任务编排
│   ├── flows/                # Flow 定义（daily/backfill/repair/materialization/publication）
│   └── tasks/                # Task 实现（t0_meta/dq_batch）
├── models/                   # 数据模型
│   ├── common.py             # ErrorResponse (API 响应)
│   ├── config.py             # DatasetSpec, T1ConfigSpec, DATASET_REGISTRY
│   └── ingestion.py          # IngestionResult, ResultCounts, BackfillResult
├── registry/                 # DI 容器（Dishka）
│   ├── core/                 # Core 层 Provider（golden dataset, quality engine）
│   ├── datahub/              # DataHub 层 Provider（stores, sources）
│   ├── infra/                # Infra 层 Provider（config, observability）
│   └── contexts/             # 请求上下文
├── services/                 # 应用服务
│   ├── ingestion/            # 数据摄取服务
│   │   ├── coordinator.py    # 统一摄取协调器
│   │   ├── backfill.py       # 回补管理器
│   │   ├── data_writer.py    # 数据写入器
│   │   └── quality/          # DQ 检查与隔离
│   ├── strategy/             # 策略运行服务
│   │   ├── backtest_service.py
│   │   ├── strategy_run_service.py
│   │   ├── input_assembler.py
│   │   └── artifact_writer.py
│   └── derived/              # 衍生数据服务
│       ├── materialization_orchestrator.py
│       ├── query_facade.py
│       ├── publication.py
│       └── research.py
└── main.py                   # FastAPI 启动入口
```

## 数据摄取

| 层级 | 说明 | 数据集 |
|------|------|--------|
| `T0_META` | 元数据基础层 | `calendar`, `stock_basic`, `etf_basic` |
| `T1_INCREMENTAL` | 日增量层 | `stock_daily`, `etf_daily`, `stock_status`, `adj_factor`, `fundamental`, `capital`, `macro` 等 |

### 任务特性

- **自动注册新证券**: 识别未解析的证券代码，自动获取基本信息并注册
- **部分失败容错**: 单个证券失败不阻断整体任务，记录 `skipped_list`
- **指数退避重试**: 网络波动自动重试（1min, 5min, 15min）
- **DQ 检查集成**: 写入数据前自动执行 L1+L2 数据质量检查
- **结构化日志**: 包含 `event` 字段，便于监控和告警

## 策略运行服务

| 服务 | 职责 |
|------|------|
| `BacktestService` | 回测编排（组装 bundle → EngineLoop → 审计收集 → 序列化报告） |
| `StrategyRunService` | 策略运行记录管理（create / running / completed / failed） |
| `StrategyInputAssembler` | 从 DataHub 组装 StrategyInputBundle |
| `ArtifactWriter` | 策略产物持久化（BacktestReport → SQLite） |

## 衍生数据服务

| 服务 | 职责 |
|------|------|
| `MaterializationOrchestrator` | 因子物化编排（依赖分析、级联触发） |
| `QueryFacade` | 衍生数据统一查询入口 |
| `CascadeProtocol` | 级联失效协议 |
| `EvaluationFacade` | 因子评估编排 |
| `ResearchService` | 研究 Spine / Dataset 管理 |

## CLI 命令

```bash
# 初始化
ditto init config    # 配置初始化
ditto init dq        # DQ 规则初始化
ditto init db        # 数据库初始化

# 数据摄入
ditto ingest metadata --date 2024-01-15
ditto ingest market --date 2024-01-15

# 历史回填
ditto backfill metadata --start 2024-01-01 --end 2024-01-31

# 查询
ditto query market --instrument 510300.SH --start 2024-01-01

# 版本
ditto version
```

## 使用示例

### 启动服务

```bash
# 开发环境（热重载）
pixi run -e dev dev

# 生产环境
pixi run server

# 健康检查
curl http://localhost:8000/healthz
```

### 手动触发 Flow

```bash
# 每日摄取
pixi run -e dev prefect flow-run run daily_ingestion_flow \
    --json '{"trade_date": "2024-01-02"}'

# 历史回填
pixi run -e dev prefect flow-run run backfill_flow \
    --json '{"start_date": "2024-01-01", "end_date": "2024-03-31"}'
```

## Token 安全配置

### 配置优先级

1. **keyring**（推荐）：Windows 凭据管理器 / macOS Keychain / Linux Secret Service
2. **~/.ditto/secrets.toml**（备用）：用户主目录配置文件
3. **TUSHARE_TOKEN** 环境变量（仅开发）

### 配置方式

**方式 1 - keyring（推荐）**：
```bash
pixi run -e dev python -c "
import keyring
keyring.set_password('ditto', 'tushare', 'YOUR_TOKEN')
"
```

**方式 2 - 备用文件**：
```toml
# ~/.ditto/secrets.toml
[tushare]
token = "YOUR_TOKEN"
```

## 相关文档

- [Port 层规范](CLAUDE.md)
- [v3 系统设计](../../docs/plans/2026-03-21-strategy-engine-system-design-v3.md)
- [Phase 2 实施计划](../../docs/plans/2026-03-22-strategy-engine-phase2-00-master.md)

## 变更记录

### v0.5.0 (2026-03-24)
**新增**
- `services/strategy/`: BacktestService、StrategyRunService、StrategyInputAssembler、ArtifactWriter
- `services/derived/`: MaterializationOrchestrator、QueryFacade、CascadeProtocol、EvaluationFacade
- `cli/`: Typer-based CLI 命令（ditto init/ingest/backfill/query/version）
- `registry/`: Dishka DI 容器（core/datahub/infra/contexts）

**改进**
- README 文档全面更新，反映当前代码库实际状态

### v0.3.0 (2026-01-23)
**新增**
- README 标准化，添加版本、日期、状态元数据
- 添加变更记录部分

**改进**
- 完善架构说明
- 重新组织文档结构

### v0.2.0 (2025-12-30)
**新增**
- 数据摄取调度服务实现
- Prefect 3 本地 Server 模式
- IngestionCoordinator 统一摄取协调器

### v0.1.0 (2025-12-27)
**新增**
- 初始应用结构
- FastAPI 基础框架
