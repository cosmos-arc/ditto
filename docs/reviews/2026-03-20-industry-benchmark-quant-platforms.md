# 业界量化平台能力对标调研报告

**日期**: 2026-03-20
**调研目的**: 为 Ditto T1 目标提供能力差距评估基准
**调研范围**: 10 个业界代表性量化平台/框架（含 3 个 A 股生态项目）

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

---

## 6. A 股生态项目深度分析（2026-03-20 追加）

### 6.1 TradingAgents — LLM 多 Agent 交易决策框架

**定位**: 模拟真实交易公司动态的 LLM 驱动多 Agent 协作决策框架（研究工具，非交易平台）。

**核心创新**: 将复杂交易决策分解为专业化角色，通过**结构化辩论（debate）**达成共识。

**Agent 架构（4 类 7+ 角色）**:

| Agent 类型 | 角色 | 职责 |
|-----------|------|------|
| Analyst Team | Fundamental Analyst | 财报分析、内在价值、风险信号 |
| Analyst Team | Sentiment Analyst | 社交媒体/舆情情绪评分 |
| Analyst Team | News Analyst | 全球新闻/宏观经济事件解读 |
| Analyst Team | Technical Analyst | MACD/RSI 等技术指标分析 |
| Researcher Team | Bull Researcher | 看多论证，评估上涨潜力 |
| Researcher Team | Bear Researcher | 看空论证，评估下行风险 |
| Trading Group | Trader Agent | 综合所有分析做出交易决策（自反思架构） |
| Risk & Portfolio | Risk Management | 评估波动率/流动性/风险因子 |
| Risk & Portfolio | Portfolio Manager | 审批/拒绝交易提案，最终决策 |

**技术实现**:
- 基于 LangGraph 构建有向图工作流
- 支持多 LLM 提供商（OpenAI GPT-5.x / Google Gemini 3.x / Anthropic Claude 4.x / xAI Grok 4.x / Ollama 本地模型）
- 双模型策略：`deep_think_llm`（复杂推理）+ `quick_think_llm`（快速任务）
- 可配置辩论轮次（`max_debate_rounds`）
- CLI + Python API 两种使用方式
- 数据源：Alpha Vantage API

**能力评分**:

| 维度 | 分数 | 说明 |
|------|------|------|
| 策略定义 | 3 | LLM 自由文本，不可序列化、不可复现 |
| 回测引擎 | 0 | 无回测能力 |
| 组合构建 | 2 | 仅 PM 审批单笔交易，无组合优化 |
| 风险管理 | 4 | 有 Risk Management Agent，但仅 LLM 文本分析 |
| 实验管理 | 2 | 无版本控制、无参数扫描 |
| 可解释性 | 8 | **极强** — 完整的辩论记录、多角色分析报告 |
| API 产品化 | 2 | CLI + Python import，无 Web/REST |
| 实盘能力 | 0 | 无 |
| LLM/AI 集成 | **10** | **核心能力** — 多 Agent + 辩论 + 多模型 |

**与 Ditto 的借鉴价值**:
1. **多角色辩论机制**: 可作为 Ditto 未来 LLM 辅助策略分析的模式参考
2. **双模型策略**: 推理任务和快速任务使用不同模型，成本/性能优化
3. **自反思架构**: Trading Group 的迭代改进模式
4. **可解释性标杆**: 完整的决策链路记录是 LLM 交易系统的可解释性最佳实践

**局限性**:
- 无回测、无订单管理、无风控执行 — 不是交易平台
- 依赖 LLM 输出的非确定性，交易结果波动大
- 仅支持美股（Alpha Vantage 数据源）
- 无因子引擎、无组合优化

---

### 6.2 Panda QuantFlow — A 股量化交易一体化平台

**定位**: 面向 A 股市场的低门槛量化交易一体化平台，可视化工作流编排 + 事件驱动回测 + CTP 实盘。

**核心架构**:

```
panda_server (FastAPI)  ←  工作流编排中枢
    ├── panda_plugins/     ← 插件化工作流节点（~40+ 节点）
    ├── panda_backtest/    ← 事件驱动回测引擎
    ├── panda_trading/     ← CTP 实盘对接
    ├── panda_ml/          ← ML 模型抽象
    └── panda_web/         ← Vue/React SPA 前端
```

**核心抽象**:

| 抽象 | 设计 |
|------|------|
| 工作流节点 | `BaseWorkNode` + `@work_node` 装饰器 + Pydantic I/O |
| 回测事件 | `EventBus` 发布-订阅，50+ 事件类型 |
| 策略 API | 聚宽/米筐风格：`initialize()` + `handle_data(context, bar)` |
| 交易代理 | `BaseOperationProxy` 统一回测/实盘接口 |
| 风控管理 | `RiskControlManager` 六阶段钩子（init/before/day/after/bar/order） |
| 交易所模拟 | `StockExchange` / `FutureExchange` — 涨跌停、滑点、手续费、分红 |

**工作流引擎**:
- 基于 DAG 拓扑排序执行
- 前端可视化拖拽编辑器
- 40+ 内置节点（因子构建、IC 计算、ML 训练、回测、调仓等）
- 支持股票/期货/基金

**A 股规则建模**（对 Ditto 直接参考价值最高）:
- 涨跌停检测（`limit_up` / `limit_down`）
- 手数调整（A 股 100 股倍数，科创板 200 股）
- 手续费（佣金 + 印花税，最低 5 元）
- ETF 拆分处理
- 分红处理（`DividendManager`）
- 每日收盘自动撤单

**LLM 集成**:
- LLM-as-Code-Generator 模式（非 Agent）
- 3 个助手：`BacktestAssistant` / `CodeAssistant` / `FactorAssistant`
- AST 级别静态代码验证（`BaseCodeChecker`）+ 多轮自动修复（最多 10 轮）

**实盘能力**:
- CTP 接口（期货实盘，SPI 回调机制）
- Redis 发布/订阅交易路由
- QMT 实盘（规划中）

**能力评分**:

| 维度 | 分数 | 说明 |
|------|------|------|
| 策略定义 | 5 | 聚宽风格事件驱动，易上手但不可序列化 |
| 回测引擎 | 6 | 事件驱动，支持日/分钟级，涨跌停/滑点/手续费 |
| 组合构建 | 3 | 无独立组合构建器，逻辑在策略代码中 |
| 风险管理 | **7** | 六阶段钩子，支持热重载，优先级排序 |
| 实验管理 | 3 | 工作流版本管理，无参数扫描/A/B 测试 |
| 可解释性 | 5 | 交易日志 + 收益曲线，无因子归因 |
| API 产品化 | 7 | FastAPI + Web 工作台，产品化程度高 |
| 实盘能力 | **7** | CTP 完整实现，Redis 路由，内测中 |
| LLM/AI 集成 | 5 | 代码生成 + AST 验证，非决策核心 |

**与 Ditto 的借鉴价值**:
1. **六阶段风控钩子**: init/before/day/after/bar/order 的细粒度风控生命周期设计
2. **A股规则建模**: 涨跌停/手数/手续费/分红的完整实现，可直接参考
3. **可视化工作流编排**: DAG 拓扑排序执行引擎的产品化思路
4. **LLM + AST 验证闭环**: 生成→静态检查→自动修复的模式
5. **CTP 实盘对接**: 如果 Ditto 未来需要期货实盘，可参考其 CTP SPI 封装

**Ditto 应避免的设计**:
- 无类型注解、全局单例 `CoreContext._context`、`from xxx import *`
- 风控代码从 MongoDB 动态加载 `exec()` — 安全风险
- 回测/实盘代码高度耦合
- 无测试覆盖

---

### 6.3 Panda Factor — A 股因子研究平台

**定位**: 面向 A 股的开源因子研究平台，提供因子创建、计算、分析的一站式体验。

**核心架构**:

```
panda_factor/
├── generate/       ← 因子生成层（Factor ABC + FactorUtils 运算符 + FactorLoader）
├── analysis/       ← 因子分析层（IC/分层/衰减/正交化/可视化）
├── panda_data_hub/ ← 数据清洗与更新（Tushare/RQ/xtquant ETL）
├── panda_llm/      ← LLM 因子开发助手
└── panda_web/      ← 前端页面
```

**因子引擎**:

| 特性 | Panda Factor | Ditto |
|------|-------------|-------|
| 表达式引擎 | 无独立 Parser，`eval()`/`exec()` + AST 白名单 | **Pratt Parser** 完整编译管线 |
| 安全性 | AST 白名单 + `exec()`（有注入风险） | 编译时类型检查，无 eval/exec |
| 运算符数量 | ~60 个（FactorUtils 静态方法） | ~38 个注册运算符 |
| 因子定义 | 运行时 Python 类（动态加载） | **FactorSpec** immutable dataclass |
| 预定义因子库 | 无，用户自建 | **56 个**预定义因子 |
| 数据框架 | pandas | **polars** |
| PIT 支持 | 无 | **PIT 研究快照** |
| 物化模型 | 计算后直接存 MongoDB | **artifact-first 物化** |

**因子评估体系**（分析层能力较强）:
- IC 分析：IC / Rank IC / IR / t-test / p-value / P(IC>0.02)
- 分层收益：2-20 组等频分组，年化收益/超额收益/最大回撤/夏普/IR/月度胜率/跟踪误差/换手率/单调性
- 衰减分析：lag 1-20 期 IC 衰减 + ACF 自相关
- 正交化：市值中性化 / 行业中性化 / **Barra 10 因子中性化**
- 数据清洗：去极值（3-sigma / MAD）、Z-score 标准化、涨跌停/ST/退市过滤
- 可视化：matplotlib + 前端 ECharts

**LLM 集成**:
- OpenAI 兼容 API（支持 Deepseek 等国产模型）
- 系统提示词限定为"因子开发助手"，注入运算符文档
- 会话管理 + MongoDB 持久化 + SSE 流式输出
- **局限**：无因子自动生成/挖掘，LLM 与因子管线分离

**能力评分**:

| 维度 | 分数 | 说明 |
|------|------|------|
| 因子定义 | 5 | 双模式（Python + 公式），但无编译验证 |
| 因子评估 | **8** | IC/分层/衰减/正交化/可视化，较完整 |
| 因子版本管理 | 3 | MongoDB 存储，无版本对比 |
| 数据管理 | 5 | 多数据源 + 自动更新，但无 PIT |
| LLM/AI 集成 | 4 | 因子助手，但与管线分离 |
| 回测集成 | 2 | 仅分层回测，无订单/成本模型 |
| 工程质量 | 3 | 无类型检查、无测试、pandas 性能瓶颈 |

**与 Ditto 的借鉴价值**:
1. **技术指标库**: MACD/KDJ/RSI/CCI/ATR/DMI/BOLL 等 20+ 技术指标实现可作为 Ditto 因子库参考
2. **分层收益统计指标**: `df_info` 表格（年化收益/超额收益/回撤/夏普/IR/月度胜率/换手率/单调性）是较完整的单因子评估模板
3. **IC 衰减 + ACF 自相关分析**: lag 1-20 期衰减分析是实用的因子时效性工具
4. **Barra 正交化**: 10 因子逐步回归去残差的方法可作为 Ditto 正交化功能参考
5. **LLM 因子助手模式**: "限定系统提示词 + 运算符文档注入"的模式值得参考

**局限性**:
- 无独立表达式引擎，`eval()`/`exec()` 不安全
- pandas 性能瓶颈，分组换手率 O(n^2)、逐 symbol 循环
- 无 PIT、无版本控制、无 Fama-MacBeth 回归
- 无测试覆盖

---

## 7. 追加项目的综合对比

| 维度 | TradingAgents | Panda QuantFlow | Panda Factor | Ditto (当前) |
|------|:------------:|:--------------:|:-----------:|:----------:|
| **定位** | LLM 决策研究 | A股一体化平台 | A股因子研究 | 量化基础设施 |
| **策略定义** | 3 (LLM 文本) | 5 (事件驱动) | N/A | 1 (设计8.5) |
| **回测引擎** | 0 | **7** (事件驱动) | 2 (分层回测) | 0 |
| **组合构建** | 2 | 3 | N/A | 0 (设计7.5) |
| **风险管理** | 4 (LLM分析) | **7** (六阶段钩子) | N/A | 0 (设计7) |
| **因子引擎** | 0 | N/A | **8** (60+算子) | **8** (56因子) |
| **因子评估** | 0 | N/A | **8** (IC/分层/衰减) | **8** (IC/Fama-MacBeth) |
| **实验管理** | 2 | 3 | 3 | 0.5 (设计8) |
| **可解释性** | **8** (辩论记录) | 5 | 7 (可视化) | 0 (设计8.5) |
| **API产品化** | 2 | **7** | 5 | 0.5 (设计7) |
| **实盘能力** | 0 | **7** (CTP) | 0 | 0 (设计预留) |
| **LLM/AI集成** | **10** | 5 | 4 | 0 (设计3) |
| **A 股规则** | 0 | **8** (完整建模) | 6 (基础过滤) | 0 |
| **工程质量** | 5 | 3 | 3 | **8** |

### 关键洞察

1. **Panda QuantFlow 的 A 股规则建模最完整** — 涨跌停/手数/手续费/分红/ETF 拆分的实现直接可参考，是 Ditto Phase 3（执行引擎）的最佳参考
2. **Panda Factor 的因子评估体系最丰富** — Barra 正交化、IC 衰减分析、单调性检验等是 Ditto 可借鉴的分析能力
3. **TradingAgents 的 LLM 多 Agent 辩论模式** — 代表了 LLM 交易决策的前沿方向，但距离生产级交易平台差距很大
4. **Ditto 在因子引擎 + 治理体系上的工程严谨性远超这三个项目** — Pratt Parser、polars、artifact-first、PIT、类型安全都是明显优势
5. **三个项目的共同短板**：无类型检查、无测试、无版本控制 — 这正是 Ditto 工程质量优势所在

### T1 借鉴优先级

| 来源 | 借鉴内容 | 优先级 | 适用 Phase |
|------|---------|--------|-----------|
| Panda QuantFlow | A 股规则建模（涨跌停/手数/手续费/T+0/T+1） | **P0** | Phase 3 |
| Panda QuantFlow | 六阶段风控钩子设计 | **P1** | Phase 5 |
| Panda QuantFlow | LLM + AST 验证代码生成闭环 | P3 | Phase 9 |
| Panda QuantFlow | 可视化工作流编排产品思路 | P3 | Phase 7 |
| Panda Factor | 技术指标库丰富（20+ 指标实现） | **P2** | Phase 1 |
| Panda Factor | IC 衰减 + ACF 自相关分析 | **P2** | Phase 2 |
| Panda Factor | Barra 10 因子正交化 | P2 | Phase 8 |
| TradingAgents | 多角色辩论机制 | P3 | Phase 9 |
| TradingAgents | 双模型策略（推理 + 快速） | P3 | Phase 9 |
| TradingAgents | 决策链路可解释性 | P3 | Phase 7 |
