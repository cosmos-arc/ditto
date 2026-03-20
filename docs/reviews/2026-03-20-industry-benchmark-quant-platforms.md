# 业界量化平台能力对标调研报告

**日期**: 2026-03-20
**调研目的**: 为 Ditto T1 目标提供能力差距评估基准
**调研范围**: 7 个业界代表性量化平台/框架

---

## 1. 调研平台概览

| 平台 | 定位 | Stars/用户 | 最新版本 | 语言 |
|------|------|-----------|---------|------|
| QuantConnect LEAN | 企业级云端量化交易引擎 | 275K+ 用户 | 持续更新 | C# / Python |
| Qlib (Microsoft) | AI 驱动的量化投资研究平台 | 39.1K Stars | v0.9.7 (2025-08) | Python |
| Zipline-Reloaded | 经典事件驱动回测框架 | 社区维护 | 2.0.0rc3 | Python |
| Backtrader | 功能丰富的回测框架 | 经典项目 | 维护停滞 | Python |
| VectorBT Pro | 高性能向量化回测引擎 | 社区活跃 | PRO 付费 | Python |
| AlphaAgent (2025) | LLM 驱动的 Alpha 因子挖掘 | 学术项目 | 2025-02 发表 | Python |
| OpenBB Platform | 开源投资研究平台 | Linux Foundation | v4 Beta | Python |

---

## 2. 各平台详细能力分析

### 2.1 QuantConnect LEAN — T1 标杆

**核心架构**: 事件驱动统一引擎，回测和实盘共享同一套接口。

**模块化 Pipeline（Algorithm Framework）**:
```
Universe Selection → Alpha Model → Portfolio Construction → Risk Management → Execution
```

**一等对象**:
- `Insight`: 信号（方向、幅度、置信度、有效期、权重）
- `PortfolioTarget`: 目标持仓（标的 + 数量）
- `Order` / `OrderTicket` / `OrderEvent`: 订单全生命周期
- `Slice`: 时间切片（每个时间步的数据包）
- `SecurityHolding`: 持仓状态
- `CashBook`: 多币种现金簿

**Reality Model（可插拔现实约束）**:
- FillModel（填充模型）、SlippageModel（滑点模型）、FeeModel（佣金模型）
- SettlementModel（交收模型）、BuyingPowerModel（购买力模型）
- 每个 Security 可独立覆盖模型配置

**Broker 抽象**:
- `IBrokerage` 统一接口，BacktestBroker 和 LiveBroker 共享
- `BrokerageModel` 打包某个券商的规则/约束
- 内置支持：IB、Binance、GDAX 等 20+ 券商

**统计体系**:
- Trade Statistics（胜率、盈亏比、平均持仓时间）
- Portfolio Statistics（Sharpe/Sortino/MaxDD/IR/TE）
- Alpha Statistics（Insight 准确率、幅度实现度）
- 图表：权益曲线、回撤图、持仓分布

**2025-2026 新能力**:
- HuggingFace 集成（FinBERT, Chronos-T5 等可直接在策略中使用）
- Walk Forward Optimization 参数优化
- 200+ 技术指标

**API 产品化**: **极高** — 云平台 + REST API + Web IDE + 20+ Broker 集成

---

### 2.2 Qlib (Microsoft) — AI 研究标杆

**核心架构**: ML 工作流优先（数据构建 → 模型训练 → 预测 → 回测/评估）。

**策略定义**: YAML 配置驱动 + Python 自定义 Workflow。

**内置模型**: 25+（LightGBM、LSTM、Transformer、TFT、TabNet、GRU、TCN 等）。

**组合构建**:
- TopkDropoutStrategy（Topk-Drop 算法）
- EnhancedIndexingStrategy（跟踪误差控制）
- Planning-based Portfolio Optimization

**实验管理**: **强**
- Qlib Recorder + MLflow 集成
- 参数记录、指标对比、artifact 存储、模型注册
- 多模型批量运行和结果收集

**可解释性**: **强**
- IC/RankIC 曲线、月度 IC、累计收益分组
- Graphical Reports 支持 Jupyter

**2025 新能力**: RD-Agent（LLM 驱动的自动因子挖掘与模型优化多智能体框架）

**API 产品化**: **中低** — 纯研究工具，无实盘执行接口

---

### 2.3 Zipline-Reloaded — 事件驱动回测标杆

**核心架构**: 事件驱动回调（`handle_data`），严格逐 bar 模拟。

**订单系统**: Market/Limit/Stop 订单，完整生命周期。

**Reality Model**: SlippageModel、CommissionModel、Bloomberg Bundle。

**生态**: Pyfolio Reloaded（回测报告）、Alphalens Reloaded（因子分析）。

**2025 趋势**: RustyBT 在 Zipline 基础上增加了 Decimal 精度和 Polars 引擎。

**局限**: 无实验管理、无组合优化、API 产品化低。

---

### 2.4 VectorBT Pro — 向量化回测标杆

**核心架构**: 向量化表达式风格，一个策略 = 一组列。

**性能**: 比事件驱动快 100-1000 倍（适合参数扫描）。

**组合构建**: 集成 PyPortfolioOpt（Markowitz、Black-Litterman 等）。

**可解释性**: **极强**
- Edge Ratio（量化入场盈利能力）
- Pattern Recognition（2.3 亿种模式自动检测）
- Event Projections

**局限**: 无实盘执行、实验管理中等。

---

### 2.5 AlphaAgent — LLM 因子挖掘标杆 (2025)

**核心创新**: LLM 驱动的 Alpha 因子自动生成。

**三大机制**:
1. AST 相似度原创性约束（防止因子重复）
2. 假设-因子对齐（LLM 评估市场假设与因子语义一致性）
3. 复杂度控制（AST 结构约束，防止过度拟合）

**Alpha Decay 跟踪**: 多 regime 下 IC 退化曲线。

**局限**: 研究工具/学术项目，API 产品化低，强依赖 OpenAI API。

---

### 2.6 Backtrader — 经典回测框架

**核心架构**: 面向对象回调（继承 `bt.Strategy`，实现 `next()`）。

**内置**: 150+ 技术指标、多种 Sizer、多种 Analyzer。

**局限**: 项目维护停滞，社区支持减弱，新项目倾向 VectorBT 或 NautilusTrader。

---

### 2.7 OpenBB Platform — 数据平台标杆

**核心定位**: "Bloomberg Terminal 的免费替代品"，Linux Foundation 项目。

**数据覆盖**: 近 100 个数据源的标准化 API。

**2026 新能力**: Quantly MCP 集成（多步工作流）、AI Copilot。

**局限**: 无回测引擎、无策略定义、无实盘执行。

---

## 3. 综合对比矩阵

| 维度 | QC | Qlib | Zipline | Backtrader | VBT | AlphaAgent | OpenBB |
|------|:--:|:----:|:-------:|:---------:|:---:|:----------:|:------:|
| **策略定义** | 模块化Pipeline | ML Workflow | 事件回调+Pipeline | OOP回调 | 向量化 | LLM自动生成 | N/A |
| **回测引擎** | 企业级事件驱动 | 日频模拟器 | 事件驱动 | 事件驱动 | 向量化高速 | 依赖Qlib | 无 |
| **组合构建** | 内置优化器 | Topk-Drop/增强 | 基础API | Sizer体系 | PyPortfolioOpt | 因子挖掘 | OpenPortfolio |
| **实验管理** | 云端项目 | Recorder+MLflow | 无 | 无 | 云实例 | Agent自管理 | Hub协作 |
| **可解释性** | 中 | 强(IC/报告) | 中(Pyfolio) | 中(Analyzers) | 极强(Edge) | 极强(AST) | 强(可视化) |
| **API产品化** | **极高** | 低 | 低 | 低 | 中 | 低 | 高(数据层) |
| **实盘能力** | **原生支持** | Online Serving | StrateQueue桥接 | IBC桥接 | 无 | 无 | 无 |
| **LLM/AI集成** | HuggingFace | RD-Agent | 无 | 无 | 无 | **核心能力** | MCP Copilot |
| **T1 能力** | **10** | 7 | 5 | 5 | 7 | 4 | 4 |

---

## 4. 对 Ditto 的借鉴价值

### 4.1 已吸收的业界共识

| 来源 | 已采纳的设计 |
|------|------------|
| QuantConnect | 阶段化 Pipeline（Universe→Signal→Score→...） |
| QuantConnect | Insight 作为一等信号对象（方向、置信度、权重） |
| Qlib | artifact-first 实验管理与版本治理 |
| VectorBT | DataFrame/Polars 向量化计算语言 |
| Feast/dbt | 版本控制和状态感知编排 |
| AQR/Man AHL | 混合范式（信号表达式 + 编排声明式 + Python 逃生舱） |

### 4.2 T1 仍需吸收的设计

| 来源 | 需要借鉴 |
|------|---------|
| QuantConnect | IBrokerage 统一接口（Backtest/Live 共享） |
| QuantConnect | Reality Model 可插拔体系（Fill/Slippage/Fee/Settlement） |
| QuantConnect | Order 生命周期状态机 |
| QuantConnect | 三层统计体系（Trade/Portfolio/Alpha） |
| QuantConnect | Per-step RiskGuard 风控守卫 |
| Qlib | Qlib Recorder + MLflow 实验管理 |
| Qlib | RD-Agent LLM 集成因子挖掘 |
| VectorBT | Walk-Forward 参数扫描 |
| AlphaAgent | AST 相似度原创性约束 |
| AlphaAgent | Alpha Decay 跟踪 |

---

## 5. 业界 80/20 法则参考

| 机构 | 声明式部分 | Python/自由编码部分 |
|------|-----------|-------------------|
| AQR | 因子库（表达式） | 研究员 Python 探索 |
| Man AHL | Pipelines（声明式） | 策略原型 Python |
| WorldQuant | FAST 表达式（核心） | 上层组合/风控内部语言 |
| Qlib | 表达式因子 + 内置模型 | 自定义 Handler Python |
| QuantConnect | 框架声明式 | Alpha Model 全 Python |

统一规律：80% 常规策略走声明式（快速、可复现、可组合），20% 创新策略用 Python 探索（自由、灵活），成熟后提炼为声明式组件沉淀。
