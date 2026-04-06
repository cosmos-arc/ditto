# Ditto: 量化投资系统

**版本**: v0.10.0 | **更新**: 2026-04-04 | **状态**: Phase 4 App 层提取完成

## 概要

面向 A 股 ETF 的全栈量化投资平台，对标 QuantConnect LEAN 架构。6 包 + 1 接口层分层设计，追求长期稳定 Alpha。

## 核心功能

- **策略引擎** — Pipeline + Stage 架构，8 个内置 Stage + 4 个策略模板（etf_rotation / etf_trend_swing / stock_sector_rotation / stock_selection_trend）
- **回测引擎** — EngineLoop 日历步进，PreTrade 6 规则 + PostTrade 4 Guard
- **执行层** — ExecutionPlanner + BacktestBrokerage + TradeBuilder + Reality Model（佣金/滑点/结算）
- **组合构建** — WeightAllocator（等权/评分/波动率倒数）+ ConstraintChecker
- **Expression DSL** — Pratt Parser 编译器，44 算子，Polars 向量化执行
- **因子评估** — IC / ICIR / Fama-MacBeth / Regime IC / Performance Attribution
- **数据质量** — 多源校验、PIT 安全、L1-L4 检查器
- **衍生数据** — 物化编排 + 发布安全（Shadow Diff / Certification）
- **任务调度** — Prefect 3（摄取/回填/修补/物化/发布）
- **CLI** — Typer 命令行（ditto init/ingest/backfill/query）

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│  interfaces (ditto_interfaces)                               │
│  FastAPI API / Typer CLI / Prefect Jobs / DI Composition Root│
└───────┬──────────────┬──────────────┬───────────────┬────────┘
        │              │              │               │
        v              v              v               v
┌──────────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────┐
│ ditto_app    │ │ ditto_    │ │ ditto_    │ │ ditto_data   │
│ CQRS 编排    │ │ analytics │ │ engine    │ │ 数据访问层    │
│ query/process│ │ 表达式编译 │ │ 策略/回测  │ │ CQRS + PIT   │
│ command/     │ │ 因子/研究  │ │ 执行/组合  │ │ 7 域服务     │
│ builders     │ │ 物化/评估  │ │ 风控/编排  │ │ 质量引擎     │
└──────┬───────┘ └─────┬─────┘ └─────┬─────┘ └──────┬───────┘
       │               │             │               │
       v               v             v               v
   ┌───────────────────────────────────────────────────────┐
   │  ditto_kernel          │  ditto_infra                 │
   │  零依赖共享内核         │  基础设施（零业务逻辑）        │
   │  identity/enums/clock/ │  config/db/cache/concurrency/ │
   │  events/specs          │  observability/notification   │
   └────────────────────────┴──────────────────────────────┘
```

**依赖方向**（import-linter 强制检查）：

```
interfaces → app → engine → data → infra
interfaces → analytics → engine → kernel
interfaces → data → kernel, infra
app → data, engine, analytics, infra
engine → kernel, data.errors, data.provider (Protocol)
analytics → kernel, data.errors, infra (logger)
data → kernel, infra
```

## 项目结构

```
ditto/
├── interfaces/                  # 应用入口（API / CLI / Jobs + DI）
│   └── src/ditto_interfaces/
│       ├── api/                 # FastAPI 路由
│       ├── cli/                 # Typer CLI
│       ├── jobs/                # Prefect 任务编排
│       ├── models/              # API 模型
│       ├── registry/            # Dishka DI 容器
│       ├── config/              # 接口层配置
│       └── main.py              # 启动入口
├── packages/
│   ├── app/                     # 应用编排层（CQRS）
│   │   └── src/ditto_app/
│   │       ├── query/           # 查询编排
│   │       ├── process/         # 流程编排
│   │       ├── command/         # 命令编排
│   │       ├── builders/        # DI builders
│   │       ├── providers.py     # Provider 注册
│   │       └── config.py
│   ├── engine/                  # 核心引擎
│   │   └── src/ditto_engine/
│   │       ├── alpha/           # Alpha 信号
│   │       ├── execution/       # 执行层
│   │       ├── backtest/        # 回测引擎
│   │       ├── portfolio/       # 组合构建
│   │       ├── accounting/      # 账户核算
│   │       ├── orchestrator/    # 编排器
│   │       ├── risk/            # 风控
│   │       └── events.py
│   ├── analytics/               # 分析层
│   │   └── src/ditto_analytics/
│   │       ├── expression/      # Expression DSL（lexer/parser/codegen/compiler）
│   │       ├── factors/         # 因子库
│   │       ├── evaluation/      # 因子评估
│   │       ├── research/        # 研究
│   │       ├── materialization/ # 物化编排
│   │       └── compile_cache.py
│   ├── data/                    # 数据访问层
│   │   └── src/ditto_data/
│   │       ├── services/        # 域服务（6 Facade）
│   │       ├── stores/          # 存储层（Reader/Writer）
│   │       ├── sources/         # 数据源（Tushare/FRED/TDX）
│   │       ├── models/          # 数据模型
│   │       ├── storage/         # 存储引擎
│   │       ├── runtime/         # 运行时（SQL/PIT/Freeze）
│   │       ├── quality/         # 数据质量
│   │       ├── query/           # 查询服务
│   │       ├── helpers/         # 辅助工具
│   │       ├── config/          # 数据层配置
│   │       └── di/              # DI 注册
│   ├── kernel/                  # 共享内核（零依赖）
│   │   └── src/ditto_kernel/
│   │       ├── identity.py      # 标识类型
│   │       ├── enums.py         # 枚举
│   │       ├── clock.py         # 时钟
│   │       ├── events.py        # 事件
│   │       └── specs.py         # 规约
│   └── infra/                   # 基础设施
│       └── src/ditto_infra/
│           ├── foundation/      # cache/checksum/concurrency/config/db/observability/util
│           └── services/        # notification
├── config/                      # 环境配置
│   ├── default/
│   ├── development/
│   ├── testing/
│   └── production/
├── docs/                        # 项目文档
│   ├── adr/                     # 架构决策记录
│   ├── design/                  # 设计文档
│   ├── plans/                   # 实施计划
│   ├── reviews/                 # 评审文档
│   ├── research/                # 研究文档
│   └── sprints/                 # Sprint 计划
├── scripts/                     # 工具脚本
└── (测试在各包内: packages/*/tests/ 和 interfaces/tests/)
```

## 快速开始

### 环境要求

- Python 3.13 | Pixi | Windows/Linux/macOS

### 安装

```bash
git clone <repository-url> && cd ditto
pixi install
```

### 配置

双层环境架构 — Pixi 环境选择 + `ENVIRONMENT` 运行时变量：

| 场景 | Pixi 环境 | ENVIRONMENT | 命令 |
|------|-----------|-------------|------|
| 本地开发 | `dev` | `development` | `pixi run -e dev ...` |
| 测试 | `dev` | `testing` | `pixi run -e dev test` |
| 生产 | `default` | `production` | `pixi run server` |

Tushare token 通过 keyring 配置：

```bash
pixi run -e dev python -c "
import keyring
keyring.set_password('ditto', 'tushare', 'your_token_here')
"
```

### 启动

```bash
pixi run -e dev ditto init db   # 初始化数据库
pixi run -e dev dev              # 开发模式（热重载）
pixi run server                  # 生产模式
```

### 开发命令

```bash
pixi run -e dev check            # lint + fmt + type + test --fast
pixi run -e dev test             # 单元测试（并行）
pixi run -e dev test --integration  # 集成测试
pixi run -e dev test --fast      # 快速测试
pixi run -e dev test --snapshot  # inline-snapshot
pixi run -e dev type             # basedpyright strict
pixi run -e dev lint             # ruff 检查
pixi run -e dev lint --fix       # 自动修复
pixi run -e dev fmt              # 格式化
pixi run -e dev ci               # 完整 CI
pixi run -e dev arch-check       # 分层依赖检查
```

## 开发路线图

- **Phase 0** — 环境与数据打底 (done)
- **Phase 0.5** — 数据质量验证 (done)
- **Phase 1** — 策略引擎：Pipeline + Stage + 4 模板 (done)
- **Phase 2** — 回测闭环：EngineLoop + PreTrade/PostTrade + Reality Model (done)
- **Phase 3** — 实盘接入：BrokerAdapter / 纸面交易（规划中）
- **Phase 4** — App 层提取：CQRS 编排 + DI builders + engine 独立包 (done)
- **Phase 5** — ML 增强：因子权重学习 / 多策略组合（远期规划）

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.13 |
| 数据 | polars, duckdb, parquet, sqlite |
| API | fastapi, pydantic, orjson, granian |
| 任务 | prefect 3.4+ |
| DI | dishka |
| CLI | typer |
| 可观测 | loguru, opentelemetry |
| 工具 | cachebox, tenacity, limits |
| 包管理 | pixi |
| 测试 | pytest, hypothesis, inline-snapshot |
| 质量 | basedpyright, ruff |

## 相关文档

- [CLAUDE.md](CLAUDE.md) — 开发规范
- [packages/engine/CLAUDE.md](packages/engine/CLAUDE.md) — Engine 层规范
- [packages/data/CLAUDE.md](packages/data/CLAUDE.md) — Data 层规范
- [packages/app/CLAUDE.md](packages/app/CLAUDE.md) — App 层规范
- [packages/analytics/CLAUDE.md](packages/analytics/CLAUDE.md) — Analytics 层规范
- [packages/infra/CLAUDE.md](packages/infra/CLAUDE.md) — Infra 层规范
- [packages/kernel/CLAUDE.md](packages/kernel/CLAUDE.md) — Kernel 层规范
- [interfaces/CLAUDE.md](interfaces/CLAUDE.md) — Interfaces 层规范

## 变更记录

### v0.10.0 (2026-04-04)
**Phase 4 App 层提取完成**
- App 层独立为 `ditto_app` 包（CQRS: query/process/command + builders）
- Engine 独立为 `ditto_engine` 包（从 core 拆分 alpha/portfolio/execution/accounting/backtest/orchestrator/risk）
- Kernel 独立为 `ditto_kernel`（零依赖共享内核: identity/enums/clock/events/specs）
- 目录结构扁平化：`interfaces/` 提升至根层级，移除 `apps/` 目录
- DI 泄漏修复 + engine 去冗余 + 测试迁移

### v0.9.0 (2026-03-24)
**文档与架构更新**
- README 全面更新反映代码库实际状态
- 架构图、项目结构、路线图、开发命令同步

### v0.8.0 (2026-03-23)
**Gap 补齐 + 质量加固**
- RegimeStage + validate_spec_params() + RebalancePlan
- DataHub 控制面: StrategyCatalogService + StrategyArtifactService
- 62 个新测试，3849 全通过，84.82% 覆盖率

*(更早版本见 git history)*

## 免责声明

本系统仅用于学习和研究目的，不构成投资建议。量化交易存在亏损风险，过去业绩不代表未来表现。使用者需充分理解风险、自行承担损失、遵守相关法律法规。
