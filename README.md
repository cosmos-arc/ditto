# Ditto: 量化投资系统

**版本**: v0.9.0
**最后更新**: 2026-03-24
**状态**: ✅ 策略引擎 + 回测闭环

## 概要

Ditto 是一个面向 A 股市场的全栈量化投资平台，专注于 ETF 行业轮动策略，采用工业级标准开发，追求长期稳定 Alpha。对标 QuantConnect LEAN 架构，分 Core / DataHub / Infra 三层核心包 + Port 应用层。

## 核心功能

- **策略引擎**: Pipeline + Stage 架构，内置 8 个 Stage + 4 个策略模板
- **回测引擎**: EngineLoop 日历步进 + PreTrade（6 规则）/ PostTrade（4 Guard）
- **执行层**: ExecutionPlanner + BacktestBrokerage + TradeBuilder + Reality Model（佣金/滑点/结算）
- **组合构建**: WeightAllocator（等权/评分/波动率倒数）+ ConstraintChecker
- **Expression DSL**: Pratt Parser 编译器，44 算子，Polars 向量化执行
- **因子评估**: IC / ICIR / Fama-MacBeth / Regime IC / Performance Attribution
- **数据质量**: 多源校验，PIT 安全，复权分离存储，L1-L4 检查器
- **衍生数据**: 物化编排 + 发布安全（Shadow Diff / Certification）
- **任务调度**: Prefect 3 编排（摄取/回填/修补/物化/发布）
- **CLI**: Typer-based 命令行（ditto init/ingest/backfill/query）

## 架构

```
┌─────────────────┐    ┌───────────────────────────────────────┐
│   Web UI        │    │   FastAPI Application (port/)          │
│   (Next.js)     │◄──►│   - API Routes                        │
│   Phase 4+      │    │   - CLI (Typer)                       │
└─────────────────┘    │   - Prefect Flows                     │
                       │   - DI (Dishka)                       │
                       │   - Services: Ingestion/Strategy/     │
                       │               Derived                  │
                       └───────────────────┬───────────────────┘
                                           │
┌──────────────────────────────────────────┼──────────────────────────┐
│ ditto-core                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │ strategy │ │execution │ │backtest  │ │portfolio │               │
│  │ Pipeline │ │ Planner  │ │EngineLoop│ │Allocator │               │
│  │ Stages   │ │ Brokerage│ │ PreTrade │ │Constraint│               │
│  │ Templates│ │ TradeBld │ │PostTrade │ │ Compare  │               │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
│  │engine    │ │accounting│ │quality   │                           │
│  │ Expr DSL │ │ Account  │ │ DQ Engine│                           │
│  │ Evaluator│ │ CashBook │ │ Checkers │                           │
│  └──────────┘ └──────────┘ └──────────┘                           │
├───────────────────────────────────────────────────────────────────┤
│ ditto-datahub                                                            │
│  CQRS: Sources → Services → Readers/Writers (Parquet/SQLite) → Runtime │
│  7 域: Metadata / Market / Fundamental / Capital / Macro / Features / Factors │
├───────────────────────────────────────────────────────────────────┤
│ ditto-infra                                                              │
│  Config / DB(SQLite) / Cache(cachebox) / Concurrency(FileLock) /        │
│  Observability(loguru+OTel) / Notification(Telegram+Email+Webhook)       │
└───────────────────────────────────────────────────────────────────┘
```

**依赖方向**: `port → core → datahub → infra`（单向依赖，import-linter 强制检查）

## 快速开始

### 环境要求

- Python 3.12+ (实际使用 3.13)
- Pixi (包管理器)
- Windows/Linux/macOS

### 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd ditto
   ```

2. **安装依赖**
   ```bash
   pixi install
   ```

3. **配置环境变量**

   系统采用双层环境架构，配置文件按环境分组在 `config/` 目录：

   ```bash
   config/
   ├── development/    # 开发环境配置
   ├── testing/        # 测试环境配置
   └── production/     # 生产环境配置
   ```

   设置运行时环境（默认为 development）：
   ```bash
   export ENVIRONMENT=development  # Linux/macOS
   ```

   **注意**：Tushare token 需要通过 keyring 或 `~/.ditto/secrets.toml` 配置
   ```bash
   # Keyring（推荐）
   pixi run -e dev python -c "
   import keyring
   keyring.set_password('ditto', 'tushare', 'your_token_here')
   "
   ```

4. **初始化数据库**
   ```bash
   pixi run -e dev ditto init db
   ```

5. **启动服务**
   ```bash
   pixi run -e dev dev      # 开发模式（热重载）
   pixi run server          # 生产模式（4 workers）
   ```

### 开发命令

```bash
# 代码质量
pixi run -e dev lint          # ruff 检查
pixi run -e dev lint --fix    # 自动修复
pixi run -e dev fmt           # 格式化
pixi run -e dev type          # basedpyright 类型检查

# 测试
pixi run -e dev test              # 单元测试（并行）
pixi run -e dev test --unit       # 只运行单元测试
pixi run -e dev test --integration # 只运行集成测试
pixi run -e dev test --fast       # 快速测试（跳过慢速）
pixi run -e dev test --snapshot   # 支持 inline-snapshot

# 快速验证（开发时）
pixi run -e dev check          # lint + fmt + type + test --fast + arch-check

# 完整检查（CI 用）
pixi run -e dev ci             # 完整 CI 流水线

# 架构边界检查
pixi run -e dev arch-check     # import-linter 分层依赖检查
```

## 项目结构

```
ditto/
├── apps/
│   ├── port/                  # 应用层（FastAPI + Prefect + CLI）
│   │   ├── src/
│   │   │   ├── api/           # API 路由
│   │   │   ├── cli/           # Typer CLI 命令
│   │   │   ├── jobs/          # Prefect 任务编排
│   │   │   ├── services/      # 应用服务
│   │   │   │   ├── ingestion/ # 数据摄取
│   │   │   │   ├── strategy/  # 策略运行
│   │   │   │   └── derived/   # 衍生数据
│   │   │   ├── registry/      # Dishka DI 容器
│   │   │   └── main.py        # 启动入口
│   │   └── tests/             # 测试
│   └── web/                   # Next.js 前端 (Phase 4+，待实现)
├── packages/
│   ├── core/                  # 核心业务逻辑（纯函数，无 I/O）
│   │   ├── src/ditto_engine/
│   │   │   ├── strategy/      # 策略引擎（Pipeline + Stage + 模板）
│   │   │   ├── execution/     # 执行层（Brokerage + Planner + Reality Model）
│   │   │   ├── backtest/      # 回测引擎（EngineLoop + PreTrade + PostTrade）
│   │   │   ├── portfolio/     # 组合构建（Allocator + Constraint）
│   │   │   ├── accounting/    # 共享账户契约（Account + CashBook + OrderBook）
│   │   │   ├── engine/        # Expression DSL + 因子评估 + 物化
│   │   │   └── quality/       # 数据质量引擎（L1-L4 检查器）
│   │   └── tests/
│   ├── datahub/               # 数据访问层（CQRS + PIT）
│   │   ├── src/ditto_data/
│   │   │   ├── services/      # 域服务（6 Facade + Strategy + Audit）
│   │   │   ├── stores/        # 存储层（Reader/Writer 分离）
│   │   │   ├── sources/       # 数据源（Tushare / FRED / TDX）
│   │   │   ├── models/        # 数据模型（50+ Record）
│   │   │   └── runtime/       # 运行时支持（SQL/PIT/Freeze）
│   │   └── tests/
│   └── infra/                 # 基础设施层（零业务逻辑）
│       ├── src/ditto_infra/
│       │   ├── foundation/    # 基础模块（config/db/cache/concurrency/observability）
│       │   └── services/      # 基础服务（notification）
│       └── tests/
├── config/                    # 环境配置（development/testing/production）
├── docs/                      # 项目文档
│   ├── adr/                   # 架构决策记录
│   ├── design/                # 设计文档
│   ├── plans/                 # 实施计划
│   ├── reviews/               # 评审文档
│   ├── research/              # 研究文档
│   └── sprints/               # Sprint 计划
├── scripts/                   # 工具脚本
└── tests/                     # E2E 测试
```

## 开发路线图

### Phase 0: 环境与数据打底 ✅
- [x] 项目脚手架 + pixi + pre-commit
- [x] Infra 层（config/db/cache/concurrency/observability）

### Phase 0.5: 数据质量验证 ✅
- [x] DataHub（CQRS + 7 域 + PIT 安全 + SourceSchema）
- [x] 多数据源（Tushare / FRED / TDX）
- [x] Golden Dataset 验证

### Phase 1: 策略引擎 ✅
- [x] Accounting 契约层（Account / CashBook / OrderBook / Position）
- [x] Strategy 决策层（StrategySpec / Pipeline / DecisionStage Protocol）
- [x] 内置 Stages（Universe / Signal / Scoring / Filtering / Selection / RiskLock / Trend / Regime）
- [x] Portfolio 构建（WeightAllocator / ConstraintChecker）
- [x] 策略模板（etf_rotation / etf_trend_swing / stock_sector_rotation / stock_selection_trend）
- [x] Expression DSL 编译器 + 因子评估指标体系

### Phase 2: 回测闭环 ✅
- [x] Execution 层（Planner / Brokerage / TradeBuilder / Reality Models）
- [x] Backtest EngineLoop + ParquetDataFeed
- [x] PreTrade 风控（6 规则）+ PostTrade Guards（4 个）
- [x] BacktestReport + RunManifest + 审计收集
- [x] Port 层编排（BacktestService / StrategyRunService / ArtifactWriter）
- [x] T+1 冻结逻辑 + 批内滚动更新

### Phase 3: 实盘接入（规划中）
- [ ] BrokerAdapter 实现
- [ ] 纸面交易验证
- [ ] 实盘小资金测试

### Phase 4: ML 增强（远期规划）
- [ ] 因子权重学习
- [ ] 多策略组合
- [ ] 可转债策略

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.13 |
| 数据处理 | polars, duckdb |
| API | fastapi, pydantic, orjson |
| ASGI | granian |
| 任务 | prefect 3.4+ |
| DI | dishka |
| CLI | typer |
| 日志 | loguru |
| 链路追踪 | opentelemetry |
| 缓存 | cachebox |
| 重试 | tenacity |
| 限流 | limits |
| 存储 | parquet, sqlite |
| 包管理 | pixi |
| 测试 | pytest, hypothesis, respx, inline-snapshot |
| 类型检查 | basedpyright |
| 代码质量 | ruff |

## 相关文档

- [CLAUDE.md](CLAUDE.md) — 项目开发规范
- [v3 策略引擎系统设计](docs/plans/2026-03-21-strategy-engine-system-design-v3.md)
- [Phase 2 实施计划](docs/plans/2026-03-22-strategy-engine-phase2-00-master.md)
- [Phase 2-5 路线图](docs/plans/2026-03-21-strategy-engine-phase2-5-roadmap.md)
- [设计文档](docs/design/README.md) — 系统架构设计
- [Sprint 规划](docs/sprints/README.md) — 迭代计划
- [ADR](docs/adr/README.md) — 架构决策记录
- [packages/core/CLAUDE.md](packages/core/CLAUDE.md) — Core 层规范
- [packages/datahub/CLAUDE.md](packages/datahub/CLAUDE.md) — DataHub 层规范
- [apps/port/CLAUDE.md](apps/port/CLAUDE.md) — Port 层规范
- [packages/infra/CLAUDE.md](packages/infra/CLAUDE.md) — Infra 层规范

## 变更记录

### v0.9.0 (2026-03-24)
**改进**
- README 文档全面更新，反映当前代码库实际状态
- 更新架构图、项目结构、路线图、开发命令
- 新增技术栈表格
- 补充 v3 策略引擎系统设计和各层 CLAUDE.md 文档链接

### v0.8.0 (2026-03-23)
**新增** — Phase 6: Gap 补齐 + 质量加固 Sprint
- RegimeStage（市场状态检测）、validate_spec_params()、RebalancePlan
- DataHub 控制面：StrategyCatalogService + StrategyArtifactService
- 62 个新测试，3849 个测试全部通过，84.82% 覆盖率

### v0.7.0 (2026-03-19)
**新增**
- **评估指标增强**: periods_per_year 可配置化、Sharpe 纳入无风险利率、Calmar Ratio
- **尾部风险指标**: CVaR 95/99, 偏度, 超额峰度, 最大单日损失
- **Grinold-Kahn IR**: Gordon Ritter 自相关修正
- **Fama-MacBeth**: 两步回归（支持多因子）
- **Regime-Adjusted IC**: Markov Regime Switching + 转移矩阵
- **Performance Attribution**: Selection/Timing/Interaction 分解
- **发布安全 DQ 增强**: 覆盖率、均值/标准差/偏度、分布漂移
- **失效传播韧性**: 修复失败不终止、死信队列、优先级队列、跨事件去重

### v0.6.0 (2026-03-01)
**新增**
- FRED 数据源集成（美国宏观数据）
- 外汇（FX）日线数据存储与 API
- 大宗商品（Commodity）日线数据存储与 API（含 VIX 指数）
- Exchange 层重构：协议 + DI 注入模式
- 全局时区工具（zoneinfo + DST 处理）

## 免责声明

本系统仅用于学习和研究目的，不构成投资建议。使用者需要：

1. 充分理解量化交易风险
2. 自行承担投资损失
3. 遵守相关法律法规
4. 在实盘交易前进行充分测试

**风险提示**: 量化交易存在亏损风险，过去业绩不代表未来表现。
