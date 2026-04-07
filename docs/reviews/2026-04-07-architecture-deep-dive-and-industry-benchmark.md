# Ditto 系统架构深度审计：业界最佳对标与架构演进建议

> 日期：2026-04-07
> 对标平台：QuantConnect LEAN、NautilusTrader、Zipline、Backtrader、Vectorbt、Databento、
>          Microsoft Qlib、Freqtrade、Hummingbot、Jesse、OpenBB
> 关联文档：[评分卡概览](2026-04-07-industry-benchmark-gap-analysis.md)
> 目标：从架构模式、扩展性、面向未来能力三个维度，深度分析 Ditto 与业界最佳的差距

---

## 目录

1. [业界量化平台架构模式全景](#1-业界量化平台架构模式全景)
2. [架构模式深度对标](#2-架构模式深度对标)
3. [回测/实盘一致性分析](#3-回测实盘一致性分析)
4. [多策略架构对比](#4-多策略架构对比)
5. [数据架构深度对比](#5-数据架构深度对比)
6. [执行层与风控层对比](#6-执行层与风控层对比)
7. [组合优化与归因分析](#7-组合优化与归因分析)
8. [引擎层代码级架构问题](#8-引擎层代码级架构问题)
9. [Ditto 独特优势与护城河](#9-ditto-独特优势与护城河)
10. [架构能力成熟度矩阵](#10-架构能力成熟度矩阵)
11. [架构演进路线建议](#11-架构演进路线建议)

---

## 1. 业界量化平台架构模式全景

### 1.1 10+ 平台架构模式分类

| 平台 | 架构模式 | 语言 | 核心特征 | 适用场景 |
|------|---------|------|---------|---------|
| **QuantConnect LEAN** | 五层框架解耦 | C# | Universe→Alpha→Portfolio→Risk→Execution 独立可替换 | 多资产多策略回测+实盘 |
| **NautilusTrader** | 六边形 Ports/Adapters | Rust+Python | Actor 模型，回测/实盘零分支共享核心 | 高频/低延迟实盘 |
| **Zipline** | Pipeline API | Python | Bundle 数据包 + 因子表达式驱动 | 研究型因子回测 |
| **Backtrader** | Cerebro 中心调度 | Python | Lines/Feeds/Strategies/Brokers 四角色 | 个人量化研究 |
| **Vectorbt** | 向量化计算 | Python | 底层 NumPy/polars，极致性能 | 大规模参数扫描 |
| **Databento** | 统一数据 API | Rust+Python | 历史和实时同一 API，dbn 格式 | 专业市场数据基础设施 |
| **Microsoft Qlib** | 模型驱动的 Alpha 框架 | Python | 因子挖掘 + 机器学习 + 量化研究 | AI 驱动的 Alpha 研究 |
| **Freqtrade** | 策略接口驱动 | Python | ISignalProvider + 事件执行 | 加密货币自动化交易 |
| **Hummingbot** | 做市策略框架 | Python/Cython | 市场做市 + 套利 | 加密货币做市 |
| **Jesse** | 简化策略框架 | Python | 信号函数 + 风控钩子 | 加密货币简单策略 |
| **OpenBB** | 金融数据平台 | Python | 统一数据接口 + 分析工具 | 金融数据获取与分析 |

### 1.2 三大架构范式

业界量化系统可以归纳为三种核心架构范式：

#### 范式 A：统一核心（Backtest-Live Parity）

**代表**：NautilusTrader、QuantConnect LEAN

```
核心交易循环（不知道自己在回测还是实盘）
  ├─ DataEngine    ← DataAdapter (Backtest | Live)
  ├─ Strategy      ← 纯逻辑，无 I/O
  ├─ ExecEngine    ← ExecClient (Simulated | LiveBroker)
  └─ RiskEngine    ← 持续运行的独立风控

切换回测/实盘 = 替换 Adapter，核心零改动
```

**关键原则**：
- 回测和实盘共享**完全相同**的订单路由、风控检查、策略逻辑
- 适配器模式隔离外部依赖（数据源、券商连接）
- 时钟抽象全链路注入（SimulatedClock vs RealtimeClock）
- 核心**永远单线程确定性**，I/O 在外围异步处理

#### 范式 B：表达式/声明式驱动

**代表**：Zipline、Microsoft Qlib、Ditto（部分）

```
因子表达式 → 编译器 → 计算图 → 向量化执行
策略定义 → 声明式 Spec → Pipeline 编排
```

**关键原则**：
- 因子/策略以**表达式或配置**定义，非命令式代码
- 编译期验证（类型检查、依赖分析、PIT 安全）
- 向量化批量执行，利用列式存储/计算优势
- 可审计、可版本化、可复现

#### 范式 C：事件驱动实时系统

**代表**：NautilusTrader（Rust 核心）、Hummingbot

```
Event Bus
  ├─ on_bar()    → tick 级行情处理
  ├─ on_quote()  → 逐笔报价
  ├─ on_trade()  → 成交回报
  └─ on_timer()  → 定时任务

Actor 模型确保：消息有序、状态隔离、无锁并发
```

**关键原则**：
- 事件驱动而非轮询
- Actor 隔离保证策略间安全
- 毫秒级响应（高频场景必需）
- 背压和流量控制

### 1.3 Ditto 的架构定位

Ditto 当前处于**范式 B（声明式驱动）** 的成熟阶段，同时具备**范式 A** 的分层架构骨架但未实现统一核心。这一定位在研究型量化平台中是合理的，但如果目标是走向实盘交易，需要补齐范式 A 的适配器层。


---

## 2. 架构模式深度对标

### 2.1 分层架构对比

| 层级 | LEAN | NautilusTrader | Ditto | 评价 |
|------|------|---------------|-------|------|
| 数据层 | `IDataFeed` + `Subscription` | `DataEngine` (Actor) | `ditto_data` (CQRS Reader/Writer) | Ditto 的 CQRS 存储最精细 |
| 因子层 | 无内建因子系统 | 无内建因子系统 | `ditto_analytics` (编译器+评估) | **Ditto 独有优势** |
| 策略层 | `IAlgorithm` (Universe+Alpha) | `Strategy` (Actor) | `StrategyPipeline` (8 Stage) | 三者模式不同，各有优势 |
| 组合层 | `IPortfolioConstruction` | Portfolio Manager | `AllocationStage` + `ConstraintStage` | Ditto 偏基础 |
| 风控层 | `IRiskManagement` (全局) | `RiskEngine` (独立 Actor) | PreTrade + PostTrade (步骤内) | Ditto 缺独立风控服务 |
| 执行层 | `IBrokerage` (40+ 券商) | `ExecClient` (统一接口) | `BacktestBrokerage` (唯一实现) | Ditto 缺实盘路径 |
| 基础设施 | 自建 | 自建 (Rust) | `ditto_infra` + `ditto_kernel` | Ditto 的 kernel 零依赖设计最干净 |

### 2.2 Ditto 分层架构的优势

Ditto 在架构清晰度方面有几个超越业界平均水平的亮点：

1. **importlinter 强制依赖方向**：大多数开源项目（包括 LEAN）仅靠代码审查保证依赖规则，Ditto 将其机器化
2. **CQRS 四象限互斥规则**（R8）：query/process/command/builders 的严格互斥在业界量化框架中没有先例
3. **Kernel 零依赖设计**：`ditto_kernel` 无任何外部依赖，仅包含值对象和 Protocol——比 LEAN 的 `QuantConnect.Common` 更纯粹
4. **Analytics 层纯计算隔离**：`ditto_analytics` 不依赖 `ditto_data`（仅 `data.errors`），实现了真正的纯计算层

### 2.3 Ditto 分层架构的局限

| 局限 | 说明 | 业界做法 |
|------|------|---------|
| Engine-Analytics 平行隔离 | 两者不能互相调用，限制了因子驱动的策略开发 | Qlib 将因子和策略统一在模型层 |
| App 层编排复杂度 | 48 个文件，process/ 下 22 个编排器 | LEAN 用 `AlgorithmManager` 统一编排 |
| Data 层过度细分 | 314 个文件，20+ Reader/Writer 对 | LEAN 用 `DataManager` + `Security` 统一 |
| Kernel 太薄 | 仅值对象和 Protocol，缺少共享计算 | NautilusTrader 的 core 包含共享算法 |

### 2.4 依赖注入对比

| 系统 | DI 方案 | 优劣 |
|------|--------|------|
| LEAN | 构造函数注入 + `IAlgorithm.Initialize()` 手动组装 | 简单直接，但大型系统难管理 |
| NautilusTrader | `Trader` 构造时传入所有 adapter | 集中式，配置驱动 |
| Ditto | Dishka 容器 + `registry/` Composition Root | 最工程化，但 learning curve 高 |
| Freqtrade | 简单工厂模式 | 最简单，适合小系统 |

Ditto 的 DI 方案在工程化程度上领先，但 `registry/` 的 Composition Root 逻辑复杂，新开发者上手成本较高。


---

## 3. 回测/实盘一致性分析

### 3.1 业界最佳实践：统一核心原则

**NautilusTrader** 是业界回测/实盘一致性的标杆，其核心设计：

```python
# NautilusTrader 核心循环（伪代码，回测和实盘完全相同）
class TradingNode:
    def __init__(self, config: TradingNodeConfig):
        self.data_engine = DataEngine(config)      # 不知道数据来源
        self.exec_engine = ExecEngine(config)      # 不知道执行目标
        self.risk_engine = RiskEngine(config)      # 持续运行
        self.cache = InstrumentCache()

    async def run(self):
        while self.running:
            # 数据进来 → 策略处理 → 执行检查 → 风控扫描 → 发送订单
            # 时钟由 DataEngine 驱动（回测=模拟，实盘=真实）
            pass

# 切换回测/实盘只需替换 adapter
backtest_node = TradingNode(
    data_clients=[BacktestDataClient(data_catalog)],
    exec_clients=[SimulatedExecClient()],
)
live_node = TradingNode(
    data_clients=[LiveDataClient("binance")],
    exec_clients=[LiveExecClient("binance")],
)
```

**关键设计**：
- 核心循环**零条件分支**（没有 `if backtest else live`）
- `Clock` 由 `DataEngine` 驱动——回测时数据推进时钟，实盘时系统时钟推进
- 订单状态机**完全相同**——回测用 `SimulatedExecClient` 模拟成交，实盘用 `LiveExecClient` 连接券商
- 风控检查**完全相同**——因为风控在核心循环内

### 3.2 LEAN 的回测/实盘统一

```csharp
// LEAN 核心接口（回测和实盘共享）
public interface IAlgorithm {
    void OnData(Slice data);           // 策略逻辑
    void SetHoldings(string symbol, double target);  // 下单
    IEnumerable<OrderTicket> Orders { get; }         // 订单管理
}

// 切换方式：替换 IDataFeed 和 IBrokerage
var engine = new AlgorithmTradingEngine(
    dataFeed: new BacktestingFeed(dataFolder),  // or LiveFeed
    brokerage: new BacktestingBrokerage(),       // or InteractiveBrokersBrokerage
    transactions: new BacktestingTransactionHandler()  // or LiveTransactionHandler
);
```

### 3.3 Ditto 当前状态分析

```python
# Ditto EngineLoop（简化）
class EngineLoop:
    def run(self, config: EngineConfig, data_feed, brokerage):
        for date in calendar:                          # 日历驱动（硬编码日频）
            bars = data_feed.get_slice(date)           # 紧耦合 data 包
            account = brokerage.get_account()
            report = self._post_trade_scan(...)        # PostTrade 检查
            if self._should_rebalance(date):
                target = self._run_pipeline(...)       # 策略计算
                plan = self._plan_execution(target)    # 执行规划
                validated = self._pre_trade_check(plan) # PreTrade 检查
                brokerage.submit(validated)            # 下单
                fills = brokerage.process_pending()    # 撮合
            account = brokerage.get_account()
            self._collect_audit(account, fills)        # 审计收集
```

### 3.4 差距逐项分析

| 维度 | NautilusTrader | LEAN | Ditto | 差距等级 |
|------|---------------|------|-------|---------|
| 主循环抽象 | Protocol/Actor | IAlgorithm | 内联在 EngineLoop | **大** |
| 时钟驱动 | DataEngine 推进 | DataFeed 推进 | 日历 for 循环 | **大** |
| 数据注入 | DataAdapter Protocol | IDataFeed | ProviderBackedDataFeed 硬绑定 | **大** |
| 执行抽象 | ExecClient Protocol | IBrokerage | BacktestBrokerage 唯一实现 | **大** |
| 风控位置 | 独立 RiskEngine | IRiskManagement | 步骤内函数调用 | **中** |
| 订单生命周期 | 完整状态机 | OrderTicket | 创建→直接成交 | **大** |
| 实时支持 | 原生 async | async Task | 同步日频 | **大** |

### 3.5 改造建议：抽取 TradingLoop Protocol

```python
# 建议的架构改造方向
class TradingLoop(Protocol):
    """统一回测/实盘的主循环接口"""

    def step(self, clock: Clock) -> None:
        """单个时间步（由时钟驱动）"""
        ...

    def on_data(self, data: MarketData) -> None:
        """数据到达回调（事件驱动）"""
        ...

    def on_fill(self, fill: Fill) -> None:
        """成交回报回调"""
        ...

    def on_risk_alert(self, alert: RiskAlert) -> None:
        """风控预警回调"""
        ...

# 回测实现
class BacktestTradingLoop:
    """日历驱动、同步、全量快照"""

# 实盘实现
class LiveTradingLoop:
    """事件驱动、异步、增量更新"""
```

核心原则：**让 EngineLoop 的业务逻辑（策略、风控、执行）与调度模式（同步/异步、日历/事件）解耦**。


---

## 4. 多策略架构对比

### 4.1 业界多策略模式

#### LEAN: Alpha Stream 模型

```
Alpha Manager
  ├─ Alpha 1 (Momentum)    → 独立 Insight 生成
  ├─ Alpha 2 (Mean Reversion) → 独立 Insight 生成
  └─ Alpha 3 (Volatility)  → 独立 Insight 生成
       ↓
  Insight Aggregator        → 合并 + 冲突解决
       ↓
  Portfolio Construction    → 统一组合优化
       ↓
  Risk Management           → 全局风控
       ↓
  Execution                 → 统一执行
```

**关键设计**：
- 每个 Alpha 独立生成 `Insight`（方向+持续时间+幅度+置信度）
- `PortfolioConstructionModel` 聚合所有 Insight 做统一优化
- 风控在组合层面统一执行
- Alpha 间通过 `Insight` 解耦，无需知道彼此存在

#### NautilusTrader: Strategy Actor 模型

```python
class Strategy(Actor):
    """每个策略是独立的 Actor"""
    id: StrategyId
    on_start() → on_bar() → on_fill() → on_stop()

    # 策略间通过 TradingNode 协调，不直接通信
```

- 每个 `Strategy` 是独立的 Actor，有自己的状态和生命周期
- `Portfolio` 全局管理所有策略的持仓和资金
- `ExecEngine` 统一路由所有策略的订单
- 策略间完全隔离，不能互相影响

#### Two Sigma / 量化机构（公开信息）

```
Signal Layer (多个 Alpha Stream)
  ├─ Alpha A: 短期反转
  ├─ Alpha B: 动量
  └─ Alpha C: 基本面
       ↓
  Signal Fusion (信号融合)
  ├─ 风险模型: Barra / 因子风险
  ├─ 配置: 目标波动率 / 行业约束 / 因子暴露限制
  └─ 优化: 均值-方差 / Black-Litterman
       ↓
  Execution Layer
  ├─ 算法执行: VWAP / TWAP
  ├─ 交易成本模型: 预估 + 实际
  └─ 执行质量分析
```

### 4.2 Ditto 现状

```
EngineLoop (单实例)
  └─ StrategyPipeline (单实例)
       └─ StrategySpec (值对象，无状态)
            └─ DecisionStage[0..N] (无状态函数)
                 └─ Account (单实例，单策略)
```

**限制**：
- 每个 `EngineLoop` 运行只支持一个策略
- `StrategySpec` 是 frozen dataclass（值对象），没有生命周期管理
- `StrategyPipeline.process()` 是无状态纯函数
- `Account` 不区分策略归属

### 4.3 改造建议：引入 StrategyInstance

```python
# 建议：StrategySpec（规格）→ StrategyInstance（运行实例）
@dataclass(frozen=True)
class StrategySpec:
    """策略规格（当前已存在，保持不变）"""
    id: str
    scorer: str
    selector: str
    params: dict[str, object]
    ...

class StrategyInstance:
    """策略运行实例（新增）"""
    spec: StrategySpec
    state: StrategyState      # RUNNING / PAUSED / STOPPED
    context: StrategyContext   # 策略级状态（持仓、风控、冷却期）
    version: int              # 版本号
    created_at: datetime
    updated_at: datetime

    def on_bar(self, data: MarketData) -> SignalSnapshot: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...

class StrategyRegistry:
    """策略注册中心（新增）"""
    def register(self, spec: StrategySpec) -> StrategyId: ...
    def get(self, id: StrategyId) -> StrategyInstance: ...
    def list_active(self) -> list[StrategyInstance]: ...
    def allocate_budget(self, allocations: dict[StrategyId, float]) -> None: ...
```

**优先级建议**：V1 阶段只设计 Protocol 接口，不实现。接口设计保证未来可以渐进式引入多策略能力。


---

## 5. 数据架构深度对比

### 5.1 统一数据 API 对比

#### Databento 模式（业界标杆）

```python
# Databento: 历史和实时同一 API
import databento as db

# 历史数据
client = db.Historical("YOUR_API_KEY")
data = client.timeseries.get_range("GLBX.MES", start="2024-01-01", end="2024-12-31")

# 实时数据（API 完全相同，仅改 timeseries 为 live）
client = db.Live("YOUR_API_KEY")
data = client.timeseries.subscribe("GLBX.MES")

# 消费方式完全相同
for record in data:
    process(record)
```

**关键原则**：客户端代码零改动切换历史/实时。数据格式统一为 `dbn`（二进制），解析逻辑完全复用。

#### LEAN 的 DataFeed 模式

```csharp
// LEAN: IDataFeed 统一接口
public interface IDataFeed {
    IEnumerator<Subscription> GetSubscriptions();
    void Consume();  // 阻塞直到有新数据
}

// 回测: ConcatEnumerator 将历史数据无缝推入
// 实时: WebSocketEnumerator 将实时行情推入
// 过渡: 先推完历史，再无缝切换到实时（warm-up）
```

#### Ditto 数据层现状

```python
# 当前: 两条完全不同的路径
# 路径 A: 批量历史数据（storage.Reader）
market_reader = MarketReader(data_root)
df = market_reader.read(instrument_id=1, start_date="2024-01-01")

# 路径 B: 外部数据源拉取（sources.*）
tushare = TushareSource(token=...)
df = tushare.fetch_daily(trade_date="20240101")

# 没有统一接口，没有流式 API
```

### 5.2 数据存储架构对比

| 维度 | LEAN | NautilusTrader | Databento | Ditto |
|------|------|---------------|-----------|-------|
| 存储格式 | 自定义 zip+json | 自定义 Parquet 扩展 | dbn (列式二进制) | Parquet + SQLite |
| 数据分片 | 按日期/按 Symbol | 按日期+Instrument | 按日期+Venue+Symbol | 按数据域+日期 |
| 压缩 | LZ4 | LZ4 + Snappy | zstd | Parquet 内建压缩 |
| 查询方式 | `Subscription` 流式 | `DataClient.request()` | `get_range()` | Reader.read() 批量 |
| 实时写入 | 无（离线系统） | 增量追加 | 流式追加 | Writer.write() 批量 |
| 数据版本 | 无 | Schema 版本 | 含 nanosecond 精度时间戳 | CompileIdentity 哈希 |

### 5.3 PIT（Point-in-Time）保证对比

| 系统 | PIT 机制 | 评价 |
|------|---------|------|
| LEAN | `DataNormalizationMode` 配置 | 简单但粗粒度 |
| Zipline | Bundle 快照 + 调整类型 | 成熟但需要预构建 |
| Databento | 原始数据不调整，客户端按需调整 | 最灵活 |
| Ditto | 表达式编译器 `shift(1)` + 冻结管理 + LateArrivalPolicy | **最精细** |

Ditto 的 PIT 实现是几个系统中**最细致的**——在表达式编译层面就保证了 `shift(1)` 防前视偏差，配合数据冻结管理和延迟到达策略，形成了三层 PIT 保护。

### 5.4 数据质量引擎对比

| 系统 | 质量检查 | 评价 |
|------|---------|------|
| LEAN | 基础（非空、格式） | 简单 |
| NautilusTrader | Schema 验证 + 业务规则 | 中等 |
| 专业数据商 (Wind/Bloomberg) | 多级检查 + 人工复核 | 最全面 |
| **Ditto** | **L1 技术检查 + L2 业务检查 + L3 统计检查 + L4 跨源交叉验证** | **开源领域最全面** |

### 5.5 数据架构差距总结

| 能力 | 业界标准 | Ditto 现状 | 建议 |
|------|---------|-----------|------|
| 统一历史/实时 API | Databento/LEAN: 同一接口 | `storage.Reader` vs `sources.*` 不同 API | 定义 `MarketDataStream` Protocol |
| 实时数据流 | WebSocket/Streaming | 仅批量拉取 | V2 引入流式数据源 |
| 数据血统 | 版本号 + 依赖图 + 生成链 | `CompileIdentity` 有哈希但无全局血统 | V2 引入血缘追踪 |
| 跨域查询 | `Slice` 统一切片 | 多个独立 Reader | 强化 `DataProvider` Protocol |
| 数据缓存 | 热数据内存缓存 | `DataCache` 存在但使用有限 | V1 优化热点数据缓存 |


---

## 6. 执行层与风控层对比

### 6.1 执行层深度对比

#### LEAN 执行架构（最完整的开源实现）

```
订单提交路径:
  SetHoldings() → PortfolioTarget → OrderRequest
    → OrderProcessor (路由+前置检查)
    → IBrokerage.PlaceOrder() (券商适配)
    → Fill (成交回报)

订单管理:
  OrderTicket: 全生命周期跟踪
    ├─ Submit()     → UNSUBMITTED → SUBMITTED
    ├─ Cancel()     → SUBMITTED → CANCEL_PENDING → CANCELED
    ├─ Update()     → SUBMITTED → UPDATE_PENDING → SUBMITTED (改单)
    └─ State:       UNSUBMITTED → SUBMITTED → PARTIALLY_FILLED → FILLED

订单类型:
  MARKET, LIMIT, STOP, STOP_LIMIT, STOP_MARKET, LIMIT_IF_TOUCHED,
  MARKET_ON_OPEN, MARKET_ON_CLOSE, COMBO_MARKET, COMBO_LIMIT

订单有效期:
  DAY (当日有效), GTC (撤单前有效), GTD (到期前有效),
  IOC (立即成交或取消), FOK (全部成交或取消)
```

#### NautilusTrader 执行架构（高性能设计）

```
ExecEngine (Actor, 持续运行)
  ├─ submit_order(order)   → 前置风控检查 → 路由到 ExecClient
  ├─ modify_order(order)   → 改单（价格/数量）
  ├─ cancel_order(order)   → 撤单
  ├─ cancel_all_orders()   → 紧急全撤
  ├─ on_order_event(event) → 状态更新回调
  └─ OrderCache            → 全局订单簿（O(1) 查询）

状态机:
  INITIALIZED → DENIED | ACCEPTED → PENDING_CANCEL → CANCELED
                                    → PENDING_UPDATE → ACCEPTED
                                    → PARTIALLY_FILLED → FILLED
                                    → REJECTED
```

#### Ditto 执行层现状

```
订单提交路径:
  RebalancePlan → SimpleExecutionPlanner.plan()
    → 生成 BuyOrders / SellOrders / BlockedOrders
    → PreTrade 风控检查（resize-recheck 循环，最多 3 轮）
    → Brokerage.submit_orders()
    → Brokerage.process_pending()  → Fill 列表

订单类型:  仅 MARKET
订单有效期: 无
订单管理:  Order 创建后直接成交，无挂单/撤单/改单
部分成交:  PARTIALLY_FILLED 状态存在但回测中总是全额成交
```

### 6.2 执行层差距矩阵

| 能力 | LEAN | NautilusTrader | Ditto | 差距 |
|------|------|---------------|-------|------|
| MARKET 单 | ✅ | ✅ | ✅ | - |
| LIMIT 单 | ✅ | ✅ | ❌ | **大** |
| STOP / STOP_LIMIT | ✅ | ✅ | ❌ | **大** |
| MOO / MOC | ✅ | ✅ | ❌ | **中** |
| 订单有效期 (GTC/DAY/IOC) | ✅ | ✅ | ❌ | **大** |
| 挂单管理 | ✅ OrderTicket | ✅ OrderId | ❌ | **大** |
| 撤单 | ✅ | ✅ | Protocol 定义未实现 | **大** |
| 改单 | ✅ | ✅ | ❌ | **中** |
| 部分成交 | ✅ | ✅ | 状态存在未使用 | **中** |
| 算法执行 (TWAP/VWAP) | ✅ | ✅ | ❌ | **中** |
| 实现 shortfall 归因 | ✅ | ✅ | ❌ | **中** |
| A 股 100+1 规则 | ❌ (通用) | ❌ (通用) | ✅ **精细实现** | **Ditto 领先** |
| A 股 T+1 冻结 | ❌ (通用) | ❌ (通用) | ✅ **完整实现** | **Ditto 领先** |
| A 股涨跌停检查 | 部分 | 部分 | ✅ **完整实现** | **Ditto 领先** |
| Reality Model 可插拔 | 部分 | ✅ | ✅ **四件套** | **Ditto 领先** |

### 6.3 风控层深度对比

#### LEAN 风控架构

```
IRiskManagement (全局持续运行)
  ├─ MaximumUnrealizedProfitLoss: 最大未实现损益
  ├─ MaximumDrawdownPercent: 最大回撤
  ├─ MaximumSectorExposure: 行业暴露限制
  ├─ MaximumPositionSize: 单标的仓位限制
  └─ NullRiskManagement: 无风控（回测可选）
```

#### NautilusTrader 风控架构

```
RiskEngine (独立 Actor, 持续运行)
  ├─ 前置风控 (下单前):
  │   ├─ max_order_size (单笔最大)
  │   ├─ max_order_rate (下单频率)
  │   ├─ max_notional_per_order (单笔名义价值)
  │   └─ self_trade_prevention (自成交防止)
  ├─ 持续风控 (运行中):
  │   ├─ max_position_notional (持仓名义价值)
  │   ├─ max_position_instrument (单标的持仓)
  │   └─ portfolio_risk_limit (组合级风险)
  └─ 告警: 风控触发 → 日志 + 通知 + 可选自动撤单
```

#### Ditto 风控层现状

```
PreTrade (下单前, 6 条规则):
  ├─ NoShortSellRule:      禁止卖空
  ├─ PriceValidityRule:    涨跌停检查
  ├─ LotSizeRule:          100+1 手数（含 resize）
  ├─ BuyingPowerRule:      资金充足性
  ├─ ConcentrationRule:    单标的集中度
  └─ DailyTurnoverRule:    日换手率

PostTrade (成交后, 4 条规则):
  ├─ MaxDrawdownRule:      最大回撤（有状态，追踪峰值 NAV）
  ├─ SingleLossLimitRule:  单笔亏损限制
  ├─ ConcentrationLimit:   组合集中度
  └─ MarketAnomalyRule:    市场异常检测
```

### 6.4 风控层差距矩阵

| 能力 | LEAN | NautilusTrader | Ditto | 差距 |
|------|------|---------------|-------|------|
| 单标的仓位限制 | ✅ | ✅ | ✅ (ConcentrationRule) | - |
| 资金充足性 | ✅ | ✅ | ✅ (BuyingPowerRule) | - |
| 最大回撤 | ✅ | ✅ | ✅ (MaxDrawdownRule) | - |
| 行业暴露限制 | ✅ | ✅ | ❌ | **大** |
| 因子暴露限制 | ❌ | ❌ | ❌ | **中** (业界也缺) |
| 流动性风险 | ✅ | ✅ | ❌ | **中** |
| 实时持续监控 | ✅ | ✅ (独立 Actor) | ❌ (仅步骤内) | **大** |
| 风险预算分配 | ❌ | ✅ | ❌ | **中** |
| 压力测试 | ❌ | ❌ | ❌ | **中** (业界也缺) |
| 风控告警 | ✅ | ✅ | ❌ | **大** |
| 自动撤单 | ✅ | ✅ | ❌ | **大** |


---

## 7. 组合优化与归因分析

### 7.1 组合优化对比

#### LEAN 组合优化

```
IPortfolioConstructionModel
  ├─ EqualWeightingPortfolioConstructionModel    → 等权
  ├─ BlackLittermanPortfolioConstructionModel    → Black-Litterman
  ├─ MeanVarianceOptimizationPortfolioConstructionModel → 均值-方差
  ├─ UnconstrainedMeanVariancePortfolioConstructionModel → 无约束 MVO
  └─ CustomPortfolioConstructionModel             → 自定义
```

LEAN 的组合优化直接集成在主循环中，每个 rebalance 日自动调用。

#### 量化机构常用优化方法

| 方法 | 适用场景 | 复杂度 |
|------|---------|--------|
| 均值-方差 (MVO) | 基础组合优化 | 低 |
| Black-Litterman | 融合观点的贝叶斯优化 | 中 |
| 风险平价 (Risk Parity) | 等风险贡献 | 中 |
| 最大分散化 (MDP) | 最大化分散化 | 中 |
| 层级风险平价 (HRP) | 层次聚类 + 风险平价 | 中 |
| Robust 优化 | 参数不确定性 | 高 |
| 条件 VaR / CVaR 优化 | 尾部风险控制 | 高 |

常用工具：`cvxpy` (凸优化)、`scipy.optimize` (通用优化)、`riskparityportfolio` (风险平价)

#### Ditto 现状

```python
# 当前仅 3 个分配器
WeightAllocator (Protocol)
  ├─ EqualWeightAllocator:    等权分配
  ├─ ScoreWeightAllocator:    按分数加权
  └─ InverseVolAllocator:     反波动率加权

# 3 个约束
Constraint (Protocol)
  ├─ MaxWeightConstraint:     最大权重
  ├─ MinWeightConstraint:     最小权重
  └─ MaxPositionsConstraint:  最大持仓数
```

**差距**：
- 无优化求解器集成（cvxpy/scipy）
- 无 Black-Litterman 观点融合
- 无行业/因子暴露约束
- 无自适应权重（根据市场状态切换）

### 7.2 归因分析对比

#### 标准归因框架

**Brinson 归因**（行业标准）：
```
总收益 = 配置收益 + 选择收益 + 交互收益

配置收益 = Σ(基准权重 × (行业收益 - 基准收益))
选择收益 = Σ(实际权重 × (个股收益 - 行业收益))
交互收益 = Σ((实际权重 - 基准权重) × (行业收益 - 基准收益))
```

**因子归因**（Fama-French / Barra 风险模型）：
```
组合收益 = α + β_market × R_market + β_SMB × SMB + β_HML × HML + ε

风险贡献 = Σ(因子暴露 × 因子收益)
特质收益 = 总收益 - 系统性收益
```

**交易成本归因**：
```
Implementation Shortfall = 理想价格 - 实际成交价
  = 预期成本（选择成本 + 延迟成本）
  + 交易成本（价差 + 手续费）
  + 市场冲击
```

#### Ditto 现状

`BacktestReport` 提供：
- NAV 曲线、年化收益、波动率
- 夏普、卡尔马、最大回撤、CVaR
- `AlphaStatsView`、`AggregatedTradeStatsView`

这是**绩效度量**（Performance Measurement），不是**归因分析**（Attribution Analysis）。绩效度量告诉你"赚了多少"，归因分析告诉你"为什么赚"。

### 7.3 改造建议

```python
# 建议新增的组合优化 Protocol
class PortfolioOptimizer(Protocol):
    def optimize(
        self,
        expected_returns: pl.DataFrame,   # 预期收益
        covariance: pl.DataFrame,         # 协方差矩阵
        constraints: list[OptConstraint], # 约束列表
        views: list[View] | None = None,  # Black-Litterman 观点
    ) -> dict[InstrumentId, float]:
        """返回 instrument_id → weight 映射"""
        ...

# 建议新增的归因分析 Protocol
class AttributionAnalyzer(Protocol):
    def brinson(self, portfolio, benchmark) -> BrinsonResult: ...
    def factor_attribution(self, portfolio, factor_returns) -> FactorAttribution: ...
    def transaction_cost(self, trades) -> TransactionCostAttribution: ...
```


---

## 8. 引擎层代码级架构问题

### 8.1 EngineLoop God Class（~630 行）

**位置**：`packages/engine/src/ditto_engine/backtest/engine.py`

**问题**：`EngineLoop` 承担了过多职责：
- 日历步进调度
- 数据获取与组装
- 风控扫描
- 策略 Pipeline 执行
- 执行规划
- PreTrade 验证
- 订单提交与撮合
- 审计收集
- 报告生成

`_step()` 方法 ~110 行，包含 6+ 层嵌套逻辑。

**业界对比**：
- LEAN 的 `AlgorithmManager` 将每步拆分为独立的 `Step()` 方法，由调度器调用
- NautilusTrader 将每步拆分为独立 Actor，消息驱动

**建议**：拆分为可组合的 Step 函数或独立的 Step Handler：

```python
# 建议: Step Chain 模式
class StepResult(NamedTuple):
    continue_loop: bool
    context: StepContext

class TradingStep(Protocol):
    def execute(self, ctx: StepContext) -> StepResult: ...

# 具体步骤
class DataFeedStep(TradingStep): ...    # 获取数据
class RiskScanStep(TradingStep): ...    # PostTrade 扫描
class StrategyStep(TradingStep): ...    # 策略计算
class ExecutionStep(TradingStep): ...   # 执行规划 + 下单
class AuditStep(TradingStep): ...       # 审计收集

# EngineLoop 变为 Step Chain 编排器
class EngineLoop:
    def __init__(self, steps: list[TradingStep]): ...
    def run(self): ...
```

### 8.2 DecisionFrame 无 Schema 保护

**位置**：`packages/engine/src/ditto_engine/alpha/models.py`

```python
# 当前: 纯类型别名，无运行时保护
DecisionFrame = pl.DataFrame
```

**问题**：列名约定靠文档（`instrument_id`, `signal_value`, `score`, `weight`, `reason_codes`），拼错列名静默失败，只有到实际使用时才抛出 `ColumnNotFoundError`。

**业界对比**：
- LEAN 用 `Slice` 强类型封装（`Slice.Bars["AAPL"]`, `Slice.Indicators["sma"]`）
- NautilusTrader 用 `BarType` + `Instrument` 强类型关联

**建议**：

```python
# 最低成本: 定义列名常量 + debug 模式验证
class DecisionFrame(pl.DataFrame):
    """带 schema 验证的 DecisionFrame"""

    REQUIRED_COLUMNS = frozenset({
        "instrument_id", "signal_value",
    })
    OPTIONAL_COLUMNS = frozenset({
        "score", "weight", "rank", "reason_codes",
    })

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.DEBUG:
            missing = self.REQUIRED_COLUMNS - set(self.columns)
            if missing:
                raise ValueError(f"DecisionFrame 缺少必要列: {missing}")
```

### 8.3 硬编码信号计算

**位置**：`EngineLoop._build_input_bundle()`

```python
# 当前: 动量信号硬编码在引擎循环内
close_to_close_return = (close / close.shift(1)) - 1
```

**问题**：信号应该由策略定义（通过 StrategySpec 或 SignalProvider），不应嵌入引擎循环。

**建议**：引入 `SignalProvider` Protocol，由 StrategySpec 配置使用哪个信号提供者。

### 8.4 MaxDrawdownRule 状态泄漏

**位置**：`packages/engine/src/ditto_engine/risk/post_trade.py`

**问题**：`MaxDrawdownRule` 内部维护 `peak_nav` 状态，但无 `reset()` 方法。如果同一实例在多次回测中复用，峰值 NAV 会泄漏。

**建议**：添加 `reset()` 方法，或在每次 `EngineLoop.run()` 开始时重建 PostTrade 守卫。

### 8.5 StrategySpec 使用 dict[str, object]

**位置**：`packages/engine/src/ditto_engine/alpha/specs.py`

```python
@dataclass(frozen=True)
class StrategySpec:
    params: dict[str, object]           # 无类型安全
    constraints: list[ConstraintSpec]
    # ...
```

**问题**：`dict[str, object]` 牺牲了类型安全，参数拼错名字或类型不匹配只能在运行时发现。

**建议**：使用 `TypedDict` 或 Pydantic model 定义策略参数 schema，至少做到参数名和类型的声明式验证。

### 8.6 Orchestrator 模块缺失

**位置**：`packages/engine/CLAUDE.md` 引用 `orchestrator/` 目录

**问题**：文档中描述了 `TradingOrchestrator Protocol` 和 `BacktestTradingOrchestrator` alias，但源码中不存在。这是文档与实现的不一致。

**建议**：要么实现该模块，要么从文档中移除引用。


---

## 9. Ditto 独特优势与护城河

在深入分析差距之后，有必要系统梳理 Ditto 相对于业界开源项目的独特优势。这些是未来竞争的护城河。

### 9.1 超越 LEAN 的能力

| 能力 | LEAN | Ditto | Ditto 优势说明 |
|------|------|-------|--------------|
| 因子表达式编译器 | ❌ 无内建 | ✅ Lexer→Parser→AST→Analyzer→Codegen | 完整的编译器管线，Rust 级错误诊断 |
| PIT 安全保证 | 配置级别 | 编译器级别 `shift(1)` | 在编译期就杜绝前视偏差 |
| 因子评估深度 | 基础 IC | Grinold-Kahn IR + Fama-MacBeth + 正交化 + Regime IC | 业界领先的分析深度 |
| 数据质量引擎 | 基础 | L1-L4 四级检查 | 开源领域最全面 |
| A 股规则精度 | 通用模型 | T+1/100+1/涨跌停/费率全部模型化 | 专业级 A 股支持 |
| 声明式策略 | 自由代码 | StrategySpec 冻结规格 | 可审计、可版本化 |

### 9.2 超越 Qlib 的能力

| 能力 | Qlib | Ditto | Ditto 优势说明 |
|------|------|-------|--------------|
| 回测引擎 | 基础 | 完整 A 股规则回测 | Qlib 偏研究，Ditto 偏交易 |
| 风控系统 | 基础 | 10 条 Pre/PostTrade 规则 | 更接近实盘需求 |
| 审计追踪 | 无 | ExecutionAuditCollector | 金融级审计能力 |
| 架构清晰度 | 单包 | 6 包分层 + importlinter | 更好的可维护性 |

### 9.3 超越 Zipline 的能力

| 能力 | Zipline | Ditto | Ditto 优势说明 |
|------|---------|-------|--------------|
| 数据质量 | 基础 | L1-L4 | Zipline 无质量引擎 |
| A 股支持 | ❌ | ✅ | Zipline 专注美股 |
| 执行模型 | 简单撮合 | Reality Model 四件套 | 更真实的交易成本建模 |
| 策略模板 | ❌ | 4 个 A 股模板 | 开箱即用的 A 股策略 |

### 9.4 超越 NautilusTrader 的能力

| 能力 | NautilusTrader | Ditto | Ditto 优势说明 |
|------|---------------|-------|--------------|
| 因子系统 | ❌ 无内建 | ✅ 编译器+评估+物化 | NautilusTrader 需要用户自行实现 |
| 数据质量 | Schema 验证 | L1-L4 四级 | 更全面的质量保证 |
| 研究工具 | 基础 | 因子评估 + Research Dataset | 更强的研究工作流 |

### 9.5 Ditto 的核心定位

```
                    研究深度
                       ↑
                       │
              Qlib ●   │   ● Ditto（目标）
                       │
    Zipline ●          │          ● NautilusTrader
                       │
    Backtrader ●       │                ● LEAN
                       │
    ───────────────────┼──────────────────→ 交易完备性
                  研究              实盘
```

Ditto 的**理想定位**是：**兼具 Qlib 的研究深度和 LEAN 的交易完备性，同时保持 A 股市场规则的专业级精度**。当前 Ditto 更偏研究端，需要向交易端延伸。


---

## 10. 架构能力成熟度矩阵

### 10.1 总览评分

| 能力域 | 成熟度 | 评级 | 相对业界 | 关键差距 |
|--------|-------|------|---------|---------|
| 分层架构 | 完整实现 | **A** | 领先 | 业界最佳之一，importlinter 机器化 |
| 因子编译器 | 完整实现 | **A** | 领先 | 37 算子、PIT-safe、Rust 级诊断 |
| 因子评估 | 完整实现 | **A-** | 领先 | Grinold-Kahn IR、Fama-MacBeth、Regime IC |
| 数据质量 | 完整实现 | **A-** | 领先 | L1-L4 四级检查，缺实时监控 |
| A 股回测 | 完整实现 | **B+** | 对齐 | 规则深度好，但仅日频单线程 |
| 数据接入 | 完整实现 | **B** | 对齐 | Tushare/TDX/FRED，缺实时流 |
| 策略 Pipeline | 完整实现 | **B** | 对齐 | 8 stage + 4 模板，仅单策略 |
| 风控系统 | 基本可用 | **B-** | 略低 | 10 条规则覆盖主场景，缺组合级 |
| 执行层 | 基本可用 | **C+** | 低于平均 | A 股规则好，但仅 MARKET 单 |
| 组合优化 | 最小可用 | **D+** | 低于平均 | 3 个基础分配器，缺优化算法 |
| 归因分析 | 最小可用 | **D** | 低于平均 | 绩效度量有，无真正归因 |
| 回测/实盘一致 | 未实现 | **F** | 显著落后 | 无实盘路径 |
| 多策略 | 未实现 | **F** | 显著落后 | 单策略单账户 |
| 实时数据流 | 未实现 | **F** | 显著落后 | 仅批量拉取 |
| 参数优化 | 未实现 | **F** | 显著落后 | 元数据存在但无框架 |
| 生产运维 | 未实现 | **F** | 显著落后 | 无监控/告警/灾备 |

### 10.2 分阶段成熟度目标

| 能力域 | 当前 | Phase A 后 | Phase B 后 | Phase C 后 |
|--------|------|-----------|-----------|-----------|
| 回测/实盘一致 | F | D | B | A |
| 多策略 | F | D | B | A |
| 执行层 | C+ | B | B+ | A- |
| 风控系统 | B- | B | B+ | A- |
| 组合优化 | D+ | D+ | B | B+ |
| 归因分析 | D | D | B- | B |
| 实时数据流 | F | F | C | B |
| 参数优化 | F | F | D+ | B |
| 生产运维 | F | F | C+ | B |


---

## 11. 架构演进路线建议

### 11.1 三阶段演进概览

```
当前状态                    Phase A                Phase B                Phase C
(研究型回测系统)            (架构基础)              (能力扩展)              (实盘就绪)
──────────────────────────────────────────────────────────────────────────────────
                           核心引擎重构             多策略支持              实盘执行
                           统一核心接口             组合优化                实时数据
                           代码质量                 参数优化                生产运维
```

### 11.2 Phase A: 核心引擎重构（架构基础）

**目标**：为统一回测/实盘核心打好架构基础，消除代码级技术债务。

**A1: 抽取 TradingLoop Protocol**
- 将 `EngineLoop._step()` 拆分为可组合的 Step 函数
- 定义 `TradingLoop` Protocol 接口
- EngineLoop 从 God Class 降级为 Step Chain 编排器
- **不影响现有功能**，纯重构

**A2: Clock 全链路注入**
- 确保 EngineLoop 所有时间操作通过 `kernel.Clock`
- 移除 `_step()` 中的直接 `datetime` 使用
- 为未来 `SimulatedClock` / `RealtimeClock` 切换铺路

**A3: DataFeed Protocol 强化**
- 定义 `BarStream` / `TickStream` 统一数据流接口
- `ProviderBackedDataFeed` 实现新接口
- 为未来实时数据源适配铺路

**A4: DecisionFrame Schema 保护**
- 从类型别名升级为带 runtime validation 的包装类型
- 定义 `DecisionFrameColumns` 列名常量
- Debug 模式自动验证

**A5: 代码质量修复**
- 修复 `MaxDrawdownRule` 状态泄漏（添加 reset）
- 移除 `_build_input_bundle()` 中的硬编码信号
- 实现/移除 `orchestrator/` 模块引用
- `StrategySpec.params` 类型安全化

**预计影响**：~500 行重构，0 行新功能，100% 向后兼容

### 11.3 Phase B: 能力扩展

**目标**：引入多策略支持、组合优化、参数优化等核心量化能力。

**B1: 多策略接口设计**
- 定义 `StrategyInstance`（运行实例）和 `StrategyRegistry`（注册中心）
- `StrategySpec` 保持不变（规格），`StrategyInstance` 管理运行时状态
- 接口设计保证未来可以渐进式引入多策略

**B2: PortfolioOptimizer Protocol**
- 集成 `cvxpy` 做约束优化
- 实现 Mean-Variance、Risk Parity 基础算法
- 支持 `OptConstraint`（行业/因子暴露约束）

**B3: 归因分析框架**
- Brinson 归因（配置 + 选择 + 交互）
- 因子归因（Fama-French 三因子/五因子）
- 交易成本归因（实现 shortfall）

**B4: 参数优化框架**
- 网格搜索 / 随机搜索
- Walk-Forward 验证
- 过拟合检测（样本外衰减分析）

**B5: 执行层增强**
- LIMIT 单支持
- 订单有效期（DAY/GTC）
- 基础挂单/撤单管理
- 实现 shortfall 归因

**B6: 组合级风控**
- 行业暴露限制
- 流动性风险检查
- 风控告警机制

**预计影响**：~3000 行新代码，新增 `cvxpy` 依赖

### 11.4 Phase C: 实盘就绪

**目标**：支持 A 股实盘交易，具备生产级运维能力。

**C1: 实时数据流**
- WebSocket 接入 Level-1 行情
- `LiveDataFeed` 实现 `BarStream` 接口
- 历史数据到实时数据的无缝切换

**C2: LiveBrokerage 实现**
- 连接 A 股券商（XtQuant / 掘金 / QMT）
- 实现 `Brokerage` Protocol
- 完整订单状态机

**C3: 实时风控服务**
- 独立运行的持续风控检查
- 风控触发 → 告警 + 可选自动撤单
- 风险预算管理

**C4: 生产运维**
- Prometheus 指标导出 + Grafana 面板
- 策略运行状态监控
- 交易审计日志
- 状态快照 + 重放

**C5: OMS 订单管理**
- 挂单管理（查询/修改/撤销）
- 部分成交处理
- 算法执行（TWAP/VWAP 基础版）

**预计影响**：~5000 行新代码，新增券商 SDK 依赖

### 11.5 优先级矩阵

| 任务 | 业务价值 | 技术复杂度 | 依赖 | 建议优先级 |
|------|---------|-----------|------|-----------|
| A1 TradingLoop Protocol | 高（架构基础） | 中 | 无 | P0 |
| A4 DecisionFrame Schema | 高（正确性） | 低 | 无 | P0 |
| A5 代码质量修复 | 中（可维护性） | 低 | 无 | P0 |
| A2 Clock 全链路 | 高（实盘前提） | 低 | A1 | P1 |
| A3 DataFeed Protocol | 高（实盘前提） | 中 | A1 | P1 |
| B1 多策略接口 | 高（扩展性） | 中 | A1 | P1 |
| B2 PortfolioOptimizer | 中（量化能力） | 中 | 无 | P2 |
| B3 归因分析 | 中（研究工具） | 中 | 无 | P2 |
| B4 参数优化 | 中（研究工具） | 中 | 无 | P2 |
| B5 执行层增强 | 中（交易能力） | 高 | A1 | P2 |
| B6 组合级风控 | 中（风控能力） | 中 | B1 | P2 |
| C1 实时数据流 | 高（实盘前提） | 高 | A2, A3 | P3 |
| C2 LiveBrokerage | 高（实盘核心） | 高 | A1, C1 | P3 |
| C3 实时风控 | 中（实盘安全） | 高 | B6, C2 | P3 |
| C4 生产运维 | 中（运维能力） | 中 | C2 | P3 |
| C5 OMS 订单管理 | 中（执行能力） | 高 | B5, C2 | P3 |

---

## 附录 A: 参考资料索引

| 文档 | 路径 |
|------|------|
| LEAN 架构参考 | `docs/reviews/2026-03-20-quantconnect-lean-architecture-reference.md` |
| T1 差距审计 | `docs/reviews/2026-03-20-t1-gap-audit.md` |
| 业界平台对标 | `docs/reviews/2026-03-20-industry-benchmark-quant-platforms.md` |
| A 股交易规则 | `docs/reviews/2026-03-20-a-share-etf-trading-rules.md` |
| 评分卡概览 | `docs/reviews/2026-04-07-industry-benchmark-gap-analysis.md` |
| Phase 4 App 层设计 | `docs/plans/2026-04-01-phase4-app-layer-design.md` |
| V1 发布能力计划 | `docs/plans/2026-04-07-v1-launch-capability-plan.md` |

## 附录 B: 业界平台参考链接

| 平台 | 类型 | 语言 | 开源 |
|------|------|------|------|
| QuantConnect LEAN | 回测+实盘 | C# | ✅ Apache-2.0 |
| NautilusTrader | 高频交易 | Rust+Python | ✅ Apache-2.0 |
| Zipline | 因子回测 | Python | ✅ Apache-2.0 |
| Backtrader | 策略回测 | Python | ✅ |
| Vectorbt | 向量化回测 | Python | ✅ |
| Microsoft Qlib | AI Alpha | Python | ✅ MIT |
| Freqtrade | 加密交易 | Python | ✅ GPLv3 |
| Hummingbot | 做市交易 | Python | ✅ Apache-2.0 |
| Jesse | 加密策略 | Python | ✅ Apache-2.0 |
| OpenBB | 金融数据 | Python | ✅ AGPL-3.0 |
| Databento | 市场数据 | Rust+Python | ❌ 商业 |
