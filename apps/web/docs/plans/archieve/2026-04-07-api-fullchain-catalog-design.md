# Ditto API 全链路接口目录

> 基于 17 个原型页面 + 18 份设计规格，梳理前端所需的全部 API 端点、字段定义、数据源映射与可行性评估。

**版本**: v1.0
**日期**: 2026-04-07
**状态**: Draft

---

## 总览

| 域 | 页面数 | REST 端点 | WebSocket | 核心外部依赖 |
|---|---|---|---|---|
| Home | 1 | 8 | — | 聚合层，无直接依赖 |
| Markets | 4 | 26 | — | tushare + FRED |
| Research | 3 | 17 | — | tushare + 内部回测引擎 |
| Trading | 4 | 28 | 2 (行情+订单) | MiniQMT（核心执行） |
| AI | 3 | 19 | 1 (Agent) | LLM 服务 |
| Platform | 1 | 8 | 1 (告警) | 无外部依赖 |
| **合计** | **16** | **106** | **4** | |

### 全局高风险项

| # | 风险 | 域 | 严重度 | 建议 |
|---|------|---|--------|------|
| 1 | MiniQMT 连接稳定性 | Trading | 🔴 高 | 健康检查 + 自动重连 + 降级模式 |
| 2 | 下单链路延迟 | Trading | 🔴 高 | 异步化 + 预校验 + 缓存行情 |
| 3 | LLM 服务可用性 | AI/Markets | 🔴 高 | 多 Provider + 本地 fallback + 降级策略 |
| 4 | 回测引擎性能 | Research | 🟡 中 | 异步任务队列 + 限制并发 + 结果缓存 |
| 5 | tushare 积分/覆盖度 | Markets | 🟡 中 | 逐一验证高级接口 + 备选数据源 |
| 6 | SSE 流式传输环境 | AI | 🟡 中 | 验证部署环境 SSE 支持 |
| 7 | Agent 审批→信号联动 | AI→Trading | 🟡 中 | 事务性保证 + 失败回滚 |

---

## 1. Home 命令中心（`/`）

Home 是跨域聚合层，自身不产生数据。

### 1.1 GET /api/home/pulse

今日全局脉动。

**Response:**
```typescript
{
  date: string;           // YYYY-MM-DD
  session: 'pre_market' | 'call_auction' | 'continuous' | 'lunch' | 'close' | 'after_hours';
  pendingActions: number;  // 待处理项计数
  criticalAlerts: number;  // 严重告警计数
  runningJobs: number;     // 运行中任务计数
  pnlToday: number;        // 今日盈亏（元）
  pnlPercent: number;      // 今日盈亏百分比
}
```

**数据来源**: 后端聚合 — MiniQMT 实时持仓盈亏 + 内部信号/任务计数
**可行性**: ✅ 可行，需后端聚合计算

### 1.2 GET /api/home/decision-banner

决策横幅 — 总览 + AI 建议。

**Response:**
```typescript
{
  totalEquity: number;
  dailyPnl: number;
  dailyPnlPercent: number;
  riskUtilization: number;  // 0-100
  marketRegime: 'risk_on' | 'risk_off' | 'mixed';
  regimeType: string;       // 可读描述
  suggestion: string;       // AI 投资建议文本
}
```

**数据来源**: MiniQMT 资产 + 内部风控 + LLM
**可行性**: ✅ 可行 — `suggestion` 需 LLM 接入

### 1.3 GET /api/home/pending-actions

跨域待处理事项。

**Response:**
```typescript
{
  actions: Array<{
    id: string;
    priority: 'critical' | 'high' | 'medium' | 'low';
    title: string;
    meta: string;
    time: string;            // ISO 8601
    badge: { type: string; label: string };
    domain: 'trading' | 'research' | 'platform';
  }>;
}
```

**数据来源**: 后端跨域聚合（信号 + 订单 + 告警 + 回测）
**可行性**: ✅ 可行

### 1.4 GET /api/home/alerts

全局告警。

**Response:**
```typescript
{
  alerts: Array<{
    id: string;
    severity: 'critical' | 'warning' | 'info';
    title: string;
    desc: string;
    time: string;
  }>;
}
```

**数据来源**: 内部监控 + 风控引擎
**可行性**: ✅ 可行

### 1.5 GET /api/home/signals/recent

近期信号。

**Response:**
```typescript
{
  signals: Array<{
    ticker: string;
    action: 'BUY' | 'SELL' | 'HOLD';
    strategy: string;
    confidence: number;  // 0-100
    time: string;
  }>;
}
```

**数据来源**: 内部信号引擎
**可行性**: ✅ 可行

### 1.6 GET /api/home/agent-findings

Agent 发现摘要。

**Response:**
```typescript
{
  findings: Array<{
    text: string;
    source: string;
    icon: 'insight' | 'warning' | 'info';
  }>;
}
```

**数据来源**: AI Agent 模块
**可行性**: ✅ 可行

### 1.7 GET /api/home/data-health

数据源健康状态。

**Response:**
```typescript
{
  providers: Array<{
    label: string;
    status: 'ok' | 'warning' | 'error';
    statusText: string;
    lastUpdate: string;
  }>;
}
```

**数据来源**: 内部数据管道监控
**可行性**: ✅ 可行

### 1.8 GET /api/market/indices

市场指数快照。

**Response:**
```typescript
{
  indices: Array<{
    name: string;
    code: string;
    price: number;
    change: number;
    changePercent: number;
    dir: 'up' | 'down';
  }>;
}
```

**数据来源**: tushare 日线 + MiniQMT 实时
**可行性**: ✅ 可行

---

## 2. Markets 市场域（4 页面）

### 2.1 Cross-Market Overview（`/markets`）

#### GET /api/markets/context
**Response:** `{ regime, volatility, usdStrength, alertCount }`
**来源**: 后端计算
**可行性**: ✅

#### GET /api/markets/scope-strip
**Response:** `{ interpretation, leadingSectors[], laggingSectors[], style, events[] }`
**来源**: LLM + 行情
**可行性**: ⚠️ `interpretation` 需 LLM 实时生成

#### GET /api/markets/overview
**Response:** `{ cards[]: { name, indexCode, price, change, breadth, driver, regimeTag } }`
**来源**: tushare + 外部 API
**可行性**: ⚠️ 港股/美股/外汇/商品需确认覆盖度

#### GET /api/markets/cross-matrix
**Response:** `{ rows[]: { name, metrics: { D1, W1, M1, vol, breadth, flow } } }`
**来源**: tushare 汇总
**可行性**: ✅

#### GET /api/markets/macro-drivers
**Response:** `{ indicators[]: { name, value, change, sparkline[] } }` — DXY, US10Y, CN10Y, VIX, Gold, Oil, CNY
**来源**: FRED + tushare
**可行性**: ✅

#### GET /api/markets/capital-rotation
**Response:** `{ sectors[]: { name, inflow, outflow, netFlow, rankChange } }`
**来源**: tushare sector_money
**可行性**: ✅

#### GET /api/markets/calendar
**Response:** `{ events[]: { date, time, title, importance, country, type } }`
**来源**: tushare + 财经日历
**可行性**: ⚠️ 需确认财经日历 API

### 2.2 Markets Screener（`/markets/screener`）

#### POST /api/markets/screener/run
**Request:** `{ filters[], universe, sortBy, limit, offset }`
**Response:** `{ results[], total, facets }`
**来源**: tushare + 后端筛选
**可行性**: ✅

#### GET /api/markets/screener/presets
**Response:** `{ presets[]: { id, name, filters, builtin } }`
**来源**: 内部存储
**可行性**: ✅

#### GET /api/markets/screener/columns
**Response:** `{ columns[]: { key, label, group, sortable, defaultVisible } }`
**来源**: 内部配置
**可行性**: ✅

#### GET /api/instruments/compare
**Request:** `{ ids[] }`
**Response:** `{ instruments[]: { id, overview, technical, fundamental, risk } }`
**来源**: tushare
**可行性**: ✅

#### POST /api/universes/generate
**Request:** `{ criteria }`
**Response:** `{ universeId, name, count, constituents[] }`
**来源**: 后端选股引擎
**可行性**: ✅

### 2.3 Markets Intelligence（`/markets/intelligence`）— 5 Tab

#### GET /api/intelligence/flow
**Response:** `{ netFlows[], sectorRankings[], largeOrders[], northbound }`
**来源**: tushare
**可行性**: ✅

#### GET /api/intelligence/macro
**Response:** `{ calendar[], indicators[], yieldSpread, fx }`
**来源**: FRED + tushare
**可行性**: ✅

#### GET /api/intelligence/fundamentals
**Response:** `{ earningsCalendar[], ratingChanges[], earningsEstimates[] }`
**来源**: tushare
**可行性**: ⚠️ analyst 需足够积分

#### GET /api/intelligence/news
**Response:** `{ news[]: { id, title, summary, sentiment, source, time } }`
**来源**: tushare + LLM
**可行性**: ⚠️ 情绪标签需 LLM

#### GET /api/intelligence/network
**Response:** `{ correlationMatrix, sectorLinkage[], supplyChain[] }`
**来源**: 后端计算
**可行性**: ✅

#### GET /api/intelligence/detail/{id}
**Response**: 完整情报详情
**来源**: 多源
**可行性**: ✅

### 2.4 Instrument Hub（`/instruments/[id]`）— 8 Tab

#### GET /api/instruments/{id}
**Response:** `{ name, code, price, change, marketCap, pe, pb, industry, market, tags[], status }`
**来源**: tushare
**可行性**: ✅

#### GET /api/instruments/{id}/chart
**Request:** `{ period, interval }`
**Response:** `{ bars[]: { time, open, high, low, close, volume }, indicators }`
**来源**: tushare + 后端计算
**可行性**: ✅ — 分钟线需通达信或 MiniQMT

#### GET /api/instruments/{id}/flow
**Response:** `{ institutional[], retail[], northbound[], chipDistribution[] }`
**来源**: tushare
**可行性**: ⚠️ 筹码分布需确认数据源

#### GET /api/instruments/{id}/fundamentals
**Response:** `{ income, balance, cashflow, ratios[], dupontAnalysis, peers[] }`
**来源**: tushare
**可行性**: ✅

#### GET /api/instruments/{id}/corporate-actions
**Response:** `{ dividends[], lockupExpiry[], shareholderChanges[], institutionalHoldings[] }`
**来源**: tushare
**可行性**: ✅

#### GET /api/instruments/{id}/news
**Response:** `{ news[]: { id, title, summary, sentiment, time } }`
**来源**: tushare + LLM
**可行性**: ⚠️ AI 摘要需 LLM

#### GET /api/instruments/{id}/network
**Response:** `{ relatedInstruments[]: { id, name, relationType, strength } }`
**来源**: 后端图谱
**可行性**: ⚠️ 需自建关联数据

#### GET /api/instruments/{id}/announcements
**Response:** `{ announcements[]: { id, title, type, importance, date } }`
**来源**: tushare
**可行性**: ✅

### Markets 域风险

| 风险 | 严重度 | 说明 |
|------|--------|------|
| tushare 积分门槛 | 🟡 中 | analyst、北向资金需 >= 2000 积分 |
| 港股/美股/商品覆盖 | 🟡 中 | 非A股覆盖需逐一验证 |
| LLM 依赖 | 🟡 中 | scope-strip、新闻情绪/摘要需 LLM |
| 筹码分布数据 | 🟢 低 | tushare 无直接 API，需估算 |
| 关联图谱 | 🟡 中 | 需自建行业/概念/供应链关联 |

---

## 3. Research 研究域（3 页面）

### 3.1 Research Workspace（`/research`）

#### GET /api/research/pulse
**Response:** `{ activeFactors, degradingFactors, failedFactors, reviewQueueLength }`
**可行性**: ✅

#### GET /api/factors
**Response:** `{ factors[]: { id, name, family, ic, ir, decay, turnover, coverage, healthStatus, lastUpdated } }`
**来源**: 内部因子引擎 + tushare
**可行性**: ✅

#### GET /api/research/runs
**Response:** `{ runs[]: { id, name, type, status, startTime, endTime, keyMetric } }`
**可行性**: ✅

#### GET /api/research/experiments
**Response:** `{ experiments[]: { id, name, status, factors[], createdAt } }`
**可行性**: ✅

#### GET /api/research/review-queue
**Response:** `{ items[]: { id, type, name, status, submittedAt } }`
**可行性**: ✅

#### POST /api/backtest
**Request:** `{ strategyId, universe, startDate, endDate, benchmark, initialCapital, costModel }`
**Response:** `{ jobId }` (异步)
**可行性**: ✅

#### GET /api/backtest/{jobId}
**Response:** `{ status, progress, navSeries[], holdings[], trades[], monthlyReturns[], statistics: { sharpe, mdd, sortino, calmar, winRate, plRatio, turnover } }`
**可行性**: ✅

### 3.2 Strategy Studio（`/research/strategies/[id]/studio`）

#### GET /api/strategies/{id}
**Response:** `{ id, name, version, mode, status, factors[], pipeline, universe, weightConfig, riskRules[], code, savedAt }`
**可行性**: ✅

#### PUT /api/strategies/{id}
**Request:** 同上结构（部分更新）
**可行性**: ✅

#### POST /api/strategies/{id}/validate
**Request:** `{ code | pipeline }`
**Response:** `{ valid, errors[], warnings[] }`
**可行性**: ✅

#### POST /api/strategies/{id}/dry-run
**Request:** `{ strategy, universe, period }`
**Response:** `{ previewResults, warnings[] }`
**可行性**: ✅

#### GET /api/strategies/{id}/versions
**Response:** `{ versions[]: { version, code, savedAt, changeNote } }`
**可行性**: ✅

#### GET /api/factors/library
**Response:** `{ factors[]: { id, name, family, description, source, preprocessorOptions[] } }`
**可行性**: ✅

### 3.3 Regime Monitor（`/research/regime`）

#### GET /api/regime/current
**Response:** `{ state, confidence, duration, keyIndicators[] }`
**可行性**: ✅ — 需实现 regime 判定模型

#### GET /api/regime/drivers
**Response:** `{ drivers[]: { name, value, trend, impact } }`
**可行性**: ✅

#### GET /api/regime/history
**Response:** `{ switches[]: { date, fromState, toState, trigger, confidence } }`
**可行性**: ✅

#### GET /api/regime/strategy-impact
**Response:** `{ strategies[]: { id, name, performance, adjustmentSuggestion } }`
**可行性**: ✅

### Research 域风险

| 风险 | 严重度 | 说明 |
|------|--------|------|
| 回测引擎性能 | 🟡 中 | 全量回测计算密集，需异步 + 进度推送 |
| Regime 模型 | 🟡 中 | 需自研或接入现成模型 |
| 因子库构建 | 🟡 中 | 大量历史数据预计算，冷启动慢 |

---

## 4. Trading 交易域（4 页面）

### 4.1 Trading Overview（`/trading`）

#### GET /api/trading/session
**Response:** `{ phase, cashBalance, margin, riskBudget, routeHealth, marginData }`
**来源**: MiniQMT query_account
**可行性**: ✅

#### GET /api/trading/equity
**Request:** `{ timeframe }`
**Response:** `{ series[]: { time, equity, pnl, pnlPercent } }`
**可行性**: ✅

#### GET /api/trading/positions
**Response:** `{ positions[]: { code, name, qty, availableQty, avgCost, currentPrice, pnl, pnlPercent, weight, frozenQty } }`
**来源**: MiniQMT query_positions
**可行性**: ✅ — frozenQty 需后端计算

#### GET /api/trading/risk/summary
**Response:** `{ var, maxDD, beta, grossExposure, netExposure, nearLimit, breachCount }`
**可行性**: ✅

#### GET /api/trading/signals/queue
**Response:** `{ pending, confirmed, ignored, ordered }`
**可行性**: ✅

#### GET /api/trading/orders/summary
**Response:** `{ pending, submitted, partial, filled, failed }`
**可行性**: ✅

#### GET /api/trading/attribution
**Response:** `{ sectors[], stocks[], factors[] }`
**可行性**: ⚠️ 需自研归因模型

#### GET /api/trading/health-check
**Response:** `{ checks[]: { name, status, detail } }`
**可行性**: ✅

#### POST /api/trading/pause
**Request:** `{ reason }`
**可行性**: ✅

### 4.2 Signals Inbox（`/trading/signals`）

#### GET /api/signals
**Request:** `{ tab, page, limit }`
**Response:** `{ signals[]: { id, time, instrument, source, direction, weight, confidence, status, limitUpDownCheck } }`
**可行性**: ✅

#### GET /api/signals/{id}
**Response:** `{ explanation, riskChecks[], portfolioImpact, actions[] }`
**可行性**: ✅

#### POST /api/signals/{id}/confirm
**Response:** `{ orderId }`
**可行性**: ✅

#### POST /api/signals/{id}/ignore
**Request:** `{ reason }`
**可行性**: ✅

#### POST /api/signals/batch-confirm
**Request:** `{ signalIds[] }`
**可行性**: ✅

#### POST /api/orders/validate
**Request:** `{ instrument, side, qty, price, type }`
**Response:** `{ valid, instrumentStatus, estimatedFee, warnings[] }`
**可行性**: ✅

#### POST /api/orders/submit
**Request:** `{ instrument, side, qty, price, type, signalId? }`
**Response:** `{ orderId, status }`
**来源**: MiniQMT order_stock
**可行性**: ✅

#### GET /api/signals/{id}/ai-interpretation
**Response:** `{ interpretation, similarHistory[], riskAssessment }`
**可行性**: ⚠️ 需 LLM

### 4.3 Orders / Execution Ledger（`/trading/orders`）

#### GET /api/orders
**Request:** `{ tab, page, limit, sort }`
**Response:** `{ orders[]: { id, instrument, side, qty, price, filledQty, type, status, account, createdAt, updatedAt } }`
**可行性**: ✅

#### GET /api/orders/{id}
**Response:** 完整订单 + trace[], rejectReason?, fees, slippage, routeLog[]
**可行性**: ✅

#### POST /api/orders/{id}/cancel
**可行性**: ✅

#### POST /api/orders/{id}/retry
**可行性**: ✅

### 4.4 Risk Center（`/trading/risk`）

#### GET /api/risk/var
**Response:** `{ series[]: { date, var95, var99 } }`
**可行性**: ✅

#### GET /api/risk/drawdown
**Response:** `{ series[]: { date, drawdown, maxDD } }`
**可行性**: ✅

#### GET /api/risk/exposure
**Response:** `{ grossExposure, netExposure, bySector[], byStyle[], byFactor[] }`
**可行性**: ✅

#### GET /api/risk/breaches
**Response:** `{ breaches[]: { id, ruleName, currentValue, threshold, deviation, affectedPositions[], status } }`
**可行性**: ✅

#### POST /api/risk/stress-test
**Request:** `{ scenario, positions? }`
**Response:** `{ scenario, impactPnl, maxLoss, affectedPositions[] }`
**可行性**: ✅

#### GET /api/risk/incidents
**Response:** `{ incidents[]: { id, severity, status, handler, resolution, createdAt } }`
**可行性**: ✅

#### PUT /api/risk/rules/{id}
**Request:** `{ threshold, action, enabled }`
**可行性**: ✅

### Trading 域风险

| 风险 | 严重度 | 说明 |
|------|--------|------|
| MiniQMT 连接稳定性 | 🔴 高 | 依赖本地进程 + QMT 客户端 |
| 下单延迟 | 🔴 高 | 信号→校验→下单链路需 < 3s |
| 归因分析 | 🟡 中 | Brinson 多因子归因需预研 |
| T+1 冻结量 | 🟢 低 | 后端维护规则表 |
| AI 信号解读 | 🟢 低 | 可异步化 |

---

## 5. AI 智能域（3 页面）

### 5.1 AI Overview（`/ai`）

#### GET /api/ai/pulse
**Response:** `{ runningPlans, pendingApprovals, activeCopilotSessions }`
**可行性**: ✅

#### GET /api/ai/agent/quick-view
**Response:** `{ plans[], recentFindings[], recentCompleted[] }`
**可行性**: ✅

#### GET /api/ai/copilot/quick-view
**Response:** `{ sessions[], recentOutputs[], savedNotes[] }`
**可行性**: ✅

### 5.2 AI Copilot（`/ai/copilot`）

#### POST /api/ai/copilot/chat (SSE)
**Request:** `{ sessionId?, mode, message, context? }`
**Response:** SSE stream — `{ delta, structuredOutput? }`
**来源**: LLM 服务
**可行性**: ✅ — 需 SSE 支持

#### GET /api/ai/copilot/sessions
**可行性**: ✅

#### POST /api/ai/copilot/sessions
**可行性**: ✅

#### GET /api/ai/copilot/sessions/{id}
**可行性**: ✅

#### POST /api/ai/copilot/notes
**可行性**: ✅

#### POST /api/ai/copilot/send-to-workspace
**可行性**: ✅

#### POST /api/ai/factor-discovery/hypothesis
**Request:** `{ description }`
**Response:** `{ hypothesis: { name, logic, dataSource, validationMethod } }`
**可行性**: ✅ — 需 LLM 结构化输出

### 5.3 Agent Console（`/ai/agent`）

#### GET /api/agent/plans
#### POST /api/agent/plans
#### GET /api/agent/plans/{id}
#### GET /api/agent/runs
#### POST /api/agent/runs/{id}/rerun
#### GET /api/agent/findings
#### POST /api/agent/findings/{id}/approve  ← 审批通过自动生成信号
#### POST /api/agent/findings/{id}/reject
#### GET /api/agent/findings/{id}/trace

全部 **可行性**: ✅

### AI 域风险

| 风险 | 严重度 | 说明 |
|------|--------|------|
| LLM 服务稳定性 | 🔴 高 | 需容错 + 降级 |
| SSE 流式传输 | 🟡 中 | 需验证部署环境 |
| Agent 执行时长 | 🟡 中 | 需 WebSocket 推送状态 |
| 审批→信号联动 | 🟡 中 | 事务性保证 |
| 结构化输出可靠性 | 🟢 低 | 需 schema 校验 |

---

## 6. Platform 运维域（1 页面）

#### GET /api/platform/health
**Response:** `{ freshness, completeness, accuracy, jobsStatus }`
**可行性**: ✅

#### GET /api/platform/providers
**Response:** `{ providers[]: { name, status, latency, missingRate, anomalyRate, lastSync, endpoint[] } }`
**可行性**: ✅

#### GET /api/platform/pipelines
#### GET /api/platform/pipelines/{id}/runs
#### GET /api/platform/alerts
#### GET /api/platform/resources
#### POST /api/platform/alerts/{id}/handle
#### POST /api/platform/pipelines/{id}/rerun

全部 **可行性**: ✅，无外部依赖。

---

## 7. WebSocket 实时通道

| 频道 | 路径 | 频率 | 消息格式 | 来源 |
|------|------|------|---------|------|
| 行情推送 | `/ws/quotes` | 3s（盘中） | `{ code, price, change, volume, bid, ask }` | MiniQMT |
| 订单状态 | `/ws/orders` | 事件驱动 | `{ orderId, status, filledQty, avgPrice }` | MiniQMT |
| Agent 状态 | `/ws/agent` | 事件驱动 | `{ runId, stage, progress, finding? }` | 后端引擎 |
| 系统告警 | `/ws/alerts` | 事件驱动 | `{ id, severity, title }` | 内部监控 |

---

## 8. 数据源能力矩阵

| 数据源 | 类型 | 关键能力 | 频率限制 | 限制 |
|--------|------|---------|---------|------|
| **tushare** | REST | A股日线/分钟/财务/北向/板块资金/新闻 | 200 req/min（基础） | 高级接口需 >= 2000 积分 |
| **MiniQMT** | Python SDK | L1实时行情(3s) + 下单/撤单 + 持仓查询 | 无限（本地） | 依赖本地 QMT 客户端运行 |
| **通达信** | 数据文件 | 历史分钟线 + 日线交叉验证 | 无限（本地） | 无官方 API，需解析数据文件 |
| **FRED** | REST | 美国及全球宏观经济指标 | 120 req/min（无需key） | 覆盖范围限于美国/全球宏观 |
| **LLM** | REST/SSE | 对话/摘要/情绪分析/结构化输出 | 取决于 Provider | 服务可用性 + 成本 |

---

## 9. 建议实施分阶段

### Phase 1: 基础数据层（只读）
- Platform 全部端点
- Home 聚合端点
- Markets 基础行情 + Instrument Hub 核心 Tab
- Trading 只读端点（positions, equity, orders 查询）

### Phase 2: 交互层
- Screener 筛选引擎
- Signals 信号确认/忽略
- Orders 下单/撤单
- Research 回测提交与结果

### Phase 3: 智能层
- AI Copilot 对话（SSE）
- Agent 计划/运行/审批
- Regime 判定模型
- 归因分析

### Phase 4: 实时层
- WebSocket 行情推送
- WebSocket 订单状态
- Agent 运行状态推送
- 系统告警推送
