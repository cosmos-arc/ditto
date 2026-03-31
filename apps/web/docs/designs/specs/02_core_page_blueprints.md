# Ditto 核心页面蓝图

> **版本**：v1.2
> **日期**：2026-03-31
> **状态**：Final
> **上游**：[01 产品信息架构](./01_product_information_architecture.md)
> **下游**：[03 对象页统一规范](./03_object_hub_spec.md)、[04 交互与状态规范](./04_interaction_state_spec.md)
> **职责**：17 个页面模板——目标、主辅工作面、关键区块、主 CTA、wireframe

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
- Right Rail（市场脉搏 / 风险预警 / 关键事件 / 推荐下钻 / 北向资金深度面板 / 快捷入口: Chart Lab / Calendar）
- Bottom Tab Band: 资金轮动 / 龙虎榜 / 两融数据 / 事件日历

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
- Bottom Tab Band: 资金轮动 / 龙虎榜 / 两融数据 / 事件日历

### 主 CTA

- 加入观察
- 固定当前视角
- AI 解读

### 主要跳转

- Map 节点 → Instrument Hub / Intelligence
- ETF → Instrument Hub
- Movers → Intelligence / Watchlist

### Right Rail — 北向资金深度面板

北向资金不仅显示单数字"北向 +12亿"，而是在 Right Rail 中提供深度面板：

- 分时净流入曲线（当日分钟级）
- 沪股通 / 深股通分别展示
- 北向持仓 Top10 变动（增持/减持数量）
- 行业偏好分析（北向近期净买入的行业）

> **注意**: 北向资金实时数据需 Level-1 行情权限，盘中延迟约 15 分钟。

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
│      │ [资金轮动] [龙虎榜] [两融数据] [事件日历]                         │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 2.2 情报中心（Markets Intelligence）

> **路由**：`/markets/intelligence`
> **Pattern**: Analytical Overview Workspace（tab 视图）

### 页面目标

多源市场情报聚合工作区，收敛原 5 个子路由（flow/macro/fundamental/news/network）为 tab 视图，让用户在一个页面内快速切换不同视角的情报分析。

### 页面角色

Analytical Overview Workspace

### 核心动词

scan → filter → drill down

### 主工作面

当前激活 tab 的情报视图

### 辅工作面

Right Rail（关联标的 / 快捷筛选 / 时间范围）

### 默认 tab

资金面 → 宏观 → 基本面 → 新闻 → 关联网络

### 核心区块

- Intelligence Header（标题 / tab 切换 / 时间范围 / 刷新）
- Tab View（每个 tab 对应一个情报维度）
- Right Rail（关联标的快览 / 筛选器 / AI 摘要）

### 主 CTA

- AI 解读
- 加入观察
- 发送到 Copilot

### 主要跳转

- 情报条目 → Instrument Hub
- AI 摘要 → Copilot
- Tab 切换 → 同页不同情报维度

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Markets Intelligence              [资金面 ▼] [1D] [09:46]    │
│      ├───────────────────────────────────────────────────────────────┤
│      │ [资金面] [宏观] [基本面] [新闻] [关联网络]                     │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Intelligence View              │ 关联标的                     │
│      │ (资金流向/宏观事件/            │ 筛选器                       │
│      │  财报数据/新闻流/网络图)       │ AI 摘要                     │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Analysis Band: trend / comparison / notes                     │
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

概览 → 行情 → 态势 → 基本面 → **公司行动** → 新闻 → 关联网络 → 公告

### 核心区块

- Object Header（含 **停牌/复牌状态标识**: 停牌时显示暂停图标 + 预计复牌日期）
- Meta Strip（含 **停牌日期 / 预计复牌日期**）
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
│      │ Object Header: name/code/price/status/suspend-flag/actions   │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Meta Strip: industry / market / tags / watch / pools / halt   │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Tabs: overview | chart | flow | fundamentals | corporate actions | news | net    │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Object View              │ Related / Signals / Notes     │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Timeline / filings / linked research                          │
└──────┴───────────────────────────────────────────────────────────────┘
```

### 公司行动 Tab（Corporate Actions）

> **v1.1 新增**：覆盖 A 股除权除息、限售解禁等公司行动信息。

展示标的相关的公司行动时间表和详情：

| 子区块 | 内容 |
|--------|------|
| 近期公司行动 | 以时间线形式展示未来 30 天内的公司行动（除权除息日/限售解禁日/股东大会） |
| 分红历史 | 历次分红的每股派息、送股、转增比例，以及除权除息日 |
| 限售解禁 | 即将解禁的限售股数量、占比、解禁日期、解禁类型（首发原股东/定增/股权激励） |
| 股东/机构持仓 | 前十大股东变动（季度）、机构持仓比例、北上资金持仓变化 |

**数据来源**：tushare 分红送转接口 + 限售解禁接口 + 股东人数接口（参见 18 数据源规格）。

---

## 4.2 Markets Calendar（轻量蓝图）

> **路由**：`/markets/calendar`
> **Pattern**: Catalog / Screener Workspace

### 页面目标

展示未来和过去的市场事件日历，帮助用户在关键时间点做出交易决策。

### 核心区块

- Calendar Header（标题 / 视图切换 / 范围筛选）
- **A 股事件日历**（v1.1 新增，以下为 A 股核心事件类型）
- 经济数据日历
- Filter Bar（事件类型 / 市场 / 重要性筛选）

### A 股事件日历内容

| 事件类型 | 说明 | 频率 | 数据来源 |
|---------|------|------|---------|
| 新股申购 | 新股发行日期、申购代码、申购价格、网上发行数量 | 不定期 | tushare new_share 接口 |
| 限售解禁 | 解禁标的、解禁数量、解禁类型、解禁市值 | 不定期 | tushare share_float 接口 |
| 期权交割日 | 沪深 300ETF 期权、中证 1000ETF 期权交割日 | 月度（第三个周五） | tushare opt_daily 接口 |
| 股指期货交割 | 沪深 300 股指期货、中证 500 股指期货、中证 1000 股指期货交割日 | 月度（第三个周五） | tushare fut_daily 接口 |
| 经济数据发布 | CPI/PPI/PMI/社融/M2 等宏观经济数据发布日期 | 月度 | tushare macro 接口 + FRED |
| 除权除息日 | 标的分红送转的除权除息日期 | 不定期 | tushare divident 接口 |
| 财报披露窗口 | 创业板/科创板业绩预告强制披露截止日 | 季度 | tushare disclosure_date 接口 |

### 主 CTA

- 查看标的详情
- 加入日历提醒
- 跳转到 Intelligence（相关事件分析）

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
- 新建策略
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
- **因子预处理管道**（Form Mode 下，因子选择后的预处理步骤）

### 因子预处理管道

在 Form Mode 中，当用户选择因子后，自动展示预处理配置面板。预处理按固定顺序执行：

```
原始因子 → [去极值] → [标准化] → [中性化] → [正交化（可选）] → 处理后因子
```

| 步骤 | 默认值 | 可选项 | 说明 |
|------|-------|--------|------|
| 去极值 | MAD 法（3×MAD） | MAD 法 / 分位数截断 / 不处理 | 移除极端值，避免对后续步骤的干扰 |
| 标准化 | Z-Score | Z-Score / 排序百分位 | 消除量纲差异 |
| 中性化 | 行业中性 | 行业中性 / 行业+市值中性 / 不处理 | 消除风格因子暴露 |
| 正交化 | 不处理 | Gram-Schmidt / 回归残差法 / 不处理 | 消除因子间线性相关性（可选） |

> 预处理管道配置保存在策略版本中，可追溯和复现。预处理后的因子值可预览（Distribution 图）。

### 组合优化器（v1.5）

在 Form Mode 权重配置步骤中，可启用组合优化器：

| 模式 | 默认 | 说明 |
|------|------|------|
| 手动配置 | v1 默认 | 用户手动设定每只标的权重 |
| 等权 | — | 所有持仓等权重分配 |
| IC 加权 | — | 按因子 IC 加权分配权重 |
| Risk Budget | — | 在风险预算约束下优化权重 |

> v1.5 前置条件：分钟线数据 + 冲击成本模型可用。
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

- **启用信号**（仅当关键指标达标时可用，见 06 核心用户流程 BP-B1 修复）
- 导出报告
- 加入对比
- 发送 AI 解读

### 交易成本明细

在 Bottom Area 中增加"交易成本"子区域，明细展示：

| 成本项 | 费率 | 说明 |
|--------|------|------|
| 印花税 | 卖出 0.05% | A 股单向征收 |
| 佣金 | 万 2.5（双向） | 可配置，含最低 5 元 |
| 滑点 | 成交额 × X | 可配置，默认 0.01% |
| 冲击成本 | 自动估算 | 大额订单市场冲击 |

> 回测净值曲线已扣除上述成本。若回测期间印花税/佣金率有调整，按当时实际费率分段计算。

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

### Backtest Compare 视图

> **触发条件**：用户在 Backtest Result 点击"加入对比"后，或在 Backtest Catalog 页选择多个回测进入 Compare 模式。

Compare 视图支持两种对比模式：

**A. 同策略不同参数**：对比同一策略在不同参数下的表现差异。

**B. 不同策略同时间段**：对比不同策略在相同时段内的表现。

#### Compare 视图布局

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Backtest Compare: 3 runs selected        [导出] [关闭]         │
│      ├───────────────────────────────────────────────────────────────┤
│      │ [v1.2 超参A] [v1.2 超参B] [v1.1 baseline]    [+ 添加]         │
│      ├───────────────────────────────────────────────────────────────┤
│      │ 净值叠加图（NAV overlay，各版本颜色区分）                       │
│      ├───────────────────────────────────────────────────────────────┤
│      │ 指标对比表                                                      │
│      │           | v1.2-A | v1.2-B | v1.1-base | 最优               │
│      │ Sharpe     | 1.82   | 1.95   | 1.61      | v1.2-B ★           │
│      │ 年化收益   | 18.2%  | 19.8%  | 16.5%     | v1.2-B ★           │
│      │ 最大回撤   | -12.3% | -15.1% | -11.8%    | v1.1-base ★        │
│      │ 换手率     | 3.2x   | 4.8x   | 2.9x      | —                  │
│      │ 胜率       | 58.2%  | 55.1%  | 57.8%     | v1.2-A ★           │
│      ├───────────────────────────────────────────────────────────────┤
│      │ 持仓差异: 3 只股票不同 | 权重差异 Top5 | 行业暴露差异           │
└──────┴───────────────────────────────────────────────────────────────┘
```

**对比数据来源**：使用 17 回测引擎规格 §11.1 定义的日频净值序列和持仓数据。

**最多对比数量**：5 个回测版本（避免视觉混乱）。

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
- Session Strip（含 **交易阶段指示器**: 集合竞价 / 连续竞价 / 午休 / 收盘集合竞价 / 盘后交易）
- Equity / PnL
- Risk / Alerts
- Positions Summary（含 **T+1 冻结标识**: 当日买入数量标灰，显示为不可卖）
- Signal Queue
- Order Status
- Recent Trades / Exceptions

### 盘后复盘模式（Review Mode）

> **触发条件**：A 股收盘后（15:00 后），Trading Overview 自动切换 Review Mode。用户可手动关闭。

收盘后页面结构变化：

| 区块 | 交易时段 | 收盘后（Review Mode） |
|------|---------|---------------------|
| Session Strip | 交易阶段指示器 | "收盘"标签 + 当日交易摘要 |
| Equity / PnL | 实时盈亏 | **当日归因**（行业贡献/个股贡献/因子贡献） |
| Positions Summary | 持仓列表 | **持仓健康检查**（涨跌停风险/异常波动/偏离成本） |
| Signal Queue | 待处理信号 | **明日策略预演**（预挂单/风险提示/Regime 判断） |

**当日归因区块**内容：

```
今日盈亏: +12,340 (+0.82%)
  行业贡献: 科技 +8,200 | 消费 +3,100 | 金融 +1,040
  个股贡献: 贵州茅台 +5,600 | 宁德时代 +4,200 | 比亚迪 -1,200
  因子贡献: 动量 +6,800 | 价值 +3,500 | 质量 +2,040
```

**持仓健康检查**关注项：

- 明日可能触及涨跌停的持仓
- 当日偏离成本价 >5% 的持仓
- 两融担保比例接近预警线的持仓

**明日策略预演**关注项：

- 明日有重大事件（财报/解禁/期权交割）的持仓标的
- 基于今日 Regime 的策略调整建议
- 待确认信号回顾

### 主 CTA

- 查看信号
- 查看持仓
- 暂停交易
- 涨跌停标的状态概览

### Wireframe

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Trading Header: account / broker / session / pause trading   │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Session Strip: [交易阶段] cash / margin / risk budget / route health│
│      │ 两融: 融资余额 +XX亿 / 融券余额 XX亿 / 担保比例 XX%            │
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
- Scope Strip（含 **涨跌停校验状态**: 涨停买入信号标灰/跳过，跌停卖出信号标灰/跳过）
- Signal Table（含 **信号来源标注**: 策略信号 / AI 信号 / 手动信号，source 可筛选）
- Signal Detail（含 **溯源链接**: 查看来源回测 → /research/backtest/[id]，查看来源策略 → /research/strategies/[id]/studio）

### 主 CTA

- 确认
- 生成订单复核
- 交给 AI 解读
- 查看来源回测
- 查看来源策略

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

### 订单确认面板（Order Confirmation Sheet）

> **触发条件**：用户在 Signals Inbox 确认信号后、生成订单前，自动弹出 Side Sheet。

订单确认面板在 Signal Detail 区域以 Side Sheet 形式展示，用户必须通过确认后才能生成订单。

```
┌──────────────────────────────────────────────┐
│ 订单确认                              [✕]   │
├──────────────────────────────────────────────┤
│ 标的: 贵州茅台 (600519)                      │
│ 方向: 买入  数量: 100 股                     │
│                                              │
│ ── 标的状态检查 ──                           │
│ ✅ 正常交易（非停牌/非退市）                   │
│ ⚠️ 接近涨停（+8.7%），买入可能滑点较大        │
│ ✅ T+1 可卖确认（非当日买入标的）              │
│                                              │
│ ── 委托配置 ──                               │
│ 委托类型: [限价委托 ▼]  （限价 / 市价）       │
│ 委托价格: [1856.00]                          │
│ 委托数量: [100] 股（1 手）                    │
│                                              │
│ ── 预估费用 ──                               │
│ 佣金:   4.64 元                              │
│ 过户费: 0.19 元                              │
│ 印花税: 0.00 元（买入免征）                   │
│ 预估总额: 185,604.83 元                       │
│                                              │
│ [取消]                        [确认提交订单]   │
└──────────────────────────────────────────────┘
```

**状态检查规则**：

| 检查项 | 通过 | 阻断 |
|--------|------|------|
| 标的状态 | 正常交易 | 停牌/退市 → 阻断下单，显示"标的不可交易" |
| 涨跌停 | 可成交 | 涨停买入/跌停卖出 → 阻断，显示"可能无法成交" |
| T+1 冻结 | 可卖出 | 当日买入标的卖出 → 阻断，显示"T+1 不可卖" |
| 两融约束 | 担保比例充足 | 担保比例 < 130% → 阻断，显示"担保比例不足" |
| 价格合理性 | 价格在涨跌停范围内 | 超出范围 → 自动修正到涨停/跌停价 |

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
- **Factor Discovery**（v1.1 新增）

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
│      │ Mode: Market Analysis | Stock Discovery | Strategy Draft | Factor Discovery │
│      ├───────────────┬───────────────────────────────┬──────────────┤
│      │ Sessions      │ Conversation + Structured Out │ Context      │
│      │ templates     │                               │ objects       │
│      │ history       │                               │ evidence      │
│      │ saved notes   │                               │ actions       │
└──────┴───────────────┴───────────────────────────────┴──────────────┘
```

### Factor Discovery 模式（v1.1 新增）

> **定位**：用 LLM 从新闻、研报、龙虎榜、财务数据中自动提取因子假设，是 AI 差异化的核心入口。

**工作流**：

```
用户输入（如"分析最近一个月北向资金大幅流入的个股特征"）
  → Copilot 检索相关数据（龙虎榜/北向/财报/新闻）
  → LLM 生成 Factor Hypothesis（因子假设）
  → 结构化输出：因子定义 + 数据来源 + 预期逻辑 + 验证方法
  → 用户审阅 → "发送到 Factor Analysis" 或 "加入 Strategy Studio"
```

**产出物类型**：

| Artifact | 格式 | 可发送到 |
|----------|------|---------|
| Factor Hypothesis | 结构化假设文档（名称/逻辑/数据源/验证方法） | Factor Analysis / Strategy Studio |
| Earnings Digest | 财报解读报告（收入拆解/利润质量/指引对比） | Research Workspace / Notes |
| Flow Analysis | 资金面/板块轮动分析报告 | Copilot 对话 / Intelligence |

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
- **审批通过后自动生成信号**（见 06 核心用户流程 BP-C1 修复）

### 审批通过后流程

Agent Finding 审批通过后，自动执行以下步骤：

1. Finding 转化为 Signal，出现在 `/trading/signals` 的"待复核"队列
2. Agent Console 中 Finding 状态变为 `approved → signal-generated`
3. Home 的 Pending 区显示新的待复核信号
4. Signal 的 source 标注为 `ai-agent`，关联原始 Finding ID
5. 用户在 Signals Inbox 复核确认后，进入订单执行流程

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

### Multi-Agent Pipeline（v1.1 新增）

> **定位**：编排多个 Agent 协同完成复杂研究任务，是 AI 差异化的长期方向。

**Pipeline 模板**：

| Pipeline 名称 | Agent 链路 | 适用场景 |
|--------------|-----------|---------|
| **全链路研究流水线** | 因子挖掘 Agent → 策略验证 Agent → 风控校验 Agent | 从因子假设到可执行信号的端到端自动化 |
| **财报季解读流水线** | 财报提取 Agent → 归因分析 Agent → 持仓影响评估 Agent | 财报季自动生成持仓标的影响分析 |
| **盘后复盘流水线** | 盈亏归因 Agent → 异常检测 Agent → 策略调整建议 Agent | 收盘后自动生成当日复盘报告 |

**Pipeline 执行流程**：

```
用户创建 Pipeline → 定义输入参数 → 启动
  → Agent 1 执行 → 产出 Artifact 1
  → Artifact 1 作为 Agent 2 的输入
  → Agent 2 执行 → 产出 Artifact 2
  → ...
  → 最终 Agent 产出 → 用户审批
```

**v1 实现范围**：Pipeline 框架定义 + 全链路研究流水线（单 Agent 串行）。多 Agent 并行、自定义 Pipeline 编辑为 v1.5。

### AI Confidence 框架（v1.1 新增）

> **适用范围**：所有 AI 产出（Copilot Suggestion / Agent Finding / Agent Signal）。

所有 AI 产出必须附带 Confidence 评分和 Evidence 链，帮助用户判断 AI 结论的可信度。

| AI 产出类型 | Confidence 展示 | Evidence 链 |
|-------------|----------------|-----------|
| Copilot Suggestion | 🟢 高置信 / 🟡 中置信 / 🔴 低置信 | 引用的数据源 + 时间戳 |
| Agent Finding | confidence score (0-100) + 等级标签 | 工具调用记录 + 数据快照 |
| Agent Signal | confidence score + risk checks 通过/失败 | 来源策略/回测链接/信号逻辑 |

**Confidence 等级定义**：

| 等级 | 分数 | 含义 | 用户引导 |
|------|------|------|---------|
| 🟢 高置信 | 80-100 | 结论基于强数据支撑，可直接采纳 | 默认通过审批 |
| 🟡 中置信 | 50-79 | 结论部分基于推理，建议人工核实 | 标记"需人工复核" |
| 🔴 低置信 | 0-49 | 结论基于弱信号或外推，需谨慎 | 标记"高风险，建议忽略" |

---

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

## 16. Regime Monitor（轻量蓝图）

> **路由**：`/research/regime`
> **Pattern**: Analytical Overview Workspace

### 页面目标

实时监控和判断当前市场状态（Risk-On / Risk-Off / Mixed），为策略调仓和风控提供环境判断依据。是 Flow B（分支 B4：Regime 异常→调整策略）和 Flow D（分支 D2：Regime 变化→策略调整）的关键节点。

### 页面角色

Analytical Overview Workspace（Chart-first 变体）

### 核心动词

monitor → identify → act

### 主工作面

Regime Indicator（主状态仪表）

### 辅工作面

驱动因子 / 历史切换 / 策略影响

### 默认信息顺序

Regime Status → Drivers → Switch History → Strategy Impact

### 核心区块

- Regime Header（标题 / 时间范围 / 刷新）
- Regime Status Strip（当前状态 + 置信度 + 关键指标）
- Regime Indicator（三状态仪表或仪表盘）
- Drivers Panel（驱动当前 Regime 判断的核心变量：波动率/流动性/资金面/宏观事件）
- Switch History（Regime 切换历史时间线）
- Strategy Impact（当前 Regime 下各策略的表现/建议调整）

### 主 CTA

- 查看策略影响
- 跳转到策略工作坊
- AI 解读

### 主要跳转

- 策略影响 → Strategy Studio（Context Transfer: `?ctx[regime]=risk-off`）
- AI 解读 → Copilot
- 驱动因子 → Cross-Market Overview（宏观变量详情）

---

## 17. AI 总览（轻量蓝图）

> **路由**：`/ai`
> **Pattern**: Global Command Center（轻量变体）

### 说明

`/ai` 是 Home Command Center 的轻量变体，聚焦 AI 产出总览与分流。复用 §1 Home 的骨架子集，但内容全部替换为 AI 相关模块。

### 页面目标

让用户进入 AI 域后 5 秒内知道：

1. Agent 当前有哪些运行/待审批
2. Copilot 最近产出了什么
3. 哪些 AI 结论需要人工处理
4. 下一步该去 Copilot 还是 Agent

### 页面角色

Global Command Center（轻量变体）

### 核心区块

- AI Header（标题 / 新建会话 / 新建 Plan）
- AI Pulse（Agent 运行中数量 / 待审批数量 / Copilot 活跃会话）
- Agent Quick View（运行中 Plans / 待审批 Findings / 最近完成的 Runs）
- Copilot Quick View（活跃会话 / 最近产出 / 保存的笔记）
- AI Actions（新建 Copilot 会话 / 新建 Agent Plan / 查看全部 Finding）

### 主 CTA

- 新建 Copilot 会话
- 新建 Agent Plan
- 查看待审批

### 主要跳转

- Agent Quick View → `/ai/agent`
- Copilot Quick View → `/ai/copilot`
- 待审批 → `/trading/signals`（已审批通过并转化为信号的 Finding）

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

### 2026-03-31 — v1.1 页面模板补全

- **[审计 Q1-1]** 新增 §2.2 Markets Intelligence 蓝图（情报中心，tab 视图聚合 5 个情报维度）
- **[审计 Q1-6]** §5 Research Workspace 主 CTA 增加"新建策略"
- **[审计 Q1-7]** 新增 §16 Regime Monitor 轻量蓝图（市场状态监控，Flow B/D 关键节点）
- **[审计 Q1-8]** 新增 §17 AI 总览轻量蓝图（Command Center 轻量变体，AI 产出总览与分流）
- **[审计 Q2-3]** §7 Strategy Studio 新增因子预处理管道（去极值→标准化→中性化→正交化）
- **[审计 Q2-4]** §10 Signals Inbox 新增订单确认面板（Order Confirmation Sheet）
- **[审计 Q2-5]** §9 Trading Overview 新增盘后复盘模式（Review Mode）
- **[审计 Q2-6]** §8 Backtest Result 新增 Backtest Compare 视图
- **[审计 Q2-7]** §7 Strategy Studio 新增组合优化器（等权/IC 加权/Risk Budget）
- **[审计 Q3-1]** §13 Copilot Studio 新增因子发现模式（Factor Discovery，LLM 从新闻/报告/龙虎榜挖掘因子）
- **[审计 Q3-2]** §14 Agent Console 新增 Multi-Agent Pipeline 模板（全链路研究/财报季解读/盘后复盘）
- **[审计 Q3-3]** §14 Agent Console 新增 AI Confidence 框架（3 级置信度 + 证据链可视化）
- **[审计 Q3-5]** §4 Instrument Hub 新增公司行动 Tab（分红历史/限售解禁/股东/机构持仓）
- **[审计 Q3-6]** §4.2 Markets Calendar 新增 A 股事件内容（IPO/解禁/期权到期/经济数据/除权除息/财报披露）

### 2026-03-31 — Core Page Blueprint S/M/L Enhancement Batch

- **[S-1]** §8 Backtest Result: 主 CTA 增加"启用信号"（仅当关键指标达标时可用）
- **[M-8]** §8 Backtest Result: 新增"交易成本明细"子区域（印花税/佣金/滑点/冲击成本）
- **[S-4]** §9 Trading Overview: Session Strip 增加交易阶段指示器（集合竞价/连续竞价/午休/收盘集合竞价/盘后交易）
- **[L-8]** §9 Trading Overview: Positions Summary 增加 T+1 冻结标识
- **[M-6]** §9 Trading Overview: Session Strip wireframe 扩展两融数据行
- **[S-5]** §10 Signals Inbox: Scope Strip 增加涨跌停校验状态，Signal Table 增加来源标注，Signal Detail 增加溯源链接
- **[S-2]** §14 Agent Console: 主 CTA 增加"审批通过后自动生成信号"，新增"审批通过后流程"5 步骤
- **[M-5]** §2.1 A 股总览: Bottom Tab Band 扩展为 资金轮动/龙虎榜/两融数据/事件日历
- **[M-7]** §2.1 A 股总览: 新增 Right Rail 北向资金深度面板（分时净流入/沪股通深股通/持仓 Top10/行业偏好）
- **[M-7]** §2 Cross-Market: Right Rail 增加北向资金深度面板
- **[M-11]** §2 Cross-Market: Right Rail 增加快捷入口 Chart Lab / Calendar
- **[L-7]** §4 Instrument Hub: Object Header 增加停牌/复牌状态标识，Meta Strip 增加停牌日期

### 2026-03-30 — Cross-Market Review R10-R12 Sync

- **[修正]** Cross-Market Matrix 列名"资金面"→"态势"（来源: FIX-03，R10）
- **[新增]** Heat map 5 级 alpha 梯度规范: 0.05/0.10/0.17（R12 收敛值，来源: FIX-04）
- **[新增]** Ambient tint alpha 标准: card 0.06, row 0.05（来源: FIX-08）
- **[新增]** Sparkline opacity 标准: 0.6, stroke-width 1.5px（来源: FIX-07）
- **[新增]** LIVE 状态指示器: 同源绿色 oklch(0.72 0.19 155)，替代"实时"（来源: COPY-09）
- **[新增]** kbd 幽灵键帽: font-mono 10px, border oklch(1 0 0 / 0.10), bg oklch(1 0 0 / 0.04)（来源: FIX-10/COPY-10）
- **[新增]** context-bar 信息层级: 核心(regime color-mix 85%) > 标准(text-secondary) > 辅助(text-tertiary)（来源: R12 FIX-1）
- **[新增]** card-change 字号 14px→13px，归入 5 级字号 scale (10/12/13/16/24)（来源: FIX-09）
