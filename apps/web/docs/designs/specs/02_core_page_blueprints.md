# Ditto 核心页面蓝图

> **版本**：v1.0
> **日期**：2026-03-28
> **状态**：Final
> **上游**：[01 产品信息架构](./01_product_information_architecture.md)
> **下游**：[03 对象页统一规范](./03_object_hub_spec.md)、[04 交互与状态规范](./04_interaction_state_spec.md)
> **职责**：15 个核心页面模板——目标、主辅工作面、关键区块、主 CTA、wireframe

---

## 文档目标

本文件只定义 Ditto v1 的核心页面模板，不覆盖所有路由。

它的目标是让设计、AICoding、前端实现围绕少量高价值页面模板推进，而不是按全部页面平均发力。

本文件解决四件事：

- 每个核心页面到底要解决什么问题
- 页面主工作面是什么
- 辅工作面是什么
- 页面默认信息顺序和主要 CTA 是什么

本文件是 UI 设计和代码实现的直接输入。

---

## 1. Home Command Center

### 页面目标

让用户登录后 5 秒内知道：

- 今天整体怎么样
- 有没有必须处理的
- 市场当前状态如何
- 下一步该去哪个工作区

### 页面角色

Global Command Center

### 主工作面

Pending / Next Actions

### 辅工作面

Alerts / Market Snapshot / Recent Findings

### 默认信息顺序

Today Pulse → Decision Banner → Pending → Alerts → Recent Signals / Runs → Agent Findings → My Workspace

### 核心区块

- Global Header
- Today Pulse
- Decision Banner
- Pending / Next Actions
- Alerts / Market Snapshot
- Recent Signals / Runs
- Agent Findings / Data Health
- My Workspace

### 主 CTA

- 查看信号
- 发起订单复核
- 编辑工作台

### 主要跳转

- 待处理 → Signals / Orders / Alerts / Approvals
- 市场快照 → Markets Overview
- 最近回测 → Backtest Result
- Agent Findings → AI / Agent

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Global Header: search / env / alerts / time                  │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Today Pulse: pnl / risk / regime / pending / jobs            │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Decision Banner: total assets | today pnl | risk | advice    │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Pending / Next Actions        │ Alerts / Market Snapshot      │
│      ├───────────────────────────────┼───────────────────────────────┤
│      │ Recent Signals / Runs         │ Agent Findings / Data Health  │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ My Workspace: customizable widgets                            │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 2. 全市场总览（Cross-Market Overview）

> **路由**：`/markets`
> **详细设计**：[全市场总览设计文档](../../plans/2026-03-29-cross-market-overview-design.md)

### 页面目标

让用户进入 Markets 域后 5 秒内回答：

1. 今天全球总体是 Risk-On 还是 Risk-Off
2. 哪些市场 / 资产类别最强，哪些最弱
3. 驱动当前市场分化的核心变量是什么
4. 哪些市场值得我点进去继续看
5. 接下来 24 小时有什么重要事件会改变格局

### 页面角色

Analytical Shell / Radar Variant（扫描 / 比较 / 下钻）

### 核心动词

scan → compare → choose where to drill down

### 主工作面

Cross-Market Cards（6 宫格平权比较） + Cross-Market Matrix（热力矩阵）

### 辅工作面

Right Rail（市场脉搏 / 风险预警 / 关键事件 / 推荐下钻）

### 默认信息顺序

Context Bar → Scope Strip → Market Cards → Matrix → Macro Drivers → Bottom Tabs

### 核心区块

- Workspace Header（标题 / 时间框架 / 刷新时间 / 视图密度）
- Context Bar（全局环境：Universe / Session / Regime / Volatility / Dollar / Alerts）
- Scope Strip（今日解读：强势 / 承压 / 风格 / 风险事件）
- Cross-Market Card Grid（6 卡片：A股 / 港股 / 美股 / 利率 / 外汇 / 商品）
- Cross-Market Matrix（行：市场，列：1D / 1W / 1M / Vol / Breadth / Flow）
- Macro Drivers Bar（DXY / US10Y / CN10Y / VIX / Gold / Oil / CNY）
- Right Rail（市场脉搏 / 风险预警 / 关键事件 / 推荐下钻）
- Bottom Tab Band（资金轮动 / 事件日历 / AI 解读）

### 主 CTA

- 进入 A 股总览
- 进入港股总览
- 进入美股总览
- 查看事件详情
- 固定视角
- 加入观察

### 主要跳转

- Market Card → 单市场总览页（`/markets/a-shares`、`/markets/hk` 等）
- Matrix 行 → 对应单市场总览页
- Right Rail 推荐下钻 → 动态推荐的单市场页
- 事件日历条目 → 事件详情
- AI 解读 → 对应单市场页

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Markets / 全市场总览                       [1D] [09:46 CST]   │
│      ├───────────────────────────────────────────────────────────────┤
│      │ GLOBAL | SESSION Mixed | REGIME Mild Risk-On | VOL 回落 | A2  │
│      ├───────────────────────────────────────────────────────────────┤
│      │ 强势：港股科技/黄金 | 承压：美元/长债 | 风险事件：FOMC-1D     │
│      ├─────────────────────────────────┬─────────────────────────────┤
│      │ 中国A股   港股     美股          │ 市场脉搏摘要               │
│      │ 利率     外汇     商品/黄金      │ 风险与预警                  │
│      ├─────────────────────────────────┤ 关键事件                    │
│      │ Cross-Market Matrix             │ 推荐下钻                    │
│      ├─────────────────────────────────┤                             │
│      │ Macro Drivers Bar               │                             │
│      ├─────────────────────────────────┴─────────────────────────────┤
│      │ [资金轮动] [事件日历] [AI 解读]                                 │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 2.1 中国 A 股总览

> **路由**：`/markets/a-shares`
> **说明**：从原 `/markets`（Markets Overview）迁入，聚焦 A 股内部结构扫描。

### 页面目标

作为 A 股单市场入口，先看 A 股整体结构，再决定看哪个行业、哪个标的。

### 页面角色

Analytical Shell / Radar Variant（结构扫描 / 下钻）

### 核心动词

structure scan → drill down to instrument

### 主工作面

Market Structure Map（treemap / heatmap）

### 辅工作面

Index Summary / ETF Matrix / Movers

### 默认信息顺序

Context → Scope → Market Structure → Breadth → ETF → Movers → Intelligence Links

### 核心区块

- A-Share Header（标题 / 板块选择 / 时间框架）
- Context Bar（A 股本地变量：Regime / Breadth / 北向 / 涨跌比）
- Scope Strip（A 股今日解读：强势板块 / 承压板块 / 主线 / 预警）
- Market Structure Map（treemap / heatmap，按行业 / 概念分组）
- Index Summary（沪深300 / 中证500 / 中证1000 / 创业板指）
- ETF Matrix（核心 ETF 表现）
- Movers / Main Theme Activity

### 主 CTA

- 加入观察
- 固定当前视角
- AI 解读

### 主要跳转

- Map 节点 → Instrument Hub / Intelligence
- ETF → Instrument Hub
- Movers → Intelligence / Watchlist

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ 中国 A 股总览                             [1D] [09:46 CST]   │
│      ├───────────────────────────────────────────────────────────────┤
│      │ REGIME Risk-On | BREADTH 偏强 | 北向 +12亿 | ALERTS 1       │
│      ├───────────────────────────────────────────────────────────────┤
│      │ 强势：AI/半导体 | 承压：地产/银行 | 主线：科技扩散 | FOMC-1D  │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Market Structure Map          │ Index Summary                 │
│      │ treemap / heatmap             ├───────────────────────────────┤
│      │                               │ ETF Matrix                    │
│      │                               ├───────────────────────────────┤
│      │                               │ Movers / Main Theme Activity  │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Bottom band: flows / calendar / intelligence links           │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 3. Markets Screener

### 页面目标

完成对象发现、候选集构建、多维比较和结果沉淀。

### 页面角色

Catalog / Screener Workspace

### 主工作面

Results Table

### 辅工作面

Filters / Actions / Compare Drawer

### 默认信息顺序

Toolbar → Filters → Results → Actions → Compare

### 核心区块

- Header + Saved Views
- Toolbar
- Filters
- Results Table
- Scoring / Presets
- Compare Cart
- Result Destinations
- Compare Drawer

### 主 CTA

- 运行筛选
- 保存预设
- 生成标的池
- 加入观察

### 主要跳转

- 结果行 → Instrument Hub
- Compare → Compare Drawer
- 结果去向 → Universe / Watchlist / Copilot / Strategy Studio

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Screener Header: saved views / run / reset / export          │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Toolbar: asset | market | universe | date | regime | search  │
│      ├───────────────┬───────────────────────────────┬──────────────┤
│      │ Filters       │ Results Table                 │ Actions      │
│      │ condition     │ symbol/name/sector/...score   │ presets      │
│      │ groups        │ sort / columns / virtual      │ scoring      │
│      │ exclusions    │                               │ compare cart │
│      │               │                               │ destinations │
│      ├───────────────┴───────────────────────────────┴──────────────┤
│      │ Compare Drawer: overview / technical / fundamentals / risk   │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 4. Instrument Hub

### 页面目标

围绕单标的形成完整对象中心。

### 页面角色

Object Hub

### 主工作面

当前 tab 对应的主对象视图

### 辅工作面

Related / Signals / Notes

### 默认 tab

概览 → 行情 → 态势 → 基本面 → 新闻 → 关联网络 → 公告

### 核心区块

- Object Header
- Meta Strip
- Tabs
- Main Object View
- Related / Signals / Notes
- Timeline / Filings / Linked Research

### 主 CTA

- 加入观察
- 加入标的池
- 发送到研究
- 打开 Chart Lab

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Object Header: name/code/price/status/actions                │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Meta Strip: industry / market / tags / watch / pools         │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Tabs: overview | chart | flow | fundamentals | news | net    │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Object View              │ Related / Signals / Notes     │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Timeline / filings / linked research                          │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 5. Research Workspace

### 页面目标

研究域入口，优先感知因子健康、最近运行结果和待审事项。

### 页面角色

Analytical Overview Workspace

### 主工作面

Factor Monitor Table

### 辅工作面

Recent Runs / Experiments / Review Queue

### 默认信息顺序

Pulse → Factor Monitor → Recent Runs → Review Queue → Analysis Band

### 核心区块

- Research Header
- Pulse Strip
- Factor Monitor Table
- Recent Runs
- Experiments / Review Queue
- Analysis Band

### 主 CTA

- 新建回测
- 新建实验
- 进入因子分析

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Research Header: command / saved view / new / backtest       │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Pulse: active factors / degrading / failed / queue           │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Factor Monitor Table          │ Recent Runs                   │
│      │                               ├───────────────────────────────┤
│      │                               │ Experiments / Review Queue    │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Analysis Band: IC trend / breadth / corr / notes             │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 6. Factor Analysis

### 页面目标

围绕单因子做多维诊断与研究判断。

### 页面角色

Object Hub

### 主工作面

2x2 Diagnostics

### 辅工作面

Stats / Correlation / Notes

### 默认 tab

IC → 收益 → 分布与相关 → 换手

### 核心区块

- Factor Header
- KPI Strip
- Tabs
- 2x2 Diagnostics
- Bottom Detail Area

### 主 CTA

- 加入回测
- 加入实验
- 发送 AI 解读

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Factor Header: name/family/status/actions                    │
│      ├───────────────────────────────────────────────────────────────┤
│      │ KPI Strip: IC / IR / decay / turnover / coverage             │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Tabs: IC | returns | dist/corr | turnover                    │
│      ├───────────────────────────────────────────────────────────────┤
│      │ 2x2 Diagnostics: series / dist / decay / heat                │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Bottom: stats table / corr matrix / notes                    │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 7. Strategy Studio

### 页面目标

统一策略构建、编辑、校验和提交回测。

### 页面角色

Studio / Builder

### 主工作面

Main Studio

### 辅工作面

Inspector / AI Assistant / Logs

### 模式

- Form Builder
- Code Editor

### 核心区块

- Studio Header
- Mode Switch
- Snippets / Sources
- Main Studio
- Inspector
- Logs / Validate / Dry Run

### 主 CTA

- 保存
- 校验
- Dry Run
- 提交回测

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Strategy Studio Header: save / validate / dry run / backtest │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Mode: Form Builder | Code Editor                             │
│      ├───────────────┬───────────────────────────────┬──────────────┤
│      │ Snippets      │ Main Studio                   │ Inspector    │
│      │ factors       │ form panels or monaco         │ AI assistant │
│      │ universe      │                               │ warnings     │
│      │ risk rules    │                               │ suggestions  │
│      ├───────────────┴───────────────────────────────┴──────────────┤
│      │ Logs / compile / validate / dry run                          │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 8. Backtest Result

### 页面目标

作为单次回测的完整对象中心。

### 页面角色

Object Hub

### 主工作面

NAV + Drawdown

### 辅工作面

Stats / Trades / Attribution / Diagnostics

### 默认 tab

概览 → 收益 → 风险 → 交易 → 归因 → 诊断

### 核心区块

- Backtest Header
- KPI Strip
- Tabs
- Main Charts
- Bottom Area

### 主 CTA

- 导出报告
- 加入对比
- 发送 AI 解读

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Backtest Header: run/strategy/version/actions                │
│      ├───────────────────────────────────────────────────────────────┤
│      │ KPI Strip: sharpe / annual / mdd / win / turnover / fees     │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Tabs: overview | returns | risk | trades | attribution | diag│
│      ├───────────────────────────────────────────────────────────────┤
│      │ Main Charts: NAV + drawdown                                  │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Bottom area: stats / trades / attribution / diagnostics      │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 9. Trading Overview

### 页面目标

实盘控制中心，连接资金、仓位、信号、订单和风险。

### 页面角色

Analytical Overview Workspace

### 主工作面

Equity / PnL

### 辅工作面

Risk / Alerts / Signal Queue

### 默认信息顺序

Session → Equity → Risk → Positions → Signals → Orders / Recent Trades

### 核心区块

- Trading Header
- Session Strip
- Equity / PnL
- Risk / Alerts
- Positions Summary
- Signal Queue
- Order Status
- Recent Trades / Exceptions

### 主 CTA

- 查看信号
- 查看持仓
- 暂停交易

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Trading Header: account / broker / session / pause trading   │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Session Strip: cash / margin / risk budget / route health    │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Equity / PnL                  │ Risk / Alerts                 │
│      ├───────────────────────────────┼───────────────────────────────┤
│      │ Positions Summary             │ Signal Queue                  │
│      ├───────────────────────────────┼───────────────────────────────┤
│      │ Order Status                  │ Recent Trades / Exceptions    │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

---

## 10. Signals Inbox

### 页面目标

统一信号复核层。

### 页面角色

Queue / Ops Console

### 主工作面

Signal Table

### 辅工作面

Signal Detail / Actions

### 默认 tab

待复核 → 已确认 → 已忽略 → 已转订单

### 核心区块

- Signals Header
- Scope Strip
- Signal Table
- Signal Detail

### 主 CTA

- 确认
- 生成订单复核
- 交给 AI 解读

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Signals Header: source / status / priority / portfolio       │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope Strip: pending / confirmed / ignored / ordered         │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Signal Table                  │ Signal Detail                 │
│      │ time/object/source/type       │ explanation                   │
│      │ side/weight/confidence/status │ risk checks                   │
│      │                               │ portfolio impact              │
│      │                               │ actions                       │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

---

## 11. Orders / Execution Ledger

### 页面目标

订单全生命周期与执行追踪。

### 页面角色

Ledger / Execution Console

### 主工作面

Orders Ledger Table

### 辅工作面

Order Trace

### 默认 tab

待提交 → 已提交 → 部分成交 → 已完成 → 失败 / 已撤单

### 核心区块

- Orders Header
- Status Strip
- Orders Ledger Table
- Order Trace

### 主 CTA

- 提交
- 撤单
- 重试

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Orders Header: session / account / route / filters           │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Strip: pending / submitted / partial / done / failed         │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Orders Ledger Table           │ Order Trace                   │
│      │ id/object/side/qty/price      │ status timeline               │
│      │ type/status/account/time       │ reject reason                 │
│      │                               │ fees / slippage / route log   │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

---

## 12. Risk Center

### 页面目标

实时风险主控制台。

### 页面角色

Analytical Overview Workspace

### 主工作面

Main Risk Charts

### 辅工作面

Breaches / Stress Summary

### 默认信息顺序

Risk Strip → Main Charts → Active Breaches → Stress Summary → Incident Timeline

### 核心区块

- Risk Header
- Risk Strip
- Main Risk Charts
- Active Breaches
- Stress Test Summary
- Incident Timeline

### 主 CTA

- 运行测试
- 查看事件
- 调整规则

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Risk Header: portfolio / scenario / refresh / rules          │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Strip: var / dd / beta / gross / net / near-limit / breach   │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Risk Charts              │ Active Breaches               │
│      │ var/dd/exposure timeline      ├───────────────────────────────┤
│      │                               │ Stress Test Summary           │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Incident Timeline / handling log                              │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 13. AI Copilot Studio

### 页面目标

统一 AI 市场分析、AI 选股、AI 策略草案的工作台。

### 页面角色

Studio / Builder

### 模式

- Market Analysis
- Stock Discovery
- Strategy Draft

### 主工作面

Conversation + Structured Output

### 辅工作面

Context / Evidence / Actions

### 核心区块

- Copilot Header
- Mode Switch
- Sessions
- Conversation + Structured Output
- Context

### 主 CTA

- 新建对话
- 保存结论
- 发送到目标工作区

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Copilot Header: new chat / save note / export / send         │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Mode: Market Analysis | Stock Discovery | Strategy Draft     │
│      ├───────────────┬───────────────────────────────┬──────────────┤
│      │ Sessions      │ Conversation + Structured Out │ Context      │
│      │ templates     │                               │ objects       │
│      │ history       │                               │ evidence      │
│      │ saved notes   │                               │ actions       │
└──────┴───────────────┴───────────────────────────────┴──────────────┘
```

---

## 14. Agent Console

### 页面目标

管理 Plan、Run、Finding、Approval 的完整 agent 工作流。

### 页面角色

Studio / Builder

### 默认 tab

Plans → Runs → Findings → Approvals

### 主工作面

Main Queue / Cards

### 辅工作面

Detail / Tool Trace

### 核心区块

- Agent Header
- Tabs
- Main Queue / Cards
- Detail / Tool Trace

### 主 CTA

- 新建 Plan
- 暂停
- 重跑
- 提交审批

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Agent Header: new plan / pause / rerun / approve             │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Tabs: plans | runs | findings | approvals                    │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Queue / Cards            │ Detail / Tool Trace          │
│      │ plans or runs or findings     │ output / approval / logs     │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

---

## 15. Platform Ops Console

### 页面目标

平台健康、任务、数据质量与异常处理的统一控制台。

### 页面角色

Queue / Ops Console

### 主工作面

Data Providers / DQ + Pipelines / Jobs

### 辅工作面

System Alerts / Resources / Logs

### 核心区块

- Platform Header
- Health Strip
- Data Providers / DQ
- Pipelines / Jobs
- System Alerts
- Resources / Quotas
- Logs / Incident History

### 主 CTA

- 刷新
- 处理异常
- 查看任务

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Platform Header: env / refresh / incidents / settings        │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Health Strip: freshness / completeness / accuracy / jobs     │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Data Providers / DQ           │ Pipelines / Jobs             │
│      ├───────────────────────────────┼───────────────────────────────┤
│      │ System Alerts                 │ Resources / Quotas           │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Logs / incident history                                      │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 页面优先级

### 第一批先设计

- Home Command Center
- Markets Overview
- Markets Screener
- Research Workspace
- Trading Overview
- Platform Ops Console

### 第二批

- Instrument Hub
- Strategy Studio
- Backtest Result
- Signals Inbox

### 第三批

- Orders / Execution Ledger
- Risk Center
- AI Copilot Studio
- Agent Console

## Changelog

### 2026-03-30 — Cross-Market Review R10-R12 Sync

- **[修正]** Cross-Market Matrix 列名"资金面"→"态势"（来源: FIX-03，R10）
- **[新增]** Heat map 5 级 alpha 梯度规范: 0.05/0.10/0.17（R12 收敛值，来源: FIX-04）
- **[新增]** Ambient tint alpha 标准: card 0.06, row 0.05（来源: FIX-08）
- **[新增]** Sparkline opacity 标准: 0.6, stroke-width 1.5px（来源: FIX-07）
- **[新增]** LIVE 状态指示器: 同源绿色 oklch(0.72 0.19 155)，替代"实时"（来源: COPY-09）
- **[新增]** kbd 幽灵键帽: font-mono 10px, border oklch(1 0 0 / 0.10), bg oklch(1 0 0 / 0.04)（来源: FIX-10/COPY-10）
- **[新增]** context-bar 信息层级: 核心(regime color-mix 85%) > 标准(text-secondary) > 辅助(text-tertiary)（来源: R12 FIX-1）
- **[新增]** card-change 字号 14px→13px，归入 5 级字号 scale (10/12/13/16/24)（来源: FIX-09）
