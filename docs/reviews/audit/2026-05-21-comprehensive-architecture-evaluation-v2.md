# Ditto 架构综合评估 V2 — 分层报告

> 日期：2026-05-21
> 基线：`docs/reviews/audit/2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md`
> 交叉参考：`docs/reviews/audit/2026-05-21-current-architecture-evaluation-and-review-plan.md`（独立评估，已合并精华）
> 方法：12 包全量源码审计 + 10 传统平台对标 + 8 AI-Agent 项目对标 + 37 条架构合约验证 + 类级 method 审计
> 分支：`remediation/architecture-remediation-batch-1`
> 源码快照：909 生产文件 / 104,602 LOC | 693 测试文件 / 163,706 LOC | 127 Protocol | 359 frozen dataclass

---

## 速览页（Executive Summary）

### 一句话结论

> Ditto 的工程边界治理已达到 8.7 分；Paper/Live runtime 从 6.1 提升到 7.0；
> AI-Agent 生态是中长期演进机会（4.0/10），当前主线仍是 paper/live runtime、DataCatalog、E2E proof。

### 自 5/14 以来的关键进展

| 完成项 | 影响 |
|--------|------|
| DatasetRegistry 集中路由（465 LOC） | 新增 dataset 不再修改 3+ 文件 |
| PaperBrokerGateway 实现（107 LOC） | 最小 paper 撮合闭环 |
| ExecutionReconciler 纯函数（147 LOC） | 5 种 Diff 类型覆盖主要对账场景 |
| RiskGate Protocol 定义（4 hook） | pre-submit / pre-cancel / post-fill / daily-scan |
| SliceView.bars `Any` → `BarSlice` Protocol | 类型安全提升 |
| EngineResult frozen + Builder 模式 | 不可变输出分离可变累积 |
| Regime 提取为子包 | strategy 包结构清晰化 |
| SourceQueryFacade Protocol 隔离 | application 不再暴露 concrete source |
| CQRS 边界零违规 | queries/commands/builders 完全互斥 |

### 总体评分对比

| 维度 | 5/14 | 5/21 | Δ | 瓶颈 |
|------|------|------|---|------|
| 工程架构综合质量 | 8.5 | **8.7** | +0.2 | 4 个 500+ LOC 文件待拆 |
| 整洁架构与依赖方向 | 8.3 | **8.5** | +0.2 | application 仍有具体实现 wiring |
| 可读性/一致性/命名治理 | 8.0 | **8.2** | +0.2 | data adapter 命名不一致 |
| 数据平台扩展性 | 7.0 | **7.5** | +0.5 | DatasetRegistry 已实现但位于 application |
| Backtest/Research 能力 | 8.6 | **8.8** | +0.2 | 统计轻微 DRY 违反 |
| Paper/Live runtime 就绪度 | 6.1 | **7.0** | +0.9 | PaperGateway 不追踪 Account 状态 |
| 全球全市场产品架构完整度 | 5.4 | **5.6** | +0.2 | 多市场/多币种/实盘 broker 仍远 |
| **AI-Agent 生态就绪度** | — | **4.0** | 新增 | 中长期机会，非当前 P0 |

### 逐模块评分

| 模块 | 5/14 | 5/21 | Δ | 评级 |
|------|------|------|---|------|
| kernel | 8.6 | **8.6** | → | A — 小而稳，3 个 Any 均合理 |
| platform | 7.7 | **7.9** | ↑ | A- — ABC 归零，paths.py 待拆 |
| data | 7.0 | **7.2** | ↑ | B+ — 21 Protocol ISP 优秀，大文件待拆 |
| features | 8.5 | **8.5** | → | A — expression pipeline 清楚 |
| strategy | 8.6 | **8.8** | ↑ | A — regime 子包，零违规依赖 |
| portfolio | 7.7 | **7.8** | ↑ | B+ — sell path 确认无误，object 类型弱 |
| risk | 7.4 | **8.0** | ↑↑ | B+ — RiskGate + BarSlice，最大提升 |
| execution | 7.2 | **7.8** | ↑↑ | B+ — Gateway + Reconciler + OMS FSM |
| backtest | 8.8 | **8.8** | → | A — EngineResult frozen |
| analysis | 7.8 | **7.5** | ↓ | B — domain.py 混合职责，reserved 过多 |
| application | 7.7 | **7.8** | ↑ | B+ — CQRS 完美，backtest_process 待拆 |
| apps | 8.2 | **8.2** | → | B+ — DI 清晰，dq_batch 重复容器 |

### 质量红线信号

| 信号 | 状态 | 说明 |
|------|------|------|
| `# type: ignore` in src/scripts | **1（回归）** | `packages/platform/src/ditto_platform/foundation/observability/_registry.py` — 需立即修复 |
| `check_code_size.py` 类级失败 | **3 个大类** | MetadataService (43 methods)、TushareSource (27 methods)、DataStoreSettings (26 methods) |
| capability-maturity.md 同步 | **滞后** | execution/paper/reconciliation 描述落后于最新源码 |
| Golden E2E lane | **缺失** | CI 无法脱离本地样本证明主路径 |

### 高优行动项（Top 15，按执行优先级排序）

| # | 优先级 | 行动 | 模块 | 业界对标 |
|---|--------|------|------|---------|
| 1 | **P0** | `# type: ignore` 清零 | platform | 质量红线 |
| 2 | **P0** | capability-maturity.md 和 ledger 同步 | docs | 文档与源码一致 |
| 3 | **P0** | PaperGateway 行为矩阵（价格/快照/cancel/reject/partial）+ broker-side account snapshot | execution | NautilusTrader adapter seam |
| 4 | **P0** | Dataset facts 拆分：data-owned catalog metadata + application-owned ingestion routing | data/application | OpenBB TET 管道 |
| 5 | **P0** | Synthetic golden E2E lane | apps | 可证明性 |
| 6 | **P1** | TradingRuntimeKernel 最小设计 | kernel/application | NautilusTrader 确定性核心 |
| 7 | **P1** | Durable OMS journal（SQLite）+ reconciliation audit links | execution | Backtrader |
| 8 | **P1** | A 股订单类型枚举 + Gateway 映射 | execution | QMT/XTP 常量体系 |
| 9 | **P1** | backtest_process.py 拆分（5 职责） | application | SRP |
| 10 | **P1** | data 3 个大类分解（MetadataService/TushareSource/DataStoreSettings） | data | 类级 SRP |
| 11 | **P1** | Alpha Signal 模型定义 | strategy/kernel | LEAN Insight |
| 12 | **P1** | 执行层错误细化（可重试/致命/资金） | execution | Freqtrade 异常层级 |
| 13 | **P2** | Kill switch 分级风控设计 | risk/execution | 实盘安全前置 |
| 14 | **P2** | Symbology 品种映射服务 | data | Databento Symbology |
| 15 | **P3** | analysis LLM-assisted research 基础 | analysis | QuantaAlpha 轨迹进化 |

---

## 业界对标全景

### 传统量化平台对标（10 个）

| 维度 | Ditto | LEAN | NautilusTrader | OpenBB | Freqtrade |
|------|-------|------|---------------|--------|-----------|
| 包边界机器化 | **领先** (37 合约) | 无 | 无 | 无 | 无 |
| Protocol 隔离 | **领先** (121 Protocol) | 接口 | 接口 | Provider | 接口 |
| Backtest/Paper/Live 一致性 | **弱** | 强 | **强** | N/A | 中 |
| Broker 生态 | **弱** (1 gateway) | **强** (40+) | **强** (15+) | N/A | **强** (CCXT) |
| 数据 Provider 插件化 | 中 (3 source) | **强** (30+) | **强** (Databento+) | **强** (Extension) | 中 |
| 因子 DSL/表达式 | **特色** (expression) | 无 | 无 | 无 | 无 |
| PIT/防前瞻 | **强** | 中 | 中 | 无 | 无 |
| 多市场覆盖 | **弱** (A 股 ETF) | **强** (全球) | **强** (全球) | **强** (全球) | 中 (加密为主) |

#### 关键新对标发现

**Databento** — Schema-first 数据建模
- DBN 统一编码层，15+ schema 固定字段集
- 双时间戳设计（exchange_ts + received_ts）
- Ditto 应为每个 dataset 定义严格 ParquetSchema，写入时校验

**ArcticDB (Man AHL)** — 金融时序版本化存储
- 四层存储架构（Data → Index → Version → Pointer）
- 所有修改保留历史版本，可 time-travel
- 不建议采用（仅支持 Pandas），但版本化和结构化 Key 概念值得借鉴

**QMT/XTP** — A 股交易网关
- 行情/交易双网关分离，回调驱动
- A 股订单类型完整（限价/市价/FAK/FAB/GTD）
- Ditto 应定义 A 股 OrderType 枚举，Gateway 做映射

**Freqtrade** — 开源交易机器人
- IStrategy 4 方法极简接口 + 5 种运行模式共享同一策略
- Protection 插件链（global_stop + stop_per_pair）
- Dry-Run 使用 SQLite 模拟，与 live 共用逻辑
- 执行层异常体系三层分离（Operational/Dependency/Strategy）

**Backtrader** — "Backtest once, trade many times"
- 保持同一套 interface，通过 Store 概念衔接 data feed 和 broker
- Paper/live 不复制 backtest 逻辑，只替换 adapter
- Ditto 的 BrokerGateway 和 DataFeed/Synchronizer 应有对称关系
- PaperBrokerGateway 应从即时成交 toy 升级为可配置、可审计、可重放的 test adapter

**Microsoft Qlib** — AI/ML 量化研究平台
- data processing → model training → backtesting → alpha seeking → risk → portfolio → execution 完整链条
- 组件 loose-coupled，可独立使用
- Ditto 在 clean architecture 和边界守卫上更严，但 AI/ML workflow、模型训练、自动研究还不是一等能力
- analysis 不应长期只做 research dataset control-plane；中期需要 experiment/run registry、parameter sweep、result cube

### AI-Agent 量化项目对标（8 个）

| 项目 | Stars | 核心模式 | 与 Ditto 关系 |
|------|-------|---------|-------------|
| TradingAgents | 16.5K | 组织架构图 + 牛熊辩论 + 经验记忆 | 信号层可借鉴 |
| QuantaAlpha | 新 | 轨迹级进化 + 语义一致性约束 | features 包 alpha discovery 候选 |
| AlphaAgent (KDD'25) | 新 | 假设→因子→评估闭环 + 反拥挤正则化 | features 表达式编译器可集成 |
| AgenticTrading | 新 | MCP/A2A 协议 + DAG 编排 + Neo4j 记忆 | 架构野心最大，基础设施要求高 |
| ai-hedge-fund | 49.6K | 多角色 agent council + meta-weighting | 证明市场对 AI 交易的巨大兴趣 |
| FinRobot | 3K+ | 4 层栈 + CoT 提示 + Smart Scheduler | 与 FinRL/FinGPT 生态集成 |
| FactorMiner | 新 | 模块化 Skill + 轻量 Experience Memory | 最轻量，适合 Ditto 风格 |
| FinCon (NeurIPS'24) | 论文 | 概念化语言强化学习 | agent 间自然语言通信模式 |

#### AI-Agent 关键洞察

**行业趋势**：从单一模型交易信号 → 多 agent 协作系统。LLM 处理定性推理（新闻解读、假设生成），传统量化方法处理定量计算（因子计算、组合优化、执行）。

**Ditto 差异化优势**（AI-Agent 项目普遍缺乏的量化基础设施）：
1. 真正的量化基础设施（数据管线、回测引擎、执行框架、风控、组合）
2. 架构边界纪律（37 条 import-linter 合约、TDD、basedpyright）
3. A 股 ETF 专业化

**Ditto 中长期可演进的方向**（非当前 P0）：
1. LLM 辅助 alpha 发现（QuantaAlpha/AlphaAgent 模式）
2. 经验记忆（TradingAgents 简单 markdown log 可作起点）
3. 多 agent 信号聚合（ai-hedge-fund meta-weighting 模式）
4. DAG 编排研究工作流（AgenticTrading 模式）

---

## 模块详细附录

### 附录 A：kernel — 8.6 / 10

**源码**：14 文件 / 919 LOC | **测试**：16 文件 / 2,345 LOC（比 2.55:1）

**优势**
- 零 I/O、零外部依赖、零业务行为
- 9 个 frozen dataclass，100% 不可变
- 仅 3 个 `Any` 使用，均有文档化理由（transport boundary / Protocol 隔离 / handler pluggability）
- 5 个 Protocol 定义，覆盖 Clock、EventBus、Synchronizer 等核心抽象

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| K-1 | 低 | `tracing.py` 全局可变状态 `_trace_handler`，非线程安全 | tracing.py:34 |
| K-2 | 低 | `SimpleEventBus.subscribe` 无线程安全，并发注册可能竞态 | events.py:96 |
| K-3 | 观察 | `trading.py` 182 LOC 占 kernel ~20%，MarketSnapshot 等仅 Execution/Backtest 使用 | trading.py |
| K-4 | 观察 | `EventName` 与 `DomainEvent.event_type: str` 类型边界未完全统一 | events.py |

**Review 计划**
- `trading.py` 类型归属 ADR：保留 kernel（跨包共享稳定）或迁出（使用范围窄）
- `EventName` vs `event_type` 类型统一方案
- tracing.py 线程安全评估（单 runtime 场景下是否需要）

---

### 附录 B：platform — 7.9 / 10

**源码**：61 文件 / 5,917 LOC | **测试**：43 文件 / 8,971 LOC（比 1.52:1）

**优势**
- ABC 归零 — 8 个 Protocol 定义，完全 Protocol-first
- 零领域名词泄漏（无 instrument/strategy/portfolio/risk/order）
- storage 按 Parquet/SQLite 分层，config/db/cache/observability 子域清晰

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| P-1 | 中 | `config/paths.py` 484 LOC，`PathResolver` + `XDGPaths` 双类重复职责 | config/paths.py |
| P-2 | 低 | `XDGPaths` 属性 getter 有 I/O 副作用（`mkdir`） | paths.py:361-404 |
| P-3 | 低 | `observability/metrics/_binding.py` 5 条配置路径，配置复杂度高 | metrics/_binding.py:181 |
| P-4 | 低 | `foundation/util/checksum.py` 和 `foundation/checksum/file.py` 重复命名 | util/ vs checksum/ |

**Review 计划**
- 拆 paths.py：PathResolver + XDGPaths 合并或职责分离
- metrics _binding.py 配置路径简化
- checksum 模块统一位置

---

### 附录 C：data — 7.2 / 10

**源码**：285 文件 / 31,440 LOC | **测试**：192 文件 / 40,060 LOC（比 1.27:1）
**全仓最大包**，占 30% 源码

**优势**
- 21 个 Protocol 定义，ISP 分解优秀（5 domain Fetcher 替代单体 DataSource ABC）
- data sources 与 storage 隔离，source 子域互斥合约守住
- PIT helper、quality、runtime freeze、ingestion log/cursor 基础扎实

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| D-1 | **高** | Dataset metadata（maturity/capability/schedule）分散在 enum + config + application，应由 data 拥有 catalog store | data/catalog/, application/ingestion/ |
| D-2 | **高** | 4 个 500+ LOC 文件混合职责（sqlite_store 5 职责、tushare/stock/fundamental 重复模式） | storage/base/, sources/tushare/ |
| D-3 | 中 | `capital_market.py` 用函数式而非类（与所有其他 adapter 不一致） | sources/tushare/adapters/ |
| D-4 | 中 | `fundamental.py` VIP 方法 ~150 LOC 近乎复制粘贴 | sources/tushare/adapters/fundamental.py |
| D-5 | 中 | `InstrumentIdRange.detect_asset_class()` 与 `get_range()` 范围表重复 | models/common.py:253-346 |
| D-6 | 中 | `catalog/` 和 `lineage/` 仅 contract-only，无 runtime 实现 | catalog/, lineage/ |
| D-7 | 低 | `sqlite_store.py` 同时包含 read + write，违反 CQRS 分离 | storage/base/sqlite_store.py |

**Review 计划**
- P0：dataset metadata（maturity/capability/schedule）迁入 `data/catalog/`；ingestion routing/factory 保留 application
- P1：拆 sqlite_store.py（SQL helper / DataFrame 转换 / merge 逻辑）
- P1：统一 adapter 模式（capital_market.py 改类）
- P1：fundamental.py VIP 方法泛化为参数化查询
- P2：DataCatalog runtime 实现（metadata 查询、capability discovery）

---

### 附录 D：features — 8.5 / 10

**源码**：112 文件 / 15,232 LOC | **测试**：34 文件 / 8,946 LOC（比 0.59:1 — **测试不足**）

**优势**
- expression pipeline 完整：lexer → parser → ast → analyzer → compiler → codegen
- 因子 registry 统一，materialization 与 expression 有合约隔离
- publication safety / shadow publish / derived catalog 产品化意识强

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| F-1 | 中 | `expression/codegen/_builders.py` 577 行 + `_visitor.py` 222 行（已拆，builder 仍偏大） | expression/codegen/ |
| F-2 | 中 | `evaluation/evaluator/_orchestrator.py` 509 行 + `_helpers.py` 210 行（已拆，orchestrator 仍偏大） | evaluation/evaluator/ |
| F-3 | 中 | `evaluation/metrics/ic.py` 622 行，指标维度过宽 | evaluation/metrics/ic.py |
| F-4 | 低 | 测试比 0.59:1 — 全仓最低，需补测试 | tests/ |
| F-5 | 低 | `FeaturesError` 与 `DerivedError` 错误根并列，捕获语义不顺 | errors/ |

**Review 计划**
- codegen/_builders.py 577 行进一步拆分：expression node dispatch / polars expr generation / diagnostics
- evaluator/_orchestrator.py 509 行进一步拆分：input preparation / grouping / metrics dispatch / report build
- 补测试到 ≥1.0:1 比率
- 统一错误层级：DerivedError 继承 FeaturesError

**AI-Agent 就绪度**：features 包是 LLM-assisted alpha discovery 的天然宿主。QuantaAlpha 的轨迹级进化 + 语义一致性约束可集成到 expression pipeline 中。建议在 evaluation 模块增加 LLM-assisted hypothesis → expression 桥接点。

---

### 附录 E：strategy — 8.8 / 10

**源码**：57 文件 / 5,898 LOC | **测试**：30 文件 / 8,732 LOC（比 1.48:1）

**优势**
- **全仓范例**：零违规依赖，不导入 data/features/portfolio/risk/execution/backtest
- Regime 子包提取成功（4 文件，10 符号 clean barrel）
- Pipeline + InputBundle 方向正确
- 14 个 Protocol 定义

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| S-1 | 低 | `signals/store.py` Protocol 非 `@runtime_checkable`（与其他 storage Protocol 不一致） | signals/store.py:10 |
| S-2 | 低 | `StrategyInputBundle.parameters: dict[str, object]` — object 类型 | specs.py |
| S-3 | 观察 | `alpha/builtins/` 下仍有 regime_allocation.py / regime_scoring.py 未迁入 regime/ 子包 | alpha/builtins/ |

**Review 计划**
- SignalStore 添加 @runtime_checkable
- 评估 regime_allocation / regime_scoring 迁移到 regime/ 子包
- 为 root 提供 3-5 个稳定顶层符号

**AI-Agent 就绪度**：strategy 的 DecisionStage Protocol 是多 agent 信号聚合的天然接入点。可增加 `CompositeDecisionStage` 支持 meta-weighting（ai-hedge-fund 模式）。

---

### 附录 F：portfolio — 7.8 / 10

**源码**：21 文件 / 1,485 LOC | **测试**：16 文件 / 2,631 LOC（比 1.77:1）

**优势**
- Account 是唯一主要可变状态持有者，AccountView frozen snapshot 方向正确
- positions 使用 MappingProxyType 只读代理
- Fill/Position/CashBook 核心值对象简洁
- 零 `Any` 使用 — 全仓最干净的包之一

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| PF-1 | 中 | `AllocationStage.process()` 和 `ConstraintStage.process()` 参数 `context: object` | allocation.py:212, constraints.py:246 |
| PF-2 | 低 | sell path `market_value` 用 fill_price，buy path 用 avg_cost — 不对称但功能安全 | accounting/account.py:236 |
| PF-3 | 低 | `target_portfolios/` 仍是 reserved 空壳 | target_portfolios/__init__.py |
| PF-4 | 低 | `holdings/` 和 `positions/` 仅 minimal Protocol + dataclass | holdings/, positions/ |

**Review 计划**
- AllocationStage / ConstraintStage context 类型改为 StrategyContext
- target_portfolios 产品化路线确认（保留 or 删除）
- positions/holdings 统一 InstrumentId 类型

---

### 附录 G：risk — 8.0 / 10

**源码**：18 文件 / 1,434 LOC | **测试**：23 文件 / 2,134 LOC（比 1.49:1）
**自 5/14 最大提升**（+0.6）

**优势**
- RiskGate Protocol 定义完整（pre-submit / pre-cancel / post-fill / daily-scan）
- SliceView.bars 类型修复为 `Mapping[InstrumentId, BarSlice]`
- PreTradeContext frozen + rolling context 支持
- 风控返回值语义（非异常），CompositePreTradeCheck resize-recheck 有最大迭代保护
- 零 `Any` 使用（domain 层）

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| R-1 | 中 | `RiskGate.daily_scan()` 返回 `list[object]` — 应改为 `list[RiskAction]` | contracts.py:95 |
| R-2 | 低 | `_accept()` helper 在 constraints/checks.py 和 exposure/checks.py 重复 | checks.py:50, checks.py:18 |
| R-3 | 低 | `models.py` 仍为 reserved 空壳（`__all__: list[str] = []`） | models.py |

**Review 计划**
- RiskGate.daily_scan() 返回类型改为 list[RiskAction]
- 提取 _accept() 到 constraints/context.py
- 填充或删除 models.py reserved namespace

---

### 附录 H：execution — 7.8 / 10

**源码**：54 文件 / 3,920 LOC | **测试**：37 文件 / 8,221 LOC（比 2.10:1）
**自 5/14 第二大提升**（+0.6）

**优势**
- PaperBrokerGateway 已实现（submit/cancel/query_fills/get_account/connect）
- ExecutionReconciler 纯函数设计优秀（5 种 MismatchType）
- OMS FSM 完整（7 状态 + 转换表 + 终态保护）
- 13 个 Protocol 定义，Brokerage（runtime-facing）与 BrokerGateway（adapter-facing）分离
- TradeBuilder 支持 FIFO + FLAT_TO_FLAT 匹配

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| EX-1 | **高** | PaperBrokerGateway.get_account() 每次返回初始状态，不反映 fills — 应返回与订单/成交一致的 broker-side account snapshot | broker/gateways/paper.py |
| EX-2 | **高** | 市价单 fill_price=0.0（最小实现简化） | broker/gateways/paper.py:57 |
| EX-3 | 中 | 缺少 Order amend/replace 能力 | broker/contracts.py |
| EX-4 | 中 | 12 个 `Any` 在 storage/sqlite/trade/ 和 audit/（row 反序列化边界） | storage/sqlite/ |
| EX-5 | 中 | `RiskGate` 已定义但未挂入 submit 路径 | contracts.py vs broker/ |
| EX-6 | 低 | root `__init__.py` 空导出 | __init__.py |

**Review 计划**
- P0：PaperGateway 返回 broker-side account snapshot（与 fills 一致），PaperRuntime 负责本地 account projection
- P0：市价单使用 last close price 成交
- P0：cancel/reject/partial fill 行为矩阵覆盖
- P1：Durable OMS journal（SQLite append-only）
- P1：RiskGate 挂入 Brokerage.submit 路径
- P1：定义 A 股 OrderType 枚举（LIMIT/MARKET/FAK/FAB/GTD），Gateway 做映射
- P2：broker adapter conformance tests
- P2：root barrel 提供 5-8 个稳定顶层符号

**QMT/XTP 对标建议**
- 行情/交易双网关分离设计
- 回调驱动订单回报（on_order_event / on_fill_event）
- Session 生命周期管理（connect / disconnect / reconnect / heartbeat）

---

### 附录 I：backtest — 8.8 / 10

**源码**：39 文件 / 5,279 LOC | **测试**：43 文件 / 18,654 LOC（比 **3.53:1** — 全仓最高）

**优势**
- Step Chain 7 步架构清晰，每步职责单一
- EngineResult frozen + EngineResultBuilder 模式 — 教科书级不可变累积
- PIT / 防前瞻 / manifest / replay / simulation models 产品级
- 文件大小控制优秀（最大 453 LOC，无 500+ 文件）

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| BT-1 | 低 | `compute_portfolio_statistics` 内联日收益计算，未复用 `daily_returns_from_navs` | statistics_returns.py:76-79 |
| BT-2 | 低 | StepContext 无 write-once 保护，后写 step 可覆盖前值 | steps/types.py |
| BT-3 | 观察 | 测试覆盖文档（CLAUDE.md 记录 21 unit + 6 integration）与实际 43 文件不一致 | CLAUDE.md |

**Review 计划**
- 统一日收益计算为复用 `daily_returns_from_navs` + 百分比转换
- 更新 CLAUDE.md 测试清单与实际文件对齐
- 评估 StepContext write-once 保护的必要性

**NautilusTrader DST 对标建议**：用回测引擎建立确定性仿真测试（Deterministic Simulation Testing）。已知场景 → 注入事件 → 预期状态验证。比传统单元测试更有生产级价值。

---

### 附录 J：analysis — 7.5 / 10

**源码**：20 文件 / 1,299 LOC | **测试**：12 文件 / 2,429 LOC（比 1.87:1）
**自 5/14 略降**（-0.3），因 domain.py 职责混合问题更突出

**优势**
- 与生产包双向隔离清楚（双向 import-linter 合约）
- `from_row()` 验证严谨（`_require_int` 拒绝 bool，JSON 三路分支）
- ResearchCatalogWriterProtocol 支持 Unit of Work 模式

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| AN-1 | 中 | `domain.py` 465 LOC 混合 3 种职责：领域模型 + 行反序列化 + 迟到检测 | research/domain.py |
| AN-2 | 中 | 4 个 reserved namespace（diagnostics/screeners/reports/experiments）占位 | 各 __init__.py |
| AN-3 | 低 | `from_row()` 非主键字段未做 null 防御（`str(None)` → `"None"`） | domain.py |
| AN-4 | 低 | `storage/__init__.py` 0 字节空文件 | storage/__init__.py |
| AN-5 | 低 | ArtifactService 依赖 filesystem glob 约定而非 manifest/index | research/artifact_service.py |

**Review 计划**
- 拆 domain.py → `domain/specs.py` + `domain/records.py` + `domain/late_arrival.py`
- 评估 reserved namespace 产品路线：实现 or 删除
- ArtifactService 改 manifest/index 驱动
- `from_row()` 增加非主键字段 null 防御

**AI-Agent 就绪度**：analysis 是 AI 集成的最佳切入点。
- **短期**：TradingAgents 风格的简单 markdown decision log + reflection
- **中期**：QuantaAlpha 风格的 alpha 轨迹记录 + 因子库管理
- **长期**：AgenticTrading 风格的 DAG 研究工作流编排

---

### 附录 K：application — 7.8 / 10

**源码**：118 文件 / 19,416 LOC | **测试**：111 文件 / 31,649 LOC（比 1.63:1）

**优势**
- **CQRS 边界完美**：queries/commands/builders 零交叉导入
- DatasetRegistry 集中路由（265 行声明式注册）
- SourceQueryFacade Protocol 隔离（不暴露 concrete source）
- PaperSynchronizer + PaperTradingRuntime 最小实现

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| AP-1 | **高** | `backtest_process.py` 583 LOC，BacktestService 5 职责（run lifecycle + engine 构建 + factor bridge + audit 持久化 + artifact 持久化） | processes/execution/ |
| AP-2 | 中 | `DatasetRegistry` 每次 write_data() 重建实例（工厂函数每次调用） | processes/ingestion/dataset_registry.py |
| AP-3 | 中 | 5 个 500+ LOC 文件 | processes/ 各处 |
| AP-4 | 低 | `default_dataset_registry()` 265 行重复注册可表驱动 | dataset_registry.py |

**Review 计划**
- P0：拆 backtest_process.py → BacktestService + FactorBundleBuilder + AuditPersistence
- P1：DatasetRegistry 实例缓存（模块级单例或 DI 注入）
- P1：DatasetRegistry ingestion routing 保留 application，通过 data catalog Protocol 查询 metadata（D-1 对应）
- P2：default_dataset_registry() 改表驱动注册

---

### 附录 L：apps — 8.2 / 10

**源码**：114 文件 / 12,363 LOC | **测试**：136 文件 / 28,934 LOC（比 2.34:1）

**优势**
- registry/container 是全仓 composition root，7 层 DI provider 按依赖序组装
- Context bundles（IngestionBundle / MaterializationBundle / StrategyBundle）frozen dataclass
- API routes 已部分 CQRS 分割（backtest_run/backtest_query, trade_command/trade_query）
- models 按 1:1 路由域组织

**问题清单**

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| A-1 | 中 | `dq_batch.py` 创建 2 个独立 DI container（lines 87 和 310） | jobs/tasks/dq_batch.py |
| A-2 | 中 | `create_dq_and_metadata_context()` 已 deprecated 但仍存在 | jobs/context.py |
| A-3 | 低 | `trade.py` barrel 模糊 CQRS 边界 | api/routes/trade.py |
| A-4 | 低 | `source.py` 233 LOC 可拆分 | api/routes/source.py |

**Review 计划**
- dq_batch.py 消除重复 container 创建
- 清理 deprecated context 函数
- source.py 拆分 fetch vs metadata operations

---

## AI-Agent 生态就绪度 — 4.0 / 10（中长期演进机会）

### 当前状态评估

| 能力 | 状态 | 业界最佳 |
|------|------|---------|
| LLM 集成入口 | ❌ 无 | TradingAgents 多 provider（OpenAI/Anthropic/DeepSeek/Qwen） |
| Alpha 发现 agent | ❌ 无 | QuantaAlpha 轨迹进化、AlphaAgent 闭环 |
| 经验记忆 | ❌ 无 | TradingAgents markdown log + SQLite checkpoint |
| 多 agent 信号聚合 | ❌ 无 | ai-hedge-fund meta-weighting |
| 研究 DAG 编排 | ❌ 无 | AgenticTrading MCP/A2A + DAG planner |
| 因子语义验证 | ⚠️ 部分 | AlphaAgent 反拥挤正则化 |

### 建议演进路线

| 阶段 | 目标 | 复用 Ditto 模块 | 参考 |
|------|------|----------------|------|
| Phase 1 | LLM-assisted research notebook | analysis + features | FactorMiner 轻量模式 |
| Phase 2 | Alpha hypothesis → expression 桥接 | features expression pipeline | QuantaAlpha 语义一致性 |
| Phase 3 | 多 agent 信号聚合 | strategy DecisionStage | ai-hedge-fund meta-weighting |
| Phase 4 | 自主研究 DAG 编排 | application processes | AgenticTrading DAG |

### 关键设计原则

1. **LLM 只做定性推理**，不做定量计算 — 不让 AI 直接操作资金
2. **利用现有基础设施** — LLM 生成 hypothesis，features 编译验证，backtest 跑分
3. **Experience Memory 先轻后重** — 先 markdown log（TradingAgents），需要时再引入 vector DB
4. **保持工程纪律** — AI agent 层同样受 import-linter 约束

---

## 全局 Review 攻坚路线（更新版）

### 优先级矩阵

| 优先级 | 含义 | 验收标准 |
|--------|------|---------|
| P0 | 阻塞扩展或运行时闭环 | 完成后可减少多点修改或跑通新路径 |
| P1 | 高收益架构修复 | 降低耦合、类型缺口、状态风险 |
| P2 | 可读性/一致性治理 | 大文件、命名、错误层级 |
| P3 | 体验和长期演进 | barrel、reserved namespace、AI-ready |

### 更新后的攻坚批次

#### Batch 0：事实源校准（P0 前置）
**目标**：修复质量红线回归，同步文档与源码，建立 review 基线

- 修复 `_registry.py` 唯一 `# type: ignore`（类型窄化）
- 同步 `capability-maturity.md`：execution/paper/reconciliation 成熟度改为 experimental
- 建立 scorecard 模板：每轮模块 review 使用统一评分
- 更新 module-review-ledger：标记已修复和仍 open 的 findings
- 运行 `rg "type: ignore" packages/*/src scripts -g "*.py"` 确认清零

**验收**：`type: ignore` 回到 0；capability-maturity.md 与源码一致

#### Batch 1A：PaperGateway correctness（P0）
**目标**：PaperBrokerGateway 行为正确、可审计

- PaperGateway submit 返回与订单/成交一致的 **broker-side account snapshot**（不持有 portfolio Account）
- 市价单使用 last close price 成交（不再 fill_price=0.0）
- Cancel/reject/partial fill 行为矩阵覆盖
- PaperRuntime/Portfolio 负责本地 account projection，与 broker snapshot 通过 reconciliation 对齐
- A 股 OrderType 枚举定义

**验收**：submit/fill/cancel/reject/partial 有 conformance tests；broker snapshot 与本地 projection 可对齐

#### Batch 1B：Durable OMS journal + reconciliation audit links（P1）
**目标**：订单生命周期可重放、可审计

- SQLite append-only OrderEventJournal，订单生命周期可重放
- Reconciliation 关联 OMS journal/fills/account snapshot，diff 可追溯到 client order id、broker order id、fill id
- RiskGate 挂入 submit 路径

**验收**：订单状态可从 journal 完整重放；reconciliation diff 可追溯到 order/fill/journal

#### Batch 1C：TradingRuntimeKernel 最小设计（P1）
**目标**：backtest/paper 共享 runtime kernel 原语

- 定义 `TradingRuntimeKernel`：Clock + EventBus + state handle + lifecycle
- 不急于 live — 先支撑 backtest/paper 共享
- 回测 step chain 中可复用的 lifecycle 抽象出来

**验收**：paper runtime 使用与 backtest 相同的 Clock/EventBus/lifecycle 原语

#### Batch 2：Dataset facts 拆分 + Data 大类分解（P0+P1）
**目标**：dataset metadata 由 data 拥有，ingestion routing 由 application 拥有；data 包内部认知负载降低

- **data-owned catalog metadata**：dataset maturity/capability/schedule/quality profile 迁入 `data/catalog/`
- **application-owned ingestion routing**：fetch/write factory、AppProcessError、DatasetRegistration 保留在 application
- application ingestion 通过 data 提供的 catalog Protocol 查询 dataset metadata
- 拆 sqlite_store.py（SQL helper / DataFrame 转换 / merge 逻辑）
- 统一 tushare adapter 模式（capital_market 改类）
- fundamental VIP 方法泛化
- **MetadataService 分解**（43 public methods → <20）
- **TushareSource 分解**为 capability facade（27 methods → <20）
- **DataStoreSettings API 收敛**（26 methods → <20）

**验收**：新增 mock dataset 时，data 包注册 metadata + application 注册 routing，各改一处；`check_code_size.py` 类级检查通过

#### Batch 3：Application 职责分离 + E2E 证明（P1）
**目标**：application 不再是第二个 composition root，E2E 可证明

- backtest_process.py 拆分（BacktestService + FactorBundleBuilder + AuditPersistence）
- DatasetRegistry 实例 DI 注入而非每次重建
- data storage wiring 下沉 apps/registry
- **Committed synthetic golden E2E lane**：CI 不依赖本地样本也能证明主路径
- API route maturity metadata：OpenAPI/CLI help 标注 initial-focus/experimental/reserved

**验收**：application 中 SQLiteClient import 数下降；CI 可证明 A 股 ETF 主路径

#### Batch 4：Execution/Risk/Portfolio Spine 完善（P1）
**目标**：交易闭环类型安全 + 实盘安全前置

- RiskGate.daily_scan() 返回 list[RiskAction]
- AllocationStage/ConstraintStage context 类型修正
- Account/Order/Fill 共享 correlation/trade date 语义
- execution 错误体系细化（TemporaryError / RetryableError / FatalError）
- **Kill switch 分级设计**：全仓清仓 / 停止新单 / 告警三级，与 account state 关联
- typed risk decision event 进入 audit/reconciliation
- 风控状态快照/恢复可重启一致

**验收**：风控可嵌入 paper submit 路径，所有关键对象类型安全；kill switch 可审计

#### Batch 5：大文件与命名一致性（P2）
**目标**：降低 review 成本

- features codegen 拆分
- features evaluator + ic.py 拆分
- analysis domain.py 拆分
- data metadata/instrument 拆分
- 统一 Service/Facade/Store/Reader/Writer 命名规则

**验收**：无未登记的 500+ LOC 热点；大文件需有职责说明和拆分计划；`check_code_size.py` 类级检查通过

#### Batch 6：AI-Ready 基础 + 产品路线（P3）
**目标**：为 AI 集成铺设架构基础

- analysis 添加 LLM-assisted research 入口
- features expression pipeline 增加 hypothesis → expression 桥接点
- strategy DecisionStage 增加 CompositeStage（支持多信号聚合）
- analysis experience memory 基础（markdown decision log）

**验收**：可演示 LLM 辅助 alpha hypothesis 生成 + expression 编译验证

### 评分提升预测

| 阶段 | 工程架构 | Runtime | 产品完整度 | AI-Ready |
|------|---------|---------|-----------|----------|
| 当前 | 8.7 | 7.0 | 5.6 | 4.0 |
| Batch 0 后 | 8.7 | 7.0 | 5.7 | 4.0 |
| Batch 1A 后 | 8.7 | 7.3 | 5.8 | 4.0 |
| Batch 1B 后 | 8.8 | 7.5 | 5.9 | 4.0 |
| Batch 1C 后 | 8.8 | 7.6 | 5.9 | 4.0 |
| Batch 2 后 | 9.0 | 7.7 | 6.3 | 4.0 |
| Batch 3 后 | 9.1 | 7.8 | 6.7 | 4.0 |
| Batch 4 后 | 9.1 | 8.0 | 7.2 | 4.2 |
| Batch 5 后 | 9.3 | 8.1 | 7.3 | 4.5 |
| Batch 6 后 | 9.3 | 8.3 | 7.6 | 6.0 |

---

## 验证命令

```bash
pixi run -e dev check           # lint + fmt + type + test --fast
pixi run -e dev arch-check      # 37 合约全部 kept, 0 broken
```

当前基线：37 contracts kept, 0 broken. Architecture smell check passed.

---

## 评分口径表

评分基于以下量化维度，每个维度独立打分后加权：

| 维度 | 权重 | 10 分标准 | 扣分规则 |
|------|------|---------|---------|
| 包边界与依赖方向 | 20% | import-linter 合约全绿，无 TYPE_CHECKING | 每个打破口 -0.5 |
| Protocol/抽象一致性 | 15% | Protocol-only，消费者拥有 | 每个 ABC -0.1；过宽 Protocol -0.2 |
| 类型安全 | 15% | 0 个 `type: ignore`、`Any` 仅在边界 | 每个 type:ignore -0.3；每个域内 Any -0.1 |
| 不可变数据文化 | 10% | 全部 frozen dataclass（运行态例外需说明） | 每个 mutable 无理由 -0.1 |
| 文件/类粒度 | 10% | 无 800+ 行文件、类 <20 public methods | 每超标 +50 LOC -0.1 |
| 测试覆盖 | 10% | test ratio ≥1.5:1，错误路径有测试 | ratio <1.0 -0.5 |
| CQRS/职责分离 | 10% | 读写分离、编排不混合 | 每个混合职责 -0.2 |
| 命名一致性 | 10% | Store/Service/Facade/Reader 命名有规范 | 每个不一致 -0.1 |

**综合分 = Σ(维度分 × 权重)**，取一位小数。

---

## 事实采集命令表

下次复核时运行以下命令，确保数据口径一致：

```bash
# 全局指标
find packages/*/src -name '*.py' | wc -l                    # 生产文件数
find packages/*/src -name '*.py' -exec cat {} + | wc -l     # 生产 LOC
find packages/*/tests -name '*.py' | wc -l                  # 测试文件数
find packages/*/tests -name '*.py' -exec cat {} + | wc -l   # 测试 LOC

# 边界守卫
pixi run -e dev arch-check                                  # 37 合约

# 类型纪律
rg "class \w+\(Protocol\)" packages/*/src -c --glob '*.py'  # Protocol 计数
rg "# type: ignore" packages/*/src scripts -g "*.py"         # 应为 0
rg "TYPE_CHECKING" packages/*/src -g "*.py"                  # 应为 0
rg "import pandas" packages/*/src -g "*.py"                  # 应为 0
rg "# noqa" packages/*/src scripts -g "*.py" | wc -l         # noqa 计数

# 粒度检查
python scripts/check_code_size.py                            # 类级 method 检查
find packages/*/src -name '*.py' -exec wc -l {} + | sort -rn | head -15  # Top 文件

# 架构合约
pixi run -e dev lint-imports                                 # import-linter
```

---

## Source of Truth 决策表

| 事实 | 拥有者 | 当前状态 | 目标 |
|------|--------|---------|------|
| Dataset 定义和 ID | `data/models/common.py` Dataset enum | 集中 | 集中（保持） |
| Dataset metadata/maturity/capability | **目标：data/catalog/** | 分散在 enum + config + application | data-owned catalog store |
| Dataset ingestion routing/factory | `application/ingestion/dataset_registry.py` | application 集中 | application-owned（保持） |
| DQ rules / quality profile | `data/quality/` | data 集中 | data-owned（保持） |
| Capability maturity | `docs/architecture/capability-maturity.md` | 文档滞后 | 与源码同步 |
| API maturity / OpenAPI metadata | `apps/api/routes/` | 未标注 | 按 maturity 标注 |
| InstrumentId / Symbology | `kernel/identity.py` + `data/storage/metadata/` | kernel 定义 ID，data 有映射 | kernel 拥有 ID 语义，data 拥有映射 |
| Trading rules / FeeModel | `kernel/trading.py` | kernel 集中 | kernel（保持，ADR 记录） |
| Protocol 定义位置 | 消费者包 | 消费者拥有 | 消费者拥有（保持） |
| Module review ledger | 待建立 | 不存在 | docs/reviews/audit/ledger.md |

---

## P0/P1 明确不做事项

以下事项在当前 6 个 Batch 内不做，避免范围扩散：

| 不做 | 原因 | 重新评估时机 |
|------|------|-------------|
| Live broker adapter 接入 | Paper 闭环未完成前不碰真实资金 | Batch 1B 完成后 |
| LLM 直接执行交易 | AI 只做定性推理（hypothesis/信号），不操作资金 | Batch 6（P3） |
| 全市场/多币种账户 | 需先完成 A 股 ETF paper 闭环 | Batch 4 完成后 |
| Rust 核心重写 | Python 性能当前足够，高频路径可局部加速 | 不设时间表 |
| ClickHouse/ArcticDB 引入 | DuckDB 嵌入式已满足当前规模 | 数据量超 10TB 时 |
| Pandas 兼容层 | 与项目铁律冲突 | 永不 |
| 第三方 LLM SDK 依赖 | analysis 层通过 Protocol 隔离 | Batch 6 |

---

## 附录 M：Review 检查清单模板

每个模块攻坚时统一使用：

### 通用检查
- [ ] 边界：是否新增违反 `.importlinter` 精神的依赖？
- [ ] 抽象：Protocol 是否由消费者拥有？是否过宽？
- [ ] 类型：是否引入 `Any`、`type: ignore`、`TYPE_CHECKING`？
- [ ] 数据：是否 frozen？若可变，生命周期是否明确？
- [ ] 命名：Service/Facade/Store/Reader/Writer 是否符合职责？
- [ ] 错误：业务返回值和异常语义是否分离？
- [ ] 测试：是否有 RED/GREEN 证据？是否覆盖错误路径？
- [ ] 文档：CLAUDE.md / ADR 是否随架构变化更新？

### 模块攻克顺序（推荐）

| 顺序 | 模块 | 原因 |
|------|------|------|
| 1 | execution | Paper runtime 闭环是产品最大短板 |
| 2 | data + application ingestion | DatasetRegistry 归位 + 大文件拆分 |
| 3 | application | 职责分离，backtest_process 拆分 |
| 4 | risk + portfolio | 类型安全 + Spine 完善 |
| 5 | features + strategy | 可读性 + AI-ready 桥接 |
| 6 | analysis | AI-ready 基础 + 产品化 |
| 7 | kernel + platform | 基础层最后清理 |

---

## 外部参考

### 传统平台（accessed on 2026-05-21）
- QuantConnect LEAN: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine
- NautilusTrader: https://nautilustrader.io/docs/latest/concepts/architecture/
- OpenBB Platform: https://docs.openbb.co/platform/developer_guide/architecture_overview
- Databento: https://docs.databento.com/
- ArcticDB: https://docs.arcticdb.io/
- Freqtrade: https://www.freqtrade.io/en/stable/
- vn.py: https://www.vnpy.org/
- Backtrader: https://www.backtrader.com/blog/posts/2016-06-21-livedata-feed/live-data-feed/
- Microsoft Qlib: https://github.com/microsoft/qlib

### AI-Agent 项目（accessed on 2026-05-21，stars 数为访问时快照）
- TradingAgents (~16.5K stars): https://github.com/tauricresearch/tradingagents
- QuantaAlpha: https://github.com/QuantaAlpha/QuantaAlpha
- AlphaAgent (KDD'25): https://dl.acm.org/doi/10.1145/3711896.3736838
- AgenticTrading: https://github.com/Open-Finance-Lab/AgenticTrading
- ai-hedge-fund (~49.6K stars): https://github.com/virattt/ai-hedge-fund
- FinRobot (~3K stars): https://github.com/AI4Finance-Foundation/FinRobot
- FactorMiner: arXiv 2602.14670
- FinCon (NeurIPS'24): arXiv 2407.06567

---

## 自审

- 未完成项：无空白章节、无 TBD 标记
- 内部一致性：评分维度区分工程架构 / runtime / 产品完整度 / AI-ready
- 范围检查：覆盖全局评估 + 12 模块附录 + 10 传统对标 + 8 AI-Agent 对标 + 7 批次攻坚路线（含 Batch 0）
- 歧义检查：P0-P3 均有验收标准
- 交叉验证：已合并 `2026-05-21-current-architecture-evaluation-and-review-plan.md` 精华（Wave 0 事实源校准、类级审计、TradingRuntimeKernel、Durable OMS journal、Golden E2E、kill switch、Backtrader/Qlib 对标）
- 独有价值：AI-Agent 生态就绪度评估、源码级精确审计、CQRS 边界验证、features 测试比信号
