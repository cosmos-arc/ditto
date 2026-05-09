# 综合架构评估报告的严格审视（第一部分：运行时架构审计）

> 日期：2026-05-08
> 审视对象：`docs/reviews/audit/2026-05-07-comprehensive-architecture-evaluation.md`
> 标准：Jane Street / NautilusTrader / LEAN / ArcticDB 级别量化系统
> 方法：运行时架构审计 + 业界一手资料对标 + 源码级验证
> 延续：`2026-05-08-runtime-architecture-critique-part2.md`

---

## 1. 核心结论

被审视报告在 Python 包结构层面的审计是优秀的，但它存在一个根本性盲区：

**它评估的是"Python 项目的包结构质量"，而不是"量化交易系统的运行时架构质量"。**

对标 NautilusTrader / LEAN / ArcticDB / Jane Street 这个级别，报告的 8.6 综合评分偏高。包结构 8.0+，但运行时架构 5.0-6.0。

### 1.1 三层评分

| 评估口径 | 报告自评 | 严格对标 | 差距原因 |
|---------|---------:|---------:|---------|
| Python 研究/回测框架 | 8.6 | **8.0** | E2E skip 扣分 |
| 模块化量化系统架构 | 8.6 | **6.8** | 包结构好，运行时架构缺失严重 |
| "全球全市场量化系统"架构就绪度 | 未评估 | **5.0** | 无实盘路径、无流式数据、无事件驱动、无 crash recovery |

### 1.2 九维度重新打分

| 维度 | 报告自评 | 严格对标 | 差距原因 |
|------|---------:|---------:|---------|
| 依赖边界与架构清晰度 | 9.3 | **7.5** | 36 条合约守的是包边界，不是运行时架构 |
| 模块化与语义所有权 | 8.8 | **7.5** | 包结构正确，但运行时职责不清 |
| Ports/Adapters 与 DI | 8.7 | **7.0** | 119 个 Protocol 好，但核心 Port 零实现 |
| CQRS 与 application 编排 | 8.8 | **7.5** | 编排本质是方法调用链，不是事件驱动 |
| 数据架构、PIT 与目录治理 | 8.0 | **6.5** | PIT 靠 developer discipline，不是系统保证 |
| 量化平台研究-回测-执行一致性 | 7.8 | **5.5** | BrokerGateway 零实现，无实盘路径 |
| 工程质量与验证 | 9.2 | **7.5** | 验证的是包结构正确性，不是交易正确性 |
| 可观测性与运维 | 8.3 | **6.0** | 4 个包 @traced 为 0，Clock 仅用于 timestamp |
| 可理解性与 agent 友好度 | 8.6 | **8.0** | 差距最小，文档和门禁确实好 |
| **严格对标综合** | **8.6** | **6.8** | |

---

## 2. 运行时架构审计（被审视报告未覆盖）

### 2.1 事件驱动架构：空壳

被审视报告在第 5 节引用了 Hexagonal/Ports & Adapters，但没有审计 Ditto 的实际事件驱动程度。

**源码验证结果**：

| 指标 | 数值 |
|------|------|
| 定义的事件类型 | 7（OrderSubmitted/OrderFilled/OrderCanceled/PositionChanged/DataIngested/QualityCheckCompleted/RiskGuardTriggered） |
| 生产代码 publish site | 3（全在 backtest/steps/） |
| 生产代码 subscribe site | **0** |
| 未使用的 stub 事件 | 4（PositionChanged/DataIngested/QualityCheckCompleted/RiskGuardTriggered 的 consumer 侧） |
| EventBus 在 EngineOptions 中 | optional（`event_bus: EventBus | None = None`） |

**结论：EventBus 是 write-only 空壳。** 没有组件对事件做反应式响应。Position 变化不触发 risk check，Data ingestion 完成不触发 quality check，Quality check 失败不通知下游。所有流程都是方法调用链。

**对标 NautilusTrader**：

| 特征 | NautilusTrader | Ditto |
|------|---------------|-------|
| 核心通信机制 | MessageBus（Pub/Sub + Point-to-Point + Request/Response） | 方法调用链 |
| 消息类型 | Data / Events / Commands（三类） | DomainEvent（一类，payload 无类型） |
| 确定性保证 | 单线程消费 + cache-then-publish | 无 |
| 组件生命周期 | 7 稳定态 + 7 过渡态 FSM | 无 |
| 持久化 | 可选 Redis | 无 |

### 2.2 回测-实盘一致性：0%

被审视报告给"量化平台研究-回测-执行一致性"打了 7.8，评价是"回测闭环较完整"。

**源码验证结果**：

| 接口 | 回测实现 | 实盘实现 |
|------|---------|---------|
| Brokerage Protocol | ✅ BacktestBrokerage | ❌ 无 |
| BrokerGateway Protocol | ❌ 不使用 | ❌ **零实现**（gateways/ 是占位符） |
| DataFeed Protocol | ✅ ProviderBackedDataFeed（全量内存加载） | ❌ 无流式实现 |
| Clock Protocol | ✅ SimulatedClock | ✅ RealtimeClock（唯一有的） |
| EventBus Protocol | ✅ SimpleEventBus | ✅ SimpleEventBus（共享） |
| Risk Check | ✅ CompositePreTradeCheck | ✅ 共享 |
| Execution Loop | ✅ EngineLoop 7 步链 | ❌ 无 live loop |

**实盘路径存在度：0%。** BrokerGateway 零实现，DataFeed 是回测专用全量加载，step chain 是回测专用顺序链。Protocol 层面的 seam 存在，但运行时路径完全不存在。

**对标**：

| 系统 | parity 机制 | Ditto |
|------|-----------|-------|
| NautilusTrader | BacktestNode/LiveNode 共享 NautilusKernel | 无共享运行时 |
| LEAN | 回测 = "快速前进的实盘"，策略代码零修改 | 回测是专用 7 步链 |

7.8 → **应评 5.5**。

### 2.3 状态管理：全部 in-memory

**源码验证结果**：

| 状态类型 | 持久化 | 恢复机制 |
|---------|--------|---------|
| Backtest Account（持仓/现金/冻结） | ❌ in-memory | ❌ 无 |
| EngineLoop fills/orders/signal queue | ❌ in-memory (list/deque) | ❌ 无 |
| Order state | ❌ in-memory (OrderBook) | ❌ 无 |
| Ingestion cursor | ✅ SQLite IngestionCursorService | ✅ 有 |
| Strategy run state | ✅ SQLite StrategyRunStore | ⚠️ 需 application 显式调用 |
| Risk state (peak NAV) | ❌ in-memory | ❌ 无 |

**结论：如果进程在回测中途或实盘交易中死亡，所有交易状态丢失。** SQLite trade records 可用于事后 reconciliation，但无 `restore()` 或 `rebuild_account_from_history()` 方法。

**对标 NautilusTrader**：crash-only 设计——不可恢复故障时立即终止，状态外部持久化，启动和崩溃恢复共享同一路径。

### 2.4 时间模型：原始

**源码验证结果**：

| 能力 | 实现 |
|------|------|
| Clock Protocol | `now()`/`today()`/`advance_to()`——仅用于 event timestamp |
| PIT in data | `knowledge_date` 约定 + `shift(1)` codegen + `_find_pit()` rules |
| PIT in features | `DerivedState` watermark + publication safety |
| Valid-time / Transaction-time / Observation-time | ❌ 无 |
| 统一时间上下文对象 | ❌ 无 |
| 纳秒精度 | ❌ 无（datetime 精度） |

**对标 ArcticDB**：版本化不可变数据结构 + `read(symbol, as_of=timestamp)` 时间旅行查询 + 原子符号链接切换。Ditto 的 PIT 是开发者纪律，不是系统保证。

### 2.5 数据管道：纯批处理

**源码验证结果**：

| 特征 | 实现 |
|------|------|
| 数据获取方式 | HTTP pull（Tushare）/ 文件读取（TDX）/ HTTP pull（FRED） |
| 数据加载策略 | 全量加载到内存（`ProviderBackedDataFeed._load_bars()`） |
| 流式数据 | ❌ 无 WebSocket / Kafka / message broker |
| 增量更新 | ❌ 无 |
| 实时推送 | ❌ 无 |

`features/` 中的 `streaming` 参数指的是 Polars streaming engine（内存映射 I/O），不是实时数据流。

**对标 Databento**：FPGA SmartNIC + Rust 网关，从 venue handoff 到应用中位延迟 6.1 微秒。Ditto 的 HTTP pull 模式无法支撑任何实时场景。

### 2.6 风控：装饰而非架构

**源码验证结果**：

| 能力 | 实现 |
|------|------|
| Pre-trade check | ✅ CompositePreTradeCheck（6 规则） |
| Post-trade scan | ✅ CompositePostTradeGuard（daily scan） |
| Continuous monitoring | ❌ 无 |
| Intraday P&L tracking | ❌ 无 |
| Position limit breach（intraday） | ❌ 无 |
| Risk state persistence | ❌ 无（MaxDrawdownRule._peak_nav in-memory） |
| Risk action execution | ⚠️ lock_instrument() 仅阻止 planner 生成订单，不强制平仓 |

**对标 NautilusTrader**：RiskEngine 位于 submit/modify 路径上，是 execution pipeline 的必经环节。Ditto 的 risk 是 pre/post 装饰，不是架构嵌入。

### 2.7 Feature Store：不存在

**对标 Chronon (Airbnb) / Feast**：

| 能力 | Chronon | Ditto |
|------|---------|-------|
| 定义一次，online/offline 自动生成 | ✅ | ❌ 只有 batch materialization |
| Point-in-Time Join | ✅ 自动 as-of join | ❌ 特征是预计算 DataFrame |
| Online serving | ✅ sub-10ms p99 | ❌ 不存在 |
| 特征 decay/staleness 监控 | ✅ watermark | ❌ 无 |

对日频 ETF 回测不是致命缺陷，但"全球全市场量化系统"目标意味着未来必须有 online feature serving。

---

## 3. 被审视报告的五个盲区

### 盲区 1：没有区分"包结构架构"和"运行时架构"

报告核心方法论：import-linter 合约 + AST 扫描 + 包间依赖分析。这衡量的是编译时架构（Python 包结构），不是运行时架构（系统实际如何运行）。

报告用 9.3 分说"依赖边界与架构清晰度"优秀。36 条 import-linter 合约确实优秀——对包结构来说。但"架构清晰度"应该包含运行时通信模式、事件流、状态管理、时间模型——这些报告没有审计。

### 盲区 2："回测-实盘一致性"评分过于宽松

7.8 分的评价是"回测闭环较完整，live broker gateway/OMS/reconciliation 仍是骨架或待完善"。

"骨架或待完善"暗示存在但未完善。实际是**零实现、零路径**。BrokerGateway 没有任何 adapter，DataFeed 没有流式实现，execution loop 是回测专用。

### 盲区 3：事件驱动架构缺失未被识别为架构缺陷

报告引用了 Hexagonal Architecture 和 Ports & Adapters，但完全没有审计 Ditto 的实际事件驱动程度。一个 EventBus write-only、零 subscribe、零 reactive flow 的系统，在被审视报告里没有被标记为问题。

### 盲区 4：时间模型原始性未被识别为架构缺陷

PIT 安全被放在"数据架构、PIT 与目录治理"维度下作为子项评估（8.0 分）。但 PIT 的实现方式——分散在 codegen shift(1)、data knowledge_date、execution _find_pit()——意味着安全靠开发者纪律而非系统保证。对标 ArcticDB 的架构级版本化，这不是 8.0 的水平。

### 盲区 5：Feature Store 缺失被低估

Features 包审计提到了 DerivedVersion 状态机和 publication safety，但没有对标真正的 feature store（Chronon/Feast）。对于报告声称的"全球全市场"目标，这是不可忽略的能力缺口。

---

## 4. 被审视报告做好的部分

公平地说，这份报告在以下方面做得好：

1. **双口径评分**（8.6 + 7.4）比单一评分更诚实。方法论对了，具体分数偏高。
2. **DDD/YAGNI 平衡**（8.8 节）正确限定了 DDD 借鉴的边界。
3. **Dataset enum** 正确识别为 #1 架构债务。
4. **过度设计防护**（"先做最小可行 contract 再补 runtime"）原则正确。
5. **业界对标广度**（10 节）比大多数架构报告更全面。
6. **Reference domain** 建议方向正确（虽然应渐进落地）。
7. **深度报告证据整合**（2.1 节）按判断力筛选有效证据的做法专业。

---

> 第一部分结束。第二部分（`2026-05-08-runtime-architecture-critique-part2.md`）覆盖：业界对标详解、第 8 节专项复核、面 10/10 真实差距清单、最终结论。
