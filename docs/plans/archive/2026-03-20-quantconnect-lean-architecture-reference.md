# QuantConnect LEAN 全栈架构参考

**日期**: 2026-03-20
**用途**: Ditto T1 目标的架构参考蓝本
**参考来源**: LEAN 开源仓库、QuantConnect 官方文档

---

## 1. 总览：引擎分层与数据流

LEAN 是 QuantConnect 开源的事件驱动算法交易引擎（C# 编写，Python/C# 双语言 API），统一了回测和实盘交易。

```
                        ┌──────────────────────────────┐
                        │         Engine (主循环)         │
                        │   Engine.Run() per time step   │
                        └──────────┬───────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │   IDataFeed     │  │ITransactionHandler│  │  IResultHandler │
    │  (数据源抽象)    │  │  (订单处理)      │  │  (结果输出)      │
    └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
             │                    │                    │
             ▼                    ▼                    ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │  IDataFeed      │  │  IBrokerage     │  │  IResultHandler │
    │  实现:          │  │  实现:          │  │  实现:          │
    │  · Backtest     │  │  · Backtesting  │  │  · Backtest     │
    │  · Live(WSS/API)│  │  · IB/TDX/...  │  │  · Live/Desktop │
    └─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Engine 主循环每个时间步**：
1. `IDataFeed` 获取下一个时间步数据
2. 数据打包为 **Slice** 对象
3. 调用算法回调 / Framework 管线
4. `ITransactionHandler` 处理订单
5. `IResultHandler` 输出结果

---

## 2. Algorithm Framework 管线

5 个正交模块，数据流单向传递：

```
Universe Selection ─→ Alpha Model ─→ Portfolio Construction ─→ Risk Management ─→ Execution
     (资产池)          (交易信号)      (目标持仓)              (风险调整)          (订单生成)
```

### 各模块接口

| 模块 | 接口 | 输入 | 输出 |
|------|------|------|------|
| Universe Selection | `IUniverseSelectionModel` | - | `Universe` 对象 |
| Alpha | `IAlphaModel` | `Slice` | `IEnumerable<Insight>` |
| Portfolio Construction | `IPortfolioConstructionModel` | Insight 集合 | `IEnumerable<PortfolioTarget>` |
| Risk Management | `IRiskManagementModel` | Target 集合 | 调整后的 Target |
| Execution | `IExecutionModel` | Target 集合 | OrderTickets |

**关键设计原则**：关注点分离 — 各模块不应依赖其他模块的内部状态。

---

## 3. 核心一等对象

### 3.1 Insight（交易信号）

| 字段 | 类型 | 说明 |
|------|------|------|
| Symbol | Symbol | 标的标识 |
| Direction | InsightDirection | Up / Down / Flat |
| Period | TimeSpan | 信号有效期 |
| Magnitude | decimal | 预期变动幅度 |
| Confidence | decimal | 置信度 [0,1] |
| Weight | decimal | 信号权重 |
| GeneratedTimeUtc | DateTime | 生成时间 |

**InsightManager** 管理活跃 Insight 的生命周期（过期、取消、冲突处理）。

### 3.2 PortfolioTarget（目标持仓）

| 字段 | 类型 | 说明 |
|------|------|------|
| Symbol | Symbol | 标的标识 |
| Quantity | decimal | 目标数量（正=多头，负=空头） |

### 3.3 Order 体系

```
Order (抽象基类)
├── MarketOrder           市价单
├── LimitOrder            限价单
├── StopMarketOrder       止损市价单
├── StopLimitOrder        止损限价单
├── LimitIfTouchedOrder   触及限价单
├── TrailingStopOrder     追踪止损单
├── MarketOnOpenOrder     开盘市价单
├── MarketOnCloseOrder    收盘市价单
└── ComboLegOrder         组合单腿
```

### 3.4 OrderTicket（订单票据）

提交订单后返回的一等引用对象：
- `Cancel()` — 取消订单
- `Update(fields)` — 更新参数
- `Status` — 查询状态
- `OrderEvents` — 事件流

### 3.5 Slice（时间切片）

```
Slice
├── Bars:      {Symbol → TradeBar}    — OHLCV
├── Ticks:     List<Tick>             — 逐笔
├── Quotes:    {Symbol → QuoteBar}    — 报价
├── Splits / Dividends / Delistings   — 公司行为
└── UniverseData                     — Universe 数据
```

### 3.6 Portfolio 对象体系

```
SecurityPortfolioManager
├── Securities: SecurityManager
│   └── Security
│       ├── Price / Bid / Ask / Close
│       └── Models (可插拔):
│           ├── FillModel
│           ├── SlippageModel
│           ├── FeeModel
│           ├── BuyingPowerModel
│           └── SettlementModel
├── Holdings: {Symbol → SecurityHolding}
│   └── SecurityHolding
│       ├── Quantity / AveragePrice
│       ├── MarketValue / UnrealizedProfit
│       └── TotalFees
└── CashBook: CashBook
    └── Cash (per currency)
        ├── Amount
        └── ConversionRate
```

---

## 4. BrokerAdapter 抽象

### IBrokerage 接口

```csharp
interface IBrokerage {
    void Connect();
    void Disconnect();
    bool IsConnected { get; }
    bool PlaceOrder(Order order);
    bool CancelOrder(Order order);
    void UpdateOrder(Order order);
    void GetAccount(Account account);
    event EventHandler<OrderEvent> OrderStatusChanged;
}
```

每个 `IBrokerage` 实现必须配套一个 `IBrokerageFactory`。

### BacktestBroker vs LiveBroker

| 维度 | BacktestBroker | LiveBroker |
|------|---------------|------------|
| 执行 | 同步、确定性、即时 | 异步、非确定性、网络依赖 |
| 数据源 | 历史数据流 | 实时 WebSocket/API |
| Fill | IFillModel 插件模拟 | 真实成交 |
| 滑点 | ISlippageModel 模拟 | 自然发生 |
| 佣金 | IFeeModel 模拟 | 真实收费 |
| 幂等性 | 不需要 | **关键**（避免重复下单） |

### BrokerageModel

回测与实盘的桥梁 — 打包某个券商的规则：
- 支持的资产类别
- 允许的订单类型
- Fee 结构
- Margin 规则
- Lot Size

---

## 5. 订单生命周期状态机

```
                ┌──────────┐
                │   New    │  内部创建
                └────┬─────┘
                     │ PlaceOrder()
                     ▼
                ┌──────────┐
          ┌────►│Submitted │
          │     └────┬─────┘
          │          ├──────────┐
          │          │          │
          │          ▼          ▼
          │   ┌──────────────┐ ┌──────────┐
          │   │PartiallyFilled│ │ Invalid  │
          │   └──────┬───────┘ └──────────┘
          │          │
          │          ▼
          │   ┌──────────┐
          │   │  Filled  │ ← (终态)
          │   └──────────┘
          │
 CancelOrder()
          │
          ▼
    ┌──────────┐
    │ Canceled │  ← (终态)
    └──────────┘
```

**终态**：Filled / Canceled / Invalid — 不可逆。

---

## 6. Reality Model 体系

### Security 级别模型（按每个 Security 独立配置）

| 模型 | 接口 | 职责 |
|------|------|------|
| Fill | IFillModel | 决定订单如何被填充 |
| Slippage | ISlippageModel | 模拟滑点 |
| Fee | IFeeModel | 计算佣金/费用 |
| BuyingPower | IBuyingPowerModel | 购买力检查 |
| Settlement | ISettlementModel | 交收规则 |

### Fill Model 内部协作

```
Execution 请求
    │
    ▼
IFillModel.MarketFill(order, asset)
    ├── 1. 获取当前价格
    ├── 2. 判断是否可成交
    ├── 3. SlippageModel.GetSlippage()  → 加滑点
    ├── 4. 确定成交数量
    └── 5. 返回 Fill (price, quantity, status)
```

### SecurityInitializer

新增 Security 时统一初始化所有模型的机制，避免散落各处。

---

## 7. 风控模型

### 触发时机

每个时间步自动触发，位于 Portfolio Construction 和 Execution 之间。

### 可执行动作

| 动作 | 说明 |
|------|------|
| 修改目标 | 调整 PortfolioTarget.Quantity |
| 平仓 | target = 0 |
| 删除目标 | 从集合中移除 |
| 返回空 | 不产生任何交易 |

### 内置模型

- `MaximumDrawdownPercentPerSecurity`
- `TrailingStopRiskManagementModel`
- `MaximumSectorExposureRiskManagementModel`
- `CompositeRiskManagementModel`

---

## 8. 统计体系

### 三层统计

| 层级 | 组件 | 指标 |
|------|------|------|
| Trade | TradeBuilder | 胜率、盈亏比、平均持仓时间 |
| Portfolio | PortfolioStatistics | Sharpe/Sortino/Treynor/MaxDD/IR/TE |
| Algorithm | StatisticsBuilder | 总交易次数、周转率、权益曲线 |

### 结果持久化

- `orders.csv` — 所有订单
- `equity.csv` — 每日权益
- `profit-loss.csv` — 已实现盈亏
- `alpha.csv` — Alpha 统计
- `report.html` — 完整报告

---

## 9. 源码结构

```
Lean/
├── Common/
│   ├── Interfaces/        (IBrokerage, IDataFeed, IResultHandler)
│   ├── Orders/            (Order, OrderTicket, OrderEvent)
│   ├── Securities/        (Security, SecurityHolding, CashBook)
│   ├── Statistics/        (PortfolioStatistics, TradeBuilder)
│   └── Algorithm/Framework/ (Alpha, Portfolio, Risk, Execution)
├── Engine/
│   ├── Engine.cs          (主循环)
│   ├── DataFeeds/         (数据源实现)
│   ├── Results/           (结果处理器实现)
│   └── TransactionHandlers/
└── Brokerages/
    ├── Backtesting/       (BacktestingBrokerage)
    └── [各券商插件]/      (IB, Binance, etc.)
```

---

## 10. 对 Ditto 的架构启发

1. **单向数据流管线**：Insight → PortfolioTarget → AdjustedTarget → Order，模块间无反向依赖
2. **接口与实现完全分离**：IBrokerage 一个接口服务 Backtest 和 Live
3. **Reality Model 组合模式**：BrokerageModel 打包子模型，每个 Security 可独立覆盖
4. **OrderTicket 一等引用**：比纯 ID 追踪更优雅的 API 设计
5. **SecurityInitializer 模型注入**：统一新增资产时的模型初始化
6. **三层统计体系**：Trade/Portfolio/Alpha 独立计算，覆盖不同分析维度
