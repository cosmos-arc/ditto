# Ditto 全面业界对标分析报告

> **日期**: 2026-04-24
> **基准**: 2026-04-07 深度对标 + 2026-04-17 全库审计修复后状态
> **对标平台**: QuantConnect LEAN、NautilusTrader、Microsoft Qlib、Panda QuantFlow、Panda Factor、Zipline、VectorBT、Backtrader、OpenBB、Databento 等 13+ 平台
> **前次评分**: 6.35/10 → **当前评分**: 6.8/10

---

## 1. 执行摘要

Ditto 经历 2026-04-17 全库架构审计（138 项发现）及 Phase 0-5 修复后，**工程质量跃居开源量化框架第一梯队** — 零 `type: ignore`（生产代码）、109 个 Protocol、27 条 importlinter 契约零违规。但在**交易能力维度**仍显著落后于 LEAN/NautilusTrader，呈现"架构先行、功能待补"的典型特征。

### 四域总评

| 域 | 评级 | 定位 |
|---|------|------|
| 架构能力 | **A-** | 业界领先 — 6 包分层 + Protocol 化 + CQRS 四象限互斥 |
| 工程质量 | **B+** | 量化指标优秀（异常体系统一、类型安全），但命名一致性/CQRS 纯净度有系统性问题 |
| 业务功能 | **D+** | 因子系统领先（A/A-），但交易/风控/归因严重缺失（F/D/D+） |
| 可演进性 | **B+** | Protocol 基础扎实、边界保护机械化，但 Data 层 44% 体量是主要风险 |

### 与前次评估的关键变化

| 变化 | 前次状态 | 当前状态 | 影响 |
|------|---------|---------|------|
| 异常体系 | P0 级碎片化（重复定义 + 冲突继承链） | 统一 `DittoError` 根 + 5 域根 | C → A |
| DataSource 抽象 | God Interface 26 抽象方法 | 5 个领域级 Fetcher Protocol | C+ → A |
| TradingLoop | 不存在 | Protocol 定义，EngineLoop 声明实现 | F → F+（架构基础就位） |
| 代码清晰度 | 未评估 | 发现 5 高 + 7 中严重度问题 | 首次纳入 B+ |
| 总分 | 6.35/10 | 6.8/10 | ↑ +0.45 |

---

## 2. 16 维度评分矩阵

### 2.1 架构能力域

| # | 维度 | 评分 | 趋势 | 对标业界 | 核心依据 |
|---|------|------|------|---------|---------|
| 1 | 分层架构 | **A** | → | 超越 LEAN | 6 包严格分层 + 27 条 importlinter 契约零违规 + CQRS 四象限互斥。LEAN 有 5 层 Framework 但无机械化执行 |
| 2 | Protocol 化抽象 | **A** | ↑ | 超越 LEAN | 109 个 Protocol 覆盖全栈：TradingLoop（回测/实盘）、6 Fetcher（数据源）、4 Storage（读写）、CommandHandler（泛型 CQRS）。LEAN 使用 abstract class + interface |
| 3 | 依赖注入 | **A** | → | 超越 LEAN | Dishka 3 层 Provider（Infra 5 + Data 14 + App 6），Composition Root 模式，25+ DI 模块全覆盖。Engine 层纯领域零 DI（正确） |
| 4 | Kernel 纯净度 | **A** | ↑ | 超越 LEAN | 13 文件 / 3,177 行 / 零外部依赖 / 13 业务子域。比 LEAN Common/（~100 文件、含序列化/配置等 I/O）更纯净 |

### 2.2 工程质量域

| # | 维度 | 评分 | 趋势 | 对标业界 | 核心依据 |
|---|------|------|------|---------|---------|
| 5 | 类型安全 | **A-** | → | 领先 | 生产代码 **0** `type: ignore`，strict basedpyright。342 处 `dict[str, object]` 集中在 error metadata（可接受） |
| 6 | 异常体系 | **A** | ↑↑ | 领先 | 统一 `DittoError(Exception)` 根 + 5 域根（Data/Engine/Analytics/App/Infra），P0 重复定义已消除 |
| 7 | 测试覆盖 | **A-** | ↑ | 领先 | 403 测试文件 / 6 包全覆盖 / 25 个 Protocol 一致性测试类 |
| 8 | 代码清晰度 | **B+** | ↑ | 对齐 | 见 [2.3 代码清晰度明细](#23-代码清晰度明细) |

### 2.3 代码清晰度明细

经深度审计发现以下问题：

**高严重度（混淆或误导）：**

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | `PositionReader` 同名冲突 | `app/process/execution/ports.py` vs `data/storage/execution/position_reader.py` | 开发者无法从名称区分 App 端口 vs Data 存储 |
| 2 | `IndicatorReader` 需要 DI 别名消歧 | `data/di/macro.py` L7: `import ... as MacroIndicatorReader` | 源头命名就应明确 |
| 3 | 3 个 `strategy_*_store.py` Reader+Writer 混装 + 错放 | `data/storage/metadata/strategy_*_store.py`（应在 `storage/strategy/`） | 双重违规：命名模式 + 目录归属 |
| 4 | App 层直接 import storage 类 | `app/providers.py` L54-55: `import InstrumentReader` | 绕过 Service 层抽象 |
| 5 | `_CatalogReader` Protocol 定义 3 次 | `data/services/derived/` 的 3 个文件各定义一个私有版本 | 违反 DRY，接口分叉 |

**中严重度（不一致或有噪音）：**

| # | 问题 | 详情 |
|---|------|------|
| 6 | CQRS 泄漏：8 Writer 含 `get_checksum()` | `data/storage/market/*/` 下 8 个 Writer 继承读方法 |
| 7 | CQRS 泄漏：3 Reader 含 `init_schema()` | `strategy_*_store.py` 中 Reader 含 DDL 写操作 |
| 8 | 双生类无指引 | `FeeScheduleReader`（内存 V1）vs `SQLiteFeeScheduleReader`（生产），无使用指引 |
| 9 | 缩写大小写不一致 | 类名 `Etf`/`FxBarsReader` vs 模块名 `etf/`/`fx/`，`FXQueryFacade` 用大写 |
| 10 | Kernel 38 符号扁平导出 | `from ditto_kernel import DerivedRole` 丢失 `strategy.` 子域上下文 |
| 11 | 中英双语 docstring 混用 | `storage/base/` 中文 vs `storage/runtime/` 英文，无统一语言策略 |
| 12 | Strategy 存储错放 metadata/ | `strategy_spec_store.py` 等应为独立 `storage/strategy/` 子域 |

**低严重度（样板或风格）：**

| # | 问题 |
|---|------|
| 13 | ~30 个 ParquetDatasetReader 子类 docstring 仅复述类名 |
| 14 | `ForwardReturnService` 在 query/ 模块但含生产环境危险操作（已加 runtime guard） |
| 15 | `FactorReader`（alpha 因子）vs `StockAdjFactorReader`（复权因子）同用 "factor" 但概念不同 |

### 2.4 业务功能域

| # | 维度 | 评分 | 趋势 | 对标业界 | 核心依据 |
|---|------|------|------|---------|---------|
| 9 | 因子编译器 | **A** | → | 超越 Qlib | 全流水线 Lexer→Parser→AST→Analyzer→Codegen + PIT 编译期安全（`shift(1)` 防未来数据）。Qlib 是单文件 ~500 行 AST |
| 10 | 因子评估 | **A-** | → | 领先 Qlib | IC 系列 / Fama-MacBeth / Grinold-Kahn IR / Regime IC / 正交化。超越 LEAN 基础 IC |
| 11 | 数据质量 | **A-** | → | 领先全部 | L1-L4 四层检查（技术/业务/统计/跨源），开源最全面 |
| 12 | A 股回测 | **B+** | → | 对标 Panda QuantFlow | T+1 / 100+1 / 涨跌停 / 费用完整建模，ExecutionAuditCollector 金融级审计。缺 LIMIT/STOP/结算模型 |
| 13 | 策略管线 | **B** | → | 对标 LEAN | StrategySpec 冻结声明式 + 8 DecisionStage + 4 策略模板。缺多策略运行时 |
| 14 | 风控 | **B-** | → | 略低于 LEAN | 10 条 Pre/Post 规则 + 回调通知。缺组合级风控 / 实时监控 / 行业暴露限制 |
| 15 | 执行层 | **C+** | → | 低于 LEAN | 仅 MARKET 单，BacktestBrokerage + Reality Model(5 Protocol)。无 Order 生命周期 / LIMIT / STOP / 算法执行 |
| 16 | 组合优化 | **D+** | → | 低于 VBT | 3 基础分配器（Equal/Score/InverseVol）。无优化器集成（cvxpy/scipy） |
| 17 | 归因分析 | **D** | → | 低于 LEAN | 仅绩效指标。无 Brinson 分解 / 因子归因 / 成本归因 |
| 18 | 回测/实盘一致性 | **F+** | ↑ | 远低于 LEAN | TradingLoop Protocol 提供架构基础（↑ 从 F），但无实盘 Brokerage / DataFeed |
| 19 | 多策略 | **F** | → | 远低于 LEAN | 单策略 / 单账户，无策略间隔离 |
| 20 | 实时数据 | **F** | → | 远低于 NautilusTrader | 纯批量获取，无流式 / WebSocket / Event-driven |
| 21 | 参数优化 | **F** | → | 远低于 VBT | 元数据结构存在但无优化框架（GridSearch/Bayesian/WalkForward） |

### 2.5 可演进性域

| # | 维度 | 评分 | 趋势 | 对标业界 | 核心依据 |
|---|------|------|------|---------|---------|
| 22 | 扩展点设计 | **A** | ↑ | 超越 LEAN | Protocol 化使新实现零侵入：新数据源→Fetcher、新存储→Reader/Writer、实盘→TradingLoop、新风控→PreTradeRule |
| 23 | 边界保护 | **A** | → | 超越 LEAN | 27 条 importlinter 契约机械化保护（包间 15 + App CQRS 4 + Data 子域 8），零违规。无其他量化框架做到 |
| 24 | Data 层可维护性 | **B-** | ↑ | 对齐 | 537 文件 / 84,068 行（44%）。Reader/Writer 已参数化（131 类），但 metadata/ 是万能桶、strategy 错放 |
| 25 | 代码可理解性 | **B-** | → | 对齐 | 命名冲突 / CQRS 泄漏 / 模块错放 / 扁平 re-export / 双语 docstring 增加认知负担 |

### 2.6 评分总览

```
架构能力域  ████████████████████░░░  A-  (4 维均值 10.0/12)
工程质量域  ███████████████████░░░░  B+  (4 维均值 10.5/12)
业务功能域  ███████████████░░░░░░░░  D+  (13 维均值 4.8/13)
可演进性域  ██████████████████░░░░░  B+  (4 维均值 9.0/12)
                                            总体 6.8/10
```

---

## 3. 差距分析

### 3.1 P0 — 功能性断层（阻碍 T1 达标）

| 差距 | 现状 | T1 要求（LEAN/NautilusTrader） | 影响 |
|------|------|-------------------------------|------|
| **订单管理** | 无 Order 概念，`TargetPortfolio` 直达 `RebalancePlan` | Order 是所有执行的一等公民，完整生命周期 state machine（Created→Submitted→PartialFill→Filled/Canceled） | 无法支撑 LIMIT/STOP/算法执行，风控无拦截点 |
| **回测/实盘一致性** | TradingLoop Protocol 定义但无实盘 Brokerage | `IBrokerage` 统一接口，`BacktestBrokerage`/`LiveBrokerage` 同构 | 无法上线 |
| **实时数据** | 纯批量获取 | DataFeed Protocol + WebSocket/Event-driven | 无法做日内策略和实时风控 |
| **组合级风控** | 仅 Instrument 级 Pre/Post 规则 | 每步 RiskGuard + 组合暴露 / 行业限制 / 熔断 | 无法管理真实资金风险 |

### 3.2 P1 — 能力短板（限制平台竞争力）

| 差距 | 现状 | T1 要求 | 差距量（预估行数） |
|------|------|---------|-------------------|
| 执行层深度 | MARKET only | LIMIT/STOP/GTC/DAY/VWAP/TWAP | ~2,000 |
| 组合优化 | 3 基础分配器 | MeanVariance/RiskParity/Black-Litterman + cvxpy | ~1,500 |
| 归因分析 | 绩效指标 | Brinson/因子归因/成本归因三层 | ~1,500 |
| 多策略运行时 | 单策略 | 多策略资金分配 + 策略间隔离 + 组合级风控 | ~3,000 |
| 参数优化 | 无 | GridSearch/Bayesian(Optuna)/WalkForward/OverfitDetector | ~2,000 |

### 3.3 P2 — 工程清晰度（增加维护成本）

| 差距 | 具体问题 | 修复量 |
|------|---------|--------|
| Data 层体量 | 537 文件 84K 行（44%），`metadata/` 是万能桶 | 重构 ~50 文件 |
| 命名冲突 | PositionReader/IndicatorReader 同名不同义 | 重命名 ~15 处引用 |
| CQRS 泄漏 | 8 Writer 含 `get_checksum()`、3 Reader 含 `init_schema()` | 移动 ~11 方法 |
| 模块错放 | strategy→metadata、ForwardReturn→query | 移动 ~6 文件 |
| Protocol 重复 | `_CatalogReader` 定义 3 次 | 合并为 1 处共享定义 |

---

## 4. 优势分析

### 4.1 独特护城河（超越所有对标平台）

| 优势 | 超越对象 | 难以复制原因 |
|------|---------|-------------|
| **因子表达式编译器** | 全部 13+ 开源平台 | 全流水线 Lexer→Parser→AST→Analyzer→Codegen + PIT 编译期安全。Qlib 是单文件 AST，LEAN 无因子编译器 |
| **importlinter 机械化治理** | 全部开源平台 | 27 条契约零违规，机械验证分层/CQRS/子域隔离。LEAN/Qlib/NautilusTrader 均依赖 code review |
| **L1-L4 数据质量引擎** | 全部开源平台 | 四层检查（技术/业务/统计/跨源验证）+ DQPatrolService 自动巡检。开源最全面 |
| **Kernel 零依赖纯净** | LEAN Common/ | 13 文件 / 3,177 行 / 零外部依赖 / 零 I/O。LEAN Common/ ~100 文件含序列化/配置 |

### 4.2 对标达标项

| 优势 | 对标平台 | 达标情况 |
|------|---------|---------|
| A 股规则精度 | Panda QuantFlow | T+1 / 100+1 / 涨跌停 / 费用完整建模，精度对标 |
| 声明式策略 | LEAN `QCAlgorithm` | StrategySpec 冻结 dataclass + 审计链，比 LEAN 自由代码更可审计 |
| DI 架构 | Cosmic Python | Dishka 3 层 Provider + Composition Root，教科书级 CQRS 分离 |
| 异常体系 | 后审计修复 | 统一根 + 5 域根 + 消除重复定义，从 P0 修复到 A |
| 回测引擎架构 | LEAN 5 层 Framework | Pipeline + Stage 模式，10 步流水线，审计评分 10/10 |

### 4.3 超越 LEAN 的设计决策

| 设计 | Ditto | LEAN |
|------|-------|------|
| 因子定义 | 表达式编译器（类型安全 + 编译期检查） | Python 函数自由定义（无编译期保证） |
| PIT 安全 | 编译器级（`shift(1)` 强制） | 配置级（需手动设置） |
| 分层执行 | 27 条 importlinter 契约 | 无机械化边界检查 |
| 数据质量 | L1-L4 四层 | 基本空值/类型检查 |
| 策略定义 | 冻结 dataclass + 版本治理 | 自由代码 |

---

## 5. 可演进性评估

### 5.1 已具备的扩展能力（架构就绪）

| 扩展点 | Protocol/接口 | 当前实现数 | 扩展方式 |
|--------|-------------|-----------|---------|
| 数据源 | 6 Fetcher Protocol | 3 (Tushare/TDX/FRED) | 实现 Fetcher + 注册 SourceRegistry |
| 存储 | DatasetReader/Writer + SqliteReader/Writer | 131 类 | 继承 ParquetDatasetReader + dataset 路径参数化 |
| 回测/实盘 | TradingLoop Protocol | 1 (EngineLoop) | 实现 LiveTradingLoop，零侵入 |
| 策略决策 | 8 DecisionStage | 8 内置 | 新增 Stage 注册 Pipeline |
| 风控规则 | PreTradeRule/PostTradeRule Protocol | 10 规则 | 实现规则 + 注册 RiskGuard |
| 现实模型 | FeeModel/FillModel/SlippageModel/SettlementModel | 各 1 | 实现模型 + 注入 EngineOptions |
| 执行规划 | ExecutionPlanner Protocol | 1 | 实现新 Planner |
| 因子 | FactorSpec + 表达式编译器 | 15+ 模块 | 新增 FactorSpec 或表达式 |
| DI 服务 | Dishka Provider | 25+ 模块 | 新增 Provider 注册 Composition Root |

**关键判断：架构层面的扩展能力已基本就绪。新能力的瓶颈不在接口设计，而在功能实现。**

### 5.2 扩展阻塞点

| 阻塞点 | 严重度 | 影响 | 建议阶段 |
|--------|--------|------|---------|
| **Order 概念缺失** | 🔴 高 | 无 Order → 无法风控拦截/拆单/实盘对接 | Phase 1 (V1.1) P0 |
| **Data 层体量** | 🟡 中 | 44% 代码集中，新开发者认知成本高 | 持续重构 |
| **命名清晰度** | 🟡 中 | PositionReader/IndicatorReader 冲突增加理解成本 | Phase 1 P1 |
| **事件/消息基础设施** | 🟡 中 | 无法支持实时风控/策略间通信 | Phase 2 |
| **DecisionFrame 无 Schema 保护** | 🟢 低 | 裸 `pl.DataFrame` 传递，无字段级约束 | Phase 1 |

### 5.3 T1 级评分预测

| 阶段 | 预估总分 | 架构 | 工程 | 功能 | 可演进 |
|------|---------|------|------|------|--------|
| 当前 (2026-04-24) | 6.8 | A- | B+ | D+ | B+ |
| Phase 1 后 (V1.1) | 8.3 | A | A- | B- | A- |
| Phase 2 后 (V2) | 9.1 | A | A | B | A |
| Phase 3 后 (T0) | 9.5 | A | A | A- | A |

---

## 6. T0 路线图

### Phase 1 — 引擎补全（V1.1，+1.5 分 → 8.3）

**目标：交易核心闭环，从"研究工具"进化为"可交易引擎"**

| 优先级 | 任务 | 预估规模 | 关键产出 | 依赖 |
|--------|------|---------|---------|------|
| **P0** | Order 模型 + 生命周期 State Machine | ~800 行 | Order / OrderTicket / OrderEvent / OrderStatus | 无（首要前置） |
| **P0** | ExecutionPlanner 增强（LIMIT/STOP/GTC/DAY） | ~600 行 | 基于 Order 的新执行路径 | Order 模型 |
| **P0** | SettlementModel（A 股 ETF T+1 结算） | ~300 行 | 现金/持仓 T+1 结算逻辑 | Order 模型 |
| **P1** | PortfolioOptimizer Protocol + cvxpy 集成 | ~800 行 | MeanVariance / RiskParity | 无 |
| **P1** | 归因分析框架 | ~1,000 行 | Brinson / 因子归因 / 成本归因 | 无 |
| **P1** | 代码清晰度专项 | ~50 文件 | 消除 P2 级工程问题（命名/CQRS/模块） | 无 |
| **P2** | 参数优化框架 | ~800 行 | GridSearch / Bayesian(Optuna) | 无 |
| **P2** | Regime 宏观指标扩展 | ~400 行 | InterestRate / Inflation / Liquidity | 无 |

**关键依赖：Order 模型是所有后续执行层任务的前置条件。**

### Phase 2 — 实盘准备（V2，+0.8 分 → 9.1）

**目标：回测/实盘一致性，可对接真实券商**

| 优先级 | 任务 | 预估规模 | 关键产出 | 依赖 |
|--------|------|---------|---------|------|
| **P0** | BacktestBrokerage 重构（基于 Order） | ~1,000 行 | 确定性撮合模拟 | Phase 1 Order |
| **P0** | DataFeed Protocol + 实时数据 | ~1,500 行 | WebSocket/TCP 流式数据 | 无 |
| **P0** | LiveBrokerage 抽象 + QMT/XtQuant 适配 | ~2,000 行 | 实盘交易通道 | BacktestBrokerage |
| **P1** | 组合级 RiskGuard（每步扫描） | ~800 行 | 暴露限制/行业集中度/熔断 | Order 模型 |
| **P1** | 多策略运行时 | ~1,500 行 | 策略隔离 + 资金分配 | RiskGuard |
| **P1** | 实时风控服务 | ~1,000 行 | Prometheus + 告警 | DataFeed |
| **P2** | 三层统计报表（Trade/Portfolio/Alpha） | ~800 行 | 结构化报告 | BacktestBrokerage |
| **P2** | 回测/实盘一致性验证 | ~600 行 | 结果差异检测 | LiveBrokerage |

### Phase 3 — 平台化（T0，+0.4 分 → 9.5）

**目标：生产级运营，可支撑外部用户**

| 优先级 | 任务 | 预估规模 | 关键产出 | 依赖 |
|--------|------|---------|---------|------|
| **P0** | 生产运维体系 | ~2,000 行 | Prometheus / Grafana / DR | Phase 2 |
| **P0** | OMS 订单管理系统 | ~1,500 行 | 订单路由/拆单/状态追踪 | LiveBrokerage |
| **P1** | API 产品化 | ~1,500 行 | RESTful API 完整覆盖 | Phase 2 |
| **P1** | 算法执行（VWAP/TWAP） | ~800 行 | 执行成本优化 | ExecutionPlanner |
| **P2** | Web Workbench | ~3,000 行 | 策略工作台 + 可视化 | API |
| **P2** | LLM/AI 集成 | ~1,000 行 | 因子挖掘/策略生成辅助 | API |

### 累计规模

| 阶段 | 新增代码 | 累计代码 |
|------|---------|---------|
| 当前 | — | ~208,000 行 |
| Phase 1 | ~5,200 行 | ~213,200 行 |
| Phase 2 | ~9,200 行 | ~222,400 行 |
| Phase 3 | ~9,800 行 | ~232,200 行 |
| **总增量** | **~24,200 行** | — |

---

## 7. 附录

### 7.1 对标平台速查表

| 平台 | 语言 | 核心优势 | 对标维度 | T1 级别 |
|------|------|---------|---------|---------|
| **QuantConnect LEAN** | C#/Python | 统一回测/实盘、40+ Broker 适配器 | 执行层/OMS/风控/统计 | 9.15/10 |
| **NautilusTrader** | Rust+Python | 高频低延迟、Actor 模型、零分支一致性 | 实时执行/Live Trading | 9.0/10 |
| **Microsoft Qlib** | Python | AI 驱动因子研究、25+ ML 模型 | 因子系统/实验管理 | 6.95/10 |
| **Panda QuantFlow** | Python | A 股规则建模、CTP 实盘 | A 股规则/风控 hooks | 7.5/10 |
| **Panda Factor** | Python | 因子评估（IC/衰减/Barra 正交化） | 因子评估 | 7.0/10 |
| **VectorBT Pro** | Python | 向量化回测、PyPortfolioOpt | 参数优化/组合优化 | 6.0/10 |
| **Zipline-Reloaded** | Python | Pipeline API、Factor/Filter/Classifier | 策略定义 | 5.0/10 |
| **OpenBB** | Python | 100 数据源、微内核插件 | 数据获取 | 5.5/10 |
| **Databento** | Rust+Python | 统一历史/实时数据 API | 实时数据 | 7.5/10 |

### 7.2 审计修复历史

| 日期 | 阶段 | 内容 | 状态 |
|------|------|------|------|
| 2026-04-17 | 审计启动 | 138 项发现（P0×2, P1×34, P2×55, P3×47） | — |
| 2026-04-18 | Phase 1 | Kernel Rich Domain（64+ 文件，4 新子域） | ✅ 完成 |
| 2026-04-19 | Phase 2 | Data Protocol + Reader/Writer 参数化 | ✅ 完成 |
| 2026-04-20 | Phase 3 | App Protocol + DataSource God Interface 拆分 | ✅ 完成 |
| 2026-04-20 | Phase 4 | TradingLoop Protocol 定义 | ✅ 完成 |
| 2026-04-22 | Phase 5 | Infra 清理 + 测试补充（41 新测试） | ✅ 完成 |
| 2026-04-24 | Phase 0 | 异常体系统一 + storage 子域隔离 + checksum/config 简化 | ✅ 完成 |

### 7.3 代码基线数据

| 指标 | 数值 |
|------|------|
| 总 .py 文件 | ~1,089 |
| 总代码行数 | ~208,000 |
| Production Protocol 数 | 109 |
| importlinter 契约数 | 27（0 违规） |
| 测试文件数 | 403 |
| 生产代码 `type: ignore` | 0 |
| `NotImplementedError`（合法守卫） | 11 |
| DI Provider 模块数 | 25+ |
| 最大包 | Data（537 文件 / 84,068 行 / 44%） |
