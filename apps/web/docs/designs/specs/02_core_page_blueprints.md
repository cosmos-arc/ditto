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

### Tab Content Sections

> Home 无 tab 系统，以下按可交互区域组织。

#### 区域: Today Pulse
- **子模块**: 组合盈亏、风险指标、市场状态（Regime）、待处理计数、后台任务状态
- **数据字段**: 当日 PnL（来源: Portfolio Engine）、风险指标（来源: Risk Engine）、市场状态标签（来源: Regime Engine）、待处理事项数（来源: Signals/Orders/Alerts 聚合）、任务运行数（来源: Job Scheduler）
- **交互说明**: 各指标卡片点击跳转对应详情页；数字变化时有微动效；风险超阈值时卡片边框变红

#### 区域: Decision Banner
- **子模块**: 总资产概览、当日盈亏、风险建议、AI 操作建议
- **数据字段**: 总资产（来源: Portfolio Engine）、当日 PnL 金额与百分比（来源: Portfolio Engine）、风险等级（来源: Risk Engine）、AI 建议文本（来源: AI Agent）
- **交互说明**: Banner 根据风险等级变色（绿/黄/红）；AI 建议区域点击展开完整解读 Drawer

#### 区域: Pending / Next Actions
- **子模块**: 跨域待处理事项列表（信号/订单/预警/审批/回测）
- **数据字段**: 事项类型图标（来源: 系统枚举）、事项摘要（来源: Signals/Orders/Alerts Engine）、优先级标签（来源: 业务规则）、时间戳（来源: 事项创建时间）
- **交互说明**: 按优先级排序；点击事项跳转对应处理页面（Signals Inbox/Orders/Alerts 等）；支持快速操作（如一键复核通过）

#### 区域: Alerts / Market Snapshot
- **子模块**: 全局预警列表、市场脉搏快览（4 指标）
- **数据字段**: 预警标题与级别（来源: Alert Engine）、触发时间（来源: Alert Engine）、市场脉搏指标（来源: Quote Service / Market Data）
- **交互说明**: 预警按级别排序，红色预警置顶；市场脉搏始终展示，不依赖用户状态

#### 区域: Recent Signals / Runs
- **子模块**: 最近信号列表、最近回测运行
- **数据字段**: 信号摘要与状态（来源: Signals Engine）、回测名称与状态（来源: Backtest Engine）、完成时间（来源: 对应 Engine）
- **交互说明**: 最近 5 条预览；点击跳转对应详情页

#### 区域: Agent Findings / Data Health
- **子模块**: Agent 发现摘要、数据健康概览
- **数据字段**: 发现摘要与状态（来源: Agent Engine）、数据源健康状态（来源: Data Quality Service）、异常计数（来源: Data Quality Service）
- **交互说明**: 数据异常时红色标识；点击跳转 AI 域或 Platform 域

#### 区域: My Workspace
- **子模块**: 可定制 widget 网格（默认: 持仓概览 / 关注列表 / 快捷入口 / 市场日历）
- **数据字段**: widget 配置（来源: 用户偏好 Store）、各 widget 数据（来源: 对应 Service）
- **交互说明**: 支持 widget 拖拽排序；支持添加/移除 widget；点击"编辑工作台"进入编辑模式

### Overlay Registry

#### Overlay: 信号详情 — Drawer
- **触发条件**: 用户点击 Pending / Next Actions 中的信号条目时
- **内容结构**: 信号摘要 + 标的详情 + 策略信息 + 风险评估 + 操作按钮（复核通过/驳回/查看完整信号）
- **关闭行为**: 点击遮罩 / ESC / 操作后自动关闭并刷新列表

#### Overlay: 订单确认 — Modal
- **触发条件**: 用户在信号详情中点击"复核通过"或"发起订单"时
- **内容结构**: 订单摘要（标的/方向/数量/价格）+ 风险校验结果 + 确认/取消按钮
- **关闭行为**: 点击遮罩 / ESC / 确认后自动关闭并跳转 Orders

#### Overlay: 编辑工作台 — Drawer
- **触发条件**: 用户点击"编辑工作台"按钮时
- **内容结构**: 可用 widget 列表 + 当前布局预览 + 拖拽排序区 + 重置默认 / 保存按钮
- **关闭行为**: 点击遮罩 / ESC / 保存后自动关闭

#### Overlay: AI 建议详情 — Drawer
- **触发条件**: 用户点击 Decision Banner 中 AI 建议区域时
- **内容结构**: AI 建议全文 + 关联数据支撑 + 操作建议 + 关闭按钮
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected |
|------|---------|---------|-------|--------|-------|----------|
| Today Pulse | 各指标卡片正常展示 | 指标 skeleton + 脉冲动画 | "开始使用 Ditto"引导 CTA | "数据加载失败" + 重试按钮 | 黄色圆点 + "数据延迟" | 选中指标卡片边框高亮 |
| Decision Banner | 资产/PnL/风险/建议正常展示 | 数字 skeleton + 建议区 skeleton | "开始使用 Ditto"引导 CTA | "加载失败" + 重试 | 数据时戳标记 | 不适用 |
| Pending / Next Actions | 事项列表（3-5 条预览） | 列表 skeleton（3 行） | "暂无待处理事项" + 绿色对勾 | "加载失败" + 重试 | 事项旁灰色圆点 | 选中事项行高亮 |
| Alerts / Market Snapshot | 预警列表 + 市场脉搏指标 | skeleton 列表 + 指标 skeleton | 预警区"一切正常"状态标识 | "加载失败" + 重试 | 红色预警持续高亮 | 选中预警行高亮 |
| Recent Signals / Runs | 最近 5 条信号/回测预览 | skeleton 列表（2 行） | "暂无近期活动" | "加载失败" + 重试 | 灰色时戳标记 | 选中条目高亮 |
| Agent Findings | Agent 摘要列表 | skeleton 列表（2 行） | "暂无 Agent 活动" | "AI 服务异常" + 重试 | 黄色圆点 | 不适用 |
| Data Health | 健康状态面板 | skeleton 面板 | "所有数据源正常" + 绿色标识 | "数据源连接异常" + 重试 | 异常数据源黄色标记 | 不适用 |
| My Workspace | widget 网格正常展示 | widget skeleton 占位 | 空网格 + "添加 widget"CTA | "加载工作台失败" + 重试 | widget 边框黄色标记 | 选中 widget 边框高亮

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
- Context Bar（全局环境客观指标：市态 / 波动 / 美元 / 预警）
- Scope Strip（AI 今日解读：领涨 / 领跌 / 风格 / 事件）
- Cross-Market Card Grid（6 卡片：A股 / 港股 / 美股 / 利率 / 外汇 / 商品）
- Cross-Market Matrix（行：市场，列：1D / 1W / 1M / Vol / Breadth / Flow）
- Macro Drivers Bar / 宏观驱动（DXY / US10Y / CN10Y / VIX / Gold / Oil / CNY）
- Right Rail（市场脉搏 / 风险预警 / 关键事件 / 推荐下钻 / 快捷入口: Chart Lab / Calendar）
- Bottom Tab Band: 资金轮动 / 事件日历 / AI 解读

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
│      │ 市态=温和风险偏好 | 波动=回落 | 美元=走弱 | 预警=2           │
│      ├───────────────────────────────────────────────────────────────┤
│      │ 领涨：港股科技/黄金 | 领跌：美元/长债 | 风格=成长占优 | 事件=FOMC 03:00 │
│      ├─────────────────────────────────┬─────────────────────────────┤
│      │ 中国A股   港股     美股          │ 市场脉搏摘要               │
│      │ 利率     外汇     商品          │ 风险与预警                  │
│      ├─────────────────────────────────┤ 关键事件                    │
│      │ Cross-Market Matrix             │ 推荐下钻                    │
│      ├─────────────────────────────────┤ 快捷入口                    │
│      ├─────────────────────────────────┤                             │
│      │ 宏观驱动 Bar                    │                             │
│      ├─────────────────────────────────┴─────────────────────────────┤
│      │ [资金轮动] [事件日历] [AI 解读]                                 │
└──────┴───────────────────────────────────────────────────────────────┘
```

### Tab Content Sections

> 全市场总览无传统顶部 tab，Bottom Tab Band 作为辅助视图切换。

#### Tab: 资金轮动（Bottom Tab）
- **子模块**: 跨市场资金流向对比、板块资金流入排名、ETF 资金净申赎
- **数据字段**: 市场间资金流向（来源: ETF 申赎数据 / 北向资金）、板块资金净流入 Top10（来源: 板块指数统计）、ETF 申赎规模（来源: 基金公司披露）
- **交互说明**: 按资金净流入排序；点击板块下钻到对应单市场页；支持时间框架切换（1D/1W/1M）

#### Tab: 事件日历（Bottom Tab）
- **子模块**: 经济数据发布日历、央行决议、财报季、重要政策事件
- **数据字段**: 事件日期与时间（来源: 宏观日历）、事件类型标签（来源: 系统分类）、预期值（来源: 一致预期）、实际值（来源: 数据发布源）、影响市场标记（来源: AI 归因）
- **交互说明**: 按时间排列；已公布事件颜色标识（超预期绿/不及预期红）；点击事件打开事件详情 Drawer

#### Tab: AI 解读（Bottom Tab）
- **子模块**: AI 市场日评、跨市场联动分析、异动归因、趋势预判
- **数据字段**: AI 解读文本（来源: AI Agent）、关联数据引用（来源: Market Data）、置信度标签（来源: AI Agent）、生成时间（来源: AI Agent）
- **交互说明**: 展示 AI 生成的结构化市场分析；支持"查看更多"展开完整解读；可发送到 Copilot 进一步讨论

### Overlay Registry

#### Overlay: 市场深度/板块详情 — Drawer
- **触发条件**: 用户点击 Market Card 或 Cross-Market Matrix 中的市场/板块行时
- **内容结构**: 市场深度指标（涨跌幅/成交额/换手率/波动率/涨跌比） + 板块分解 + 领涨/领跌个股 + 资金流向 + 入口 CTA（"进入 XX 总览"）
- **关闭行为**: 点击遮罩 / ESC / 点击 CTA 跳转并关闭

#### Overlay: 指数成分股 — Sheet
- **触发条件**: 用户点击 Context Bar 或 Scope Strip 中的指数名称时
- **内容结构**: 指数成分股列表（代码/名称/涨跌幅/权重）+ 排序/筛选控件 + 加入观察 CTA
- **关闭行为**: 点击遮罩 / ESC

#### Overlay: 筛选器面板 — Drawer
- **触发条件**: 用户点击工具栏筛选按钮时
- **内容结构**: 市场范围筛选、时间框架选择、数据维度筛选、视图密度切换 + 应用/重置按钮
- **关闭行为**: 点击遮罩 / ESC / 点击"应用"后自动关闭

#### Overlay: 事件详情 — Drawer
- **触发条件**: 用户点击事件日历中的事件条目时
- **内容结构**: 事件标题 + 日期时间 + 预期值 vs 实际值 + 历史对比图表 + AI 归因分析 + 关联市场影响
- **关闭行为**: 点击遮罩 / ESC

#### Overlay: 固定视角 — Toast
- **触发条件**: 用户点击"固定视角"按钮时
- **内容结构**: "视角已固定"提示 + 撤销按钮
- **关闭行为**: 3 秒自动消失 / 手动关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected |
|------|---------|---------|-------|--------|-------|----------|
| Context Bar | 四指标正常展示（市态/波动/美元/预警） | 指标 skeleton | "暂无市场数据" | "市场数据加载失败" + 重试 | 黄色边框 + 数据时戳 | 不适用 |
| Scope Strip | AI 解读文本 + 领涨/领跌标签 | 脉冲动画 + skeleton 文本 | "AI 分析中，请稍候..." | "AI 分析失败" + 重试 | 标注生成时间 | 不适用 |
| Market Card Grid | 6 张卡片正常展示 | 卡片 skeleton × 6 | 卡片 skeleton + "无市场数据" | "加载失败" + 重试 | 边框黄色标记 | 选中卡片高亮 + 右侧联动 |
| Cross-Market Matrix | 矩阵单元格正常渲染（含热力色） | 单元格 skeleton | 空矩阵 + "无数据" | "加载失败" + 重试 | 单元格黄色边框 | 选中行高亮 + Right Rail 联动 |
| Macro Drivers Bar | 各驱动指标正常展示 | 指标 skeleton | "暂无宏观数据" | "加载失败" + 重试 | 指标旁黄色圆点 | 选中指标展开详情 |
| Right Rail | 各面板正常展示 | 面板 skeleton | 面板空状态 CTA | "加载失败" + 重试 | 面板黄色边框 | 不适用 |
| Bottom Tab Band | 3 个 tab 标签 + 当前 tab 内容 | tab 内容 skeleton | 当前 tab "暂无数据" | "加载失败" + 重试 | tab 标签黄色圆点 | 选中 tab 高亮

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

### Tab Content Sections

> A 股总览无传统顶部 tab，Bottom Tab Band 作为辅助视图切换。

#### Tab: 资金轮动（Bottom Tab）
- **子模块**: 北向资金净流入、板块资金流向、龙虎榜席位资金、两融余额变动
- **数据字段**: 北向净买入金额（来源: 沪深港通）、沪股通/深股通分别净买入（来源: 沪深港通）、板块资金净流入 Top10（来源: 板块指数）、两融余额（来源: 交易所披露）、融资买入额（来源: 两融数据）
- **交互说明**: 北向资金点击跳转 Right Rail 深度面板；板块按净流入排序；支持时间框架切换

#### Tab: 龙虎榜（Bottom Tab）
- **子模块**: 龙虎榜上榜股票、上榜原因分类、席位资金统计
- **数据字段**: 上榜股票列表（来源: 交易所披露）、上榜原因（来源: 龙虎榜分类）、买卖席位（来源: 龙虎榜数据）、席位净买入额（来源: 龙虎榜数据）、机构/游资标签（来源: 席位分类算法）
- **交互说明**: 按净买入额排序；点击股票跳转 Instrument Hub；按上榜原因筛选（涨停/跌停/换手率/振幅等）

#### Tab: 两融数据（Bottom Tab）
- **子模块**: 两融余额趋势、融资/融券余额分解、行业两融偏好、标的融资买入排名
- **数据字段**: 两融余额及环比（来源: 交易所披露）、融资余额/融券余额（来源: 两融数据）、行业两融净买入（来源: 行业统计）、标的融资买入额 Top10（来源: 两融数据）
- **交互说明**: 展示趋势折线图；行业按融资净买入排序；点击标的跳转 Instrument Hub

#### Tab: 事件日历（Bottom Tab）
- **子模块**: A 股相关事件日历（IPO/解禁/财报/除权除息/股东大会）
- **数据字段**: 事件日期（来源: 交易所公告）、事件类型（来源: 系统分类）、涉及标的（来源: 公告解析）、影响评估（来源: AI Agent）
- **交互说明**: 按日期排列；支持按事件类型筛选；点击事件展开详情

### Overlay Registry

#### Overlay: 北向资金详情 — Drawer
- **触发条件**: 用户点击 Right Rail 北向资金深度面板中的展开按钮，或 Context Bar 中北向资金指标时
- **内容结构**: 分时净流入曲线（当日分钟级）+ 沪股通/深股通分别展示 + 北向持仓 Top10 变动（增持/减持数量）+ 行业偏好分析（北向近期净买入行业）+ "查看完整报告"CTA
- **关闭行为**: 点击遮罩 / ESC

#### Overlay: 行业详情 — Sheet
- **触发条件**: 用户点击 Market Structure Map 中的行业节点时
- **内容结构**: 行业概况（涨跌幅/成交额/换手率）+ 行业成分股列表 + 资金流向 + 领涨/领跌个股 + 加入观察 CTA
- **关闭行为**: 点击遮罩 / ESC / 点击标的跳转并关闭

#### Overlay: 筛选器面板 — Drawer
- **触发条件**: 用户点击工具栏筛选按钮时
- **内容结构**: 板块范围筛选、时间框架选择、Map 视图模式切换（treemap/heatmap）+ 应用/重置按钮
- **关闭行为**: 点击遮罩 / ESC / 点击"应用"后自动关闭

#### Overlay: AI 解读 — Drawer
- **触发条件**: 用户点击"AI 解读"按钮时
- **内容结构**: AI 生成的 A 股结构分析 + 主线归因 + 异动解读 + 趋势预判 + 发送到 Copilot CTA
- **关闭行为**: 点击遮罩 / ESC

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected |
|------|---------|---------|-------|--------|-------|----------|
| Context Bar | 四指标正常展示（Regime/Breadth/北向/Alerts） | 指标 skeleton | "暂无 A 股数据" | "加载失败" + 重试 | 黄色边框 + 数据时戳 | 不适用 |
| Scope Strip | AI 解读文本 + 强势/承压板块标签 | 脉冲动画 + skeleton | "AI 分析中..." | "AI 分析失败" + 重试 | 标注生成时间 | 不适用 |
| Market Structure Map | treemap/heatmap 正常渲染 | 空白占位 + 加载 spinner | 空白 + "暂无结构数据" | "加载失败" + 重试 | 节点边框黄色 | 选中节点高亮 + 弹出 Sheet |
| Index Summary | 4 个指数卡片正常展示 | 卡片 skeleton × 4 | "暂无指数数据" | "加载失败" + 重试 | 指标旁黄色圆点 | 选中指数高亮 |
| ETF Matrix | ETF 表格正常展示 | 表格 skeleton | "暂无 ETF 数据" | "加载失败" + 重试 | 行黄色圆点 | 选中行高亮 + 跳转 CTA |
| Movers | 涨幅榜/跌幅榜正常展示 | 列表 skeleton | "暂无涨跌数据" | "加载失败" + 重试 | 灰色时戳标记 | 选中条目高亮 |
| Right Rail 北向深度面板 | 分时曲线 + 持仓 Top10 + 行业偏好 | 曲线 skeleton + 列表 skeleton | "盘前暂无北向数据" | "加载失败" + 重试 | 数据时戳标记 | 不适用 |
| Bottom Tab Band | 4 个 tab 标签 + 当前 tab 内容 | tab 内容 skeleton | 当前 tab "暂无数据" | "加载失败" + 重试 | tab 标签黄色圆点 | 选中 tab 高亮

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

### Tab Content Sections

#### Tab: 资金面
- **子模块**: 资金流向总览、板块资金流入/流出、个股大单追踪、北向资金概览
- **数据字段**: 净流入金额（来源: Level-1 行情）、主力资金净额（来源: 大单统计）、板块排名 Top10（来源: 板块指数）、北向资金净买入（来源: 沪深港通）、大单成交明细（来源: 逐笔成交）
- **交互说明**: 板块按净流入排序，点击板块下钻到行业详情；个股大单支持按时间/金额筛选；北向资金概览点击跳转 A 股总览 Right Rail 深度面板

#### Tab: 宏观
- **子模块**: 宏观经济日历、关键指标追踪（CPI/PPI/PMI/M2/社融）、中美利差、汇率与外储
- **数据字段**: 事件日期与预期值（来源: Wind/彭博宏观数据）、实际值与偏差（来源: 统计局）、中美 10Y 利差（来源: 中债/美债）、USDCNY 即期（来源: 外汇市场）、外汇储备（来源: 外管局）
- **交互说明**: 日历按时间排列，已公布事件显示实际值颜色标识（超预期绿/不及预期红）；点击事件展开详情 Drawer；指标支持同比/环比切换

#### Tab: 基本面
- **子模块**: 财报日历、业绩快报、分析师评级变动、盈利预测调整
- **数据字段**: 报告期与发布日期（来源: 交易所公告）、营收/净利润同比（来源: 财报数据）、评级机构与目标价（来源: 分析师研报）、一致预期 EPS（来源: Wind 一致预期）
- **交互说明**: 按发布日期倒序排列；支持按行业/超预期幅度筛选；点击条目打开情报详情 Drawer，展示完整财报摘要

#### Tab: 新闻
- **子模块**: 实时新闻流、热点追踪、研报摘要、政策解读
- **数据字段**: 标题与摘要（来源: 财联社/华尔街见闻等）、发布时间（来源: 新闻源）、关联标的标签（来源: NER 解析）、情绪标签（来源: NLP 模型）、热点度排名（来源: 聚合统计）
- **交互说明**: 新闻流按时间倒序，支持按情绪/来源/关联标的筛选；热点追踪展示 Top5 话题及其关联标的；点击条目打开情报详情 Drawer

#### Tab: 关联网络
- **子模块**: 标的相关性图谱、板块联动分析、资金链路追踪、产业链传导
- **数据字段**: 相关性系数矩阵（来源: 历史收益率计算）、板块联动强度（来源: 贝塔系数）、资金流向路径（来源: 持仓变动）、产业链上下游映射（来源: 行业分类数据）
- **交互说明**: 图谱支持缩放与拖拽；点击节点展开关联标的列表；支持选中多个节点比较联动关系

### Overlay Registry

#### Overlay: 情报详情 — Drawer
- **触发条件**: 用户点击任意情报条目（资金面/宏观/基本面/新闻/关联网络）时
- **内容结构**: 标题 + 来源标识 + 时间戳 + 正文/数据摘要 + 关联标的列表 + AI 摘要 + 操作栏（加入观察/发送到 Copilot/收藏/标注）
- **关闭行为**: 点击遮罩 / ESC / 切换 tab 时保留 Drawer 状态

#### Overlay: 自定义筛选 — Sheet
- **触发条件**: 用户点击筛选器按钮或 Right Rail 中的"高级筛选"时
- **内容结构**: 筛选条件分组（行业/时间范围/数据源/情绪标签/关联标的）+ 已保存的筛选预设列表 + 重置 / 应用按钮
- **关闭行为**: 点击遮罩 / ESC / 点击"应用"后自动关闭并刷新视图

#### Overlay: 收藏/标注成功 — Toast
- **触发条件**: 用户点击"收藏"或"标注"操作成功后
- **内容结构**: 操作结果提示（如"已收藏"）+ 撤销按钮
- **关闭行为**: 3 秒自动消失 / 手动关闭

#### Overlay: 删除标注确认 — Confirm Dialog
- **触发条件**: 用户对已标注的情报执行删除操作时
- **内容结构**: 标题"确认删除标注" + 标注摘要 + 取消 / 确认删除按钮
- **关闭行为**: 点击取消 / 点击遮罩 / 确认删除后自动关闭

#### Overlay: 发送到 Copilot — Drawer
- **触发条件**: 用户点击"发送到 Copilot"时
- **内容结构**: 选中情报预览 + 补充说明输入框 + Copilot 会话选择 + 发送 / 取消按钮
- **关闭行为**: 点击遮罩 / ESC / 发送成功后自动关闭并跳转 Copilot 会话

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected |
|------|---------|---------|-------|--------|-------|----------|
| Tab 视图 | 情报列表正常展示 | skeleton 列表（4-6 行占位） | "暂无符合条件的数据" + 引导 CTA | 错误图标 + "加载失败" + 重试按钮 | 顶部黄色提示条"数据更新于 XX 分钟前" | 当前行高亮 + 展开关联详情 |
| Right Rail 关联标的 | 标的列表 + 涨跌幅 | skeleton 卡片（2-3 张） | "无关联标的" | 错误提示 + 重试 | 边框变黄 + 时戳标记 | 选中标的联动主视图高亮 |
| Right Rail 筛选器 | 筛选条件展示 + 计数 | skeleton 面板 | "无活跃筛选" | 错误提示 | 不适用 | 已选筛选项高亮 |
| Right Rail AI 摘要 | AI 生成摘要文本 | 脉冲动画 + "AI 分析中..." | "暂无 AI 摘要" + 触发按钮 | "AI 分析失败" + 重试 | 标注生成时间 | 不适用 |
| Analysis Band | 趋势/对比/笔记条正常展示 | skeleton 条状占位 | "暂无分析记录" + 新建 CTA | 错误提示 + 重试 | 数据时戳标记 | 当前选中条高亮 |

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

### Tab Content Sections

> Screener 无传统 tab 系统，以下按可交互区域组织。

#### 区域: Filters
- **子模块**: 资产类型选择、市场范围、Universe 选择、时间框架、市场态（Regime）过滤、文本搜索、条件组（AND/OR 组合）、排除规则
- **数据字段**: 资产类型枚举（来源: 系统配置）、市场枚举（来源: 系统配置）、Universe 列表（来源: Universe Service）、Regime 标签（来源: Regime Engine）、条件字段下拉（来源: Factor/Indicator Registry）
- **交互说明**: 条件组支持 AND/OR 切换；支持拖拽排序条件优先级；支持保存为预设模板；点击「运行筛选」触发查询

#### 区域: Results Table
- **子模块**: 列定义管理、排序控件、虚拟滚动表格、行操作菜单、批量选择
- **数据字段**: 标的代码（来源: Instrument Master）、标的名称（来源: Instrument Master）、所属行业（来源: Instrument Master）、最新价/涨跌幅（来源: Quote Service）、因子值/评分（来源: Factor Engine）、自定义列（来源: 用户列配置）
- **交互说明**: 列可拖拽排序、显示/隐藏、宽度调整；点击行头 checkbox 进入批量模式；点击行进入 Instrument Hub；右键菜单支持快捷操作（观察/标的池/Compare）；虚拟滚动支持万级行数

#### 区域: Compare Drawer
- **子模块**: 概览对比、技术面对比、基本面对比、风险指标对比
- **数据字段**: 标的基本信息（来源: Instrument Master）、价格/技术指标（来源: Quote Service）、财务数据（来源: Fundamental Service）、风险指标（来源: Risk Service）
- **交互说明**: 从 Compare Cart 拖入标的；最多对比 6 个标的；维度切换（概览/技术/基本面/风险）；点击「生成标的池」将对比结果固化为 Universe

#### 区域: Actions Panel
- **子模块**: 评分预设、Compare Cart、结果去向（Destinations）
- **数据字段**: 评分模型列表（来源: Scoring Service）、Compare Cart 状态（来源: 客户端状态）、目标 Universe/Watchlist 列表（来源: Universe/Watchlist Service）
- **交互说明**: 评分预设下拉选择后自动重算；Compare Cart 实时显示已加入数量；结果去向支持多选目标

### Overlay Registry

#### Overlay: 保存预设 — Sheet
- **触发条件**: 用户点击「保存预设」按钮
- **内容结构**: 预设名称输入 + 条件摘要展示 + 标签选择 + 保存/取消按钮
- **关闭行为**: 点击遮罩 / ESC / 保存成功后自动关闭

#### Overlay: 列管理 — Drawer
- **触发条件**: 用户点击表格列头「列管理」图标
- **内容结构**: 可用列列表（含搜索） + 已选列列表 + 拖拽排序 + 重置默认 / 确认按钮
- **关闭行为**: 点击遮罩 / ESC / 确认后关闭

#### Overlay: Compare Drawer — Drawer
- **触发条件**: 用户点击 Compare Cart 展开按钮或从行菜单选择「加入对比」
- **内容结构**: Compare Cart 标题 + 已选标的标签 + 对比维度 Tabs + 对比内容区 + 底部操作栏
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 生成标的池确认 — Modal
- **触发条件**: 用户点击「生成标的池」按钮
- **内容结构**: 提示文案 + 标的池名称输入 + 包含标的数据量提示 + 确认/取消按钮
- **关闭行为**: 点击遮罩 / ESC / 确认创建后自动关闭

#### Overlay: 导出结果 — Sheet
- **触发条件**: 用户点击「导出」按钮
- **内容结构**: 导出格式选择（CSV/Excel） + 列范围（当前列/全部列） + 数据范围（全部/已选） + 导出按钮
- **关闭行为**: 点击遮罩 / ESC / 导出开始后关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| Filters | 展示当前条件 | — | 显示默认条件 | 筛选条件加载失败 + 重试 | — | 条件高亮显示 | — |
| Results Table | 渲染数据行 | 行 skeleton（8 行） | 「暂无匹配标的」+ 调整筛选条件 CTA | 「加载失败」+ 重试按钮 | 行左上角黄色圆点 + 提示文字 | 行背景高亮 + 右侧 Actions 联动 | 顶部批量操作栏: 观察/标的池/导出/Compare |
| Compare Cart | 显示已选数量（0-N） | — | 空状态 + 拖入提示 | — | — | — | 显示批量已选数量 |
| Compare Drawer | 展示对比内容 | 图表/数据 skeleton | 「请从结果表添加标的」 | 「加载对比数据失败」+ 重试 | 黄色边框提示 | 对比项高亮 | — |
| Scoring Presets | 下拉列表 | 下拉 skeleton | 「暂无评分模型」 | — | — | 选中项标记 | — |
| Result Destinations | 目标列表 | 列表 skeleton | 「暂无可选目标」 | — | — | — | 支持批量发送 |

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

### Tab Content Sections

#### Tab: 概览（Overview）
- **子模块**: 关键指标卡片（价格/涨跌/市值/PE/PB）、行业排名、核心财务摘要、近期事件提示
- **数据字段**: 最新价/涨跌幅/涨跌额（来源: Quote Service）、总市值/流通市值（来源: Instrument Master）、PE(TTM)/PB/PS（来源: Fundamental Service）、行业排名（来源: Ranking Engine）、近期公司行动提示（来源: Corporate Actions Service）
- **交互说明**: 价格指标支持点击切换时间框架（1D/1W/1M/3M/YTD/1Y）；行业排名支持点击跳转到同行业对比；事件提示支持点击跳转到对应 tab

#### Tab: 行情（Chart）
- **子模块**: 价格图表区域、技术指标叠加、时间框架切换、绘图工具栏、图表类型切换（K线/折线/面积）
- **数据字段**: OHLCV 数据（来源: Quote Service）、技术指标（MA/MACD/RSI/布林带，来源: Indicator Engine）、成交量（来源: Quote Service）、复权因子（来源: Instrument Master）
- **交互说明**: 支持鼠标悬停十字线 + 数据浮窗；支持拖拽缩放时间范围；技术指标可叠加/移除；绘图工具支持趋势线/水平线/斐波那契；双击重置视图

#### Tab: 态势（Flow / Sentiment）
- **子模块**: 资金流向图（主力/散户/北向）、资金流入流出排行、筹码分布、市场情绪指标
- **数据字段**: 主力净流入/散户净流入（来源: Flow Service）、北向持仓变动（来源: Northbound Service）、筹码分布区间（来源: Chip Distribution Service）、换手率/量比（来源: Quote Service）
- **交互说明**: 资金流向支持按日/周/月切换；筹码分布与价格图联动；点击资金流入排行项跳转到对应标的

#### Tab: 基本面（Fundamentals）
- **子模块**: 财务三表摘要（利润表/资产负债表/现金流量表）、关键财务指标趋势、杜邦分析、同行对比
- **数据字段**: 营收/净利润/毛利率/净利率/ROE/ROA（来源: Fundamental Service）、资产负债率/流动比率（来源: Fundamental Service）、经营性现金流（来源: Fundamental Service）、同行对比数据（来源: Peer Comparison Service）
- **交互说明**: 财务指标趋势图支持多周期切换（季度/年度）；同行对比支持雷达图/表格切换；杜邦分析支持点击下钻

#### Tab: 公司行动（Corporate Actions）
- **子模块**: 近期公司行动时间线、分红历史表格、限售解禁日历、股东/机构持仓变动
- **数据字段**: 除权除息日/每股派息/送股/转增（来源: tushare 分红送转接口）、限售解禁数量/类型/市值（来源: tushare share_float 接口）、前十大股东变动（来源: tushare 股东人数接口）、机构持仓比例（来源: Institutional Holdings Service）
- **交互说明**: 时间线支持点击展开详情；分红历史支持按年筛选；限售解禁支持日历视图切换

#### Tab: 新闻（News）
- **子模块**: 新闻流列表、新闻分类筛选、AI 新闻摘要、相关新闻
- **数据字段**: 新闻标题/来源/时间（来源: News Service）、AI 摘要（来源: AI Summary Service）、情感标签（来源: Sentiment Service）、分类标签（来源: News Service）
- **交互说明**: 支持按时间/相关性排序；分类筛选（公告/研报/新闻/社交媒体）；AI 摘要支持展开/收起；点击新闻打开详情

#### Tab: 关联网络（Network）
- **子模块**: 关联标的图（同行业/同概念/供应链）、关联强度指标、网络布局控件
- **数据字段**: 关联标的列表及关联类型（来源: Relation Service）、关联强度分数（来源: Relation Service）、概念标签（来源: Concept Service）
- **交互说明**: 力导向图支持缩放/拖拽；节点点击跳转到对应标的；关联类型筛选（行业/概念/供应链/股东）

#### Tab: 公告（Announcements）
- **子模块**: 公告列表、公告类型筛选、公告详情预览
- **数据字段**: 公告标题/日期/类型（来源: Announcement Service）、公告正文（来源: Announcement Service）、重要性标签（来源: AI Classification Service）
- **交互说明**: 支持按类型筛选（财报/股东大会/限售解禁/增持减持/其他）；重要公告高亮标记；点击展开详情面板

### Overlay Registry

#### Overlay: 图表工具栏 — Floating Toolbar
- **触发条件**: 用户在行情 tab 中点击绘图工具按钮
- **内容结构**: 绘图工具选择（趋势线/水平线/斐波那契/标注） + 颜色选择 + 清除所有绘图
- **关闭行为**: 点击其他区域 / ESC / 点击关闭按钮

#### Overlay: 新闻详情 — Drawer
- **触发条件**: 用户在新闻列表中点击新闻条目
- **内容结构**: 新闻标题 + 来源/时间 + 正文内容 + AI 摘要 + 相关标的标签 + 关闭按钮
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 公告详情 — Drawer
- **触发条件**: 用户在公告列表中点击公告条目
- **内容结构**: 公告标题 + 日期/类型 + 正文内容 + 关联公司行动提示 + 下载原文按钮
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 加入观察/标的池 — Sheet
- **触发条件**: 用户点击 Object Header 中的「加入观察」或「加入标的池」按钮
- **内容结构**: 目标选择（已有 Watchlist/Universe 列表） + 新建分组输入 + 确认/取消
- **关闭行为**: 点击遮罩 / ESC / 确认后自动关闭 + Toast 提示

#### Overlay: 发送到研究 — Sheet
- **触发条件**: 用户点击「发送到研究」按钮
- **内容结构**: 研究目标选择（回测/策略/实验） + 附注输入 + 发送/取消
- **关闭行为**: 点击遮罩 / ESC / 发送后自动关闭 + Toast 提示

#### Overlay: 停牌详情 — Modal
- **触发条件**: 标的处于停牌状态时，用户点击停牌状态标识
- **内容结构**: 停牌原因 + 停牌日期 + 预计复牌日期 + 历史停牌记录 + 关闭按钮
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| Object Header | 显示标的名称/代码/价格/状态 | 标题 skeleton + 价格 placeholder | — | 「标的信息加载失败」+ 重试 | 价格右上角黄色脉冲点 | — | — |
| Meta Strip | 显示行业/市场/标签/所属池 | 条目 skeleton | — | — | 黄色边框提示 | — | — |
| 概览 Tab: 指标卡片 | 渲染指标值 + 变化趋势 | 卡片 skeleton（4 个） | 「暂无基本面数据」 | 「数据加载失败」+ 重试 | 指标值黄色闪烁 | — | — |
| 概览 Tab: 行业排名 | 排名数值 + 排名徽章 | skeleton | 「暂无排名数据」 | — | 黄色边框 | — | — |
| 行情 Tab: 图表 | 渲染 K 线/指标 | 图表 skeleton + 脉冲动画 | 「暂无行情数据」 | 「行情数据加载失败」+ 重试 | 图表顶部黄色横条 + 时戳 | — | — |
| 态势 Tab: 资金流向 | 流向柱状图 + 排行 | 图表 skeleton | 「暂无资金数据」 | 「数据加载失败」+ 重试 | 黄色边框提示 | — | — |
| 基本面 Tab: 财务表 | 渲染财务数据 + 趋势图 | 表格 skeleton（5 行） | 「暂无财务数据」 | 「财务数据加载失败」+ 重试 | 黄色边框 + 提示 | — | — |
| 公司行动 Tab: 时间线 | 渲染事件节点 | 时间线 skeleton | 「近 30 天无公司行动」 | 「加载失败」+ 重试 | — | 事件节点高亮 | — |
| 新闻 Tab: 新闻流 | 新闻列表 + AI 摘要 | 列表 skeleton（5 条） | 「暂无相关新闻」 | 「新闻加载失败」+ 重试 | 顶部黄色提示「部分新闻可能不是最新」 | 新闻条目高亮 | — |
| 关联网络 Tab: 关系图 | 渲染力导向图 | 图 skeleton + 节点占位 | 「暂无关联标的」 | 「关联数据加载失败」+ 重试 | — | 中心节点高亮 | — |
| 公告 Tab: 公告列表 | 公告列表 + 类型筛选 | 列表 skeleton（5 条） | 「暂无公告」 | 「公告加载失败」+ 重试 | 黄色边框提示 | 公告条目高亮 | — |
| Related / Signals / Notes | 关联标的卡片 + 信号列表 + 笔记 | skeleton | 「暂无关联内容」 | 「加载失败」+ 重试 | 黄色边框 | — | — |
| Timeline / Filings | 时间线 + 文件列表 | skeleton | 「暂无记录」 | 「加载失败」+ 重试 | — | 时间节点高亮 | — |


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

### Tab Content Sections

> Calendar 无传统 tab 系统，以下按可交互区域组织。

#### 区域: A 股事件日历
- **子模块**: 月历视图、事件列表视图、事件类型筛选
- **数据字段**: 事件名称/日期/类型/重要性（来源: tushare new_share/share_float/opt_daily/fut_daily/macro/divident/disclosure_date 接口）、关联标的（来源: Instrument Master）
- **交互说明**: 支持月/周/列表视图切换；点击日期查看当日事件详情；重要事件高亮标记（红/橙/黄三级）；事件条目点击跳转到标的详情或 Intelligence

#### 区域: 经济数据日历
- **子模块**: 经济数据时间线、前值/预期/实际值对比、重要性标记
- **数据字段**: 指标名称/发布时间/前值/预期值/实际值（来源: tushare macro 接口 + FRED）、重要性等级（来源: Intelligence Service）
- **交互说明**: 支持按国家/指标类型筛选；实际值发布后与前值/预期值对比高亮；超预期数据绿色标记，不及预期红色标记

#### 区域: Filter Bar
- **子模块**: 事件类型多选、市场范围、重要性等级、时间范围
- **数据字段**: 事件类型枚举（来源: 系统配置）、市场枚举（来源: 系统配置）
- **交互说明**: 筛选条件实时过滤日历显示；支持组合筛选；重置按钮一键清除

### Overlay Registry

#### Overlay: 事件详情 — Drawer
- **触发条件**: 用户点击日历中的事件条目
- **内容结构**: 事件标题 + 日期/时间 + 类型 + 重要性 + 详细描述 + 关联标的列表 + 跳转按钮
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 日历提醒设置 — Sheet
- **触发条件**: 用户点击「加入日历提醒」按钮
- **内容结构**: 提醒时间选择（提前 1 天/当天/提前 1 小时） + 提醒方式（站内/邮件） + 确认/取消
- **关闭行为**: 点击遮罩 / ESC / 确认后自动关闭 + Toast 提示

#### Overlay: 跳转 Intelligence — Modal
- **触发条件**: 用户点击「跳转到 Intelligence」按钮
- **内容结构**: 提示文案（将携带当前事件上下文跳转）+ 确认跳转/取消
- **关闭行为**: 点击遮罩 / ESC / 确认后跳转

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| 月历视图 | 渲染日历网格 + 事件标记 | 日历 skeleton | 「所选范围内无事件」 | 「日历加载失败」+ 重试 | 事件标记变灰 + 时戳提示 | 日期单元格高亮 + 侧边事件列表 | — |
| 事件列表 | 渲染事件条目列表 | 列表 skeleton（8 条） | 「暂无匹配事件」+ 调整筛选 CTA | 「事件加载失败」+ 重试 | 黄色边框提示 | 事件条目高亮 | 批量设置提醒 |
| 经济数据时间线 | 渲染数据点 + 前值/预期 | skeleton | 「无经济数据发布」 | 「数据加载失败」+ 重试 | 数据点变灰 + 提示 | 数据点高亮 + 详情浮窗 | — |
| Filter Bar | 展示当前筛选条件 | — | 显示默认条件 | — | — | — | — |


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

### Tab Content Sections

> Research Workspace 无传统 tab 系统，以下按可交互区域组织。

#### 区域: Pulse Strip
- **子模块**: 活跃因子计数、退化因子计数、失败因子计数、队列长度
- **数据字段**: 活跃因子数（来源: Factor Engine）、退化因子数（来源: Factor Monitor）、失败因子数（来源: Factor Monitor）、待审队列长度（来源: Review Queue Service）
- **交互说明**: 各指标实时更新；点击指标跳转到对应区域（如点击退化因子跳转到 Factor Monitor 表并筛选退化状态）；退化/失败指标红色警告

#### 区域: Factor Monitor Table
- **子模块**: 因子列表表格、因子状态标记、因子评分、排序/筛选控件
- **数据字段**: 因子名称/家族（来源: Factor Engine）、IC/IR/Decay/Turnover（来源: Factor Engine）、Coverage（来源: Factor Engine）、健康状态（来源: Factor Monitor）、最近运行时间（来源: Job Service）
- **交互说明**: 支持按列排序；状态筛选（活跃/退化/失败/待审）；点击因子行跳转到 Factor Analysis 页面；行悬停显示因子 KPI 摘要卡片

#### 区域: Recent Runs
- **子模块**: 运行记录列表、运行状态、运行结果摘要
- **数据字段**: 运行名称/类型（来源: Job Service）、状态（来源: Job Service）、开始/结束时间（来源: Job Service）、关键指标摘要（来源: Run Result Service）
- **交互说明**: 支持按类型筛选（回测/策略/实验）；点击运行记录查看详情；运行中状态显示进度条；失败运行红色标记 + 重试按钮

#### 区域: Experiments / Review Queue
- **子模块**: 实验列表、审核队列
- **数据字段**: 实验名称/状态/创建时间（来源: Experiment Service）、审核项/审核状态/提交人（来源: Review Service）
- **交互说明**: 实验列表支持状态筛选（草稿/运行中/完成/失败）；审核队列显示待审项目；点击审核项打开审核流程

#### 区域: Analysis Band
- **子模块**: IC 趋势迷你图、因子宽度指标、因子相关性热力图、笔记区
- **数据字段**: IC 时间序列（来源: Factor Engine）、Breadth 指标（来源: Factor Engine）、因子相关性矩阵（来源: Correlation Service）
- **交互说明**: IC 趋势图支持悬停查看具体值；相关性热力图支持缩放；笔记区支持添加/编辑研究笔记

### Overlay Registry

#### Overlay: 新建回测 — Modal
- **触发条件**: 用户点击「新建回测」按钮
- **内容结构**: 回测名称输入 + 策略/因子选择 + Universe 选择 + 时间范围 + 参数配置 + 提交/取消
- **关闭行为**: 点击遮罩 / ESC / 提交后跳转到回测结果页

#### Overlay: 新建策略 — Modal
- **触发条件**: 用户点击「新建策略」按钮
- **内容结构**: 策略名称输入 + 策略类型选择 + 因子配置 + 参数设置 + 保存/取消
- **关闭行为**: 点击遮罩 / ESC / 保存后自动关闭 + Toast 提示

#### Overlay: 新建实验 — Sheet
- **触发条件**: 用户点击「新建实验」按钮
- **内容结构**: 实验名称 + 假设描述 + 关联因子 + 对照组设置 + 创建/取消
- **关闭行为**: 点击遮罩 / ESC / 创建后跳转到实验详情

#### Overlay: 运行详情 — Drawer
- **触发条件**: 用户点击运行记录条目
- **内容结构**: 运行概况 + 关键指标表格 + 性能图表 + 日志 + 重新运行/导出按钮
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 审核操作 — Modal
- **触发条件**: 用户点击审核队列中的审核项
- **内容结构**: 审核内容摘要 + 审核意见输入 + 通过/驳回按钮（破坏性操作）
- **关闭行为**: 点击遮罩 / ESC / 审核完成后自动关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| Pulse Strip | 渲染四项指标 + 状态色 | 指标 skeleton（4 个） | — | 「因子监控加载失败」+ 重试 | 退化/失败指标闪烁 | 指标卡片高亮 | — |
| Factor Monitor Table | 渲染因子行 + 状态 | 表格 skeleton（10 行） | 「暂无因子数据」 | 「因子数据加载失败」+ 重试 | 行左上角黄色圆点 | 行背景高亮 + KPI 联动 | 批量操作栏: 标记/导出 |
| Recent Runs | 渲染运行记录列表 | 列表 skeleton（5 条） | 「暂无运行记录」+ 新建 CTA | 「运行记录加载失败」+ 重试 | — | 运行条目高亮 | 批量取消/导出 |
| Experiments / Review Queue | 渲染实验列表 + 审核队列 | skeleton | 「暂无实验/审核」 | 「加载失败」+ 重试 | — | 条目高亮 | 批量审核操作 |
| Analysis Band: IC 趋势 | 渲染迷你折线图 | 图表 skeleton | 「暂无 IC 数据」 | 「图表加载失败」 | 黄色边框 + 时戳 | — | — |
| Analysis Band: 相关性 | 渲染热力图 | 热力图 skeleton | 「暂无相关性数据」 | 「加载失败」 | 黄色边框提示 | 单元格高亮 | — |


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

### Tab Content Sections

#### Tab: IC（信息系数）
- **子模块**: IC 时间序列图、IC 均值/标准差/IR 统计、IC 分位数分布、IC 滚动窗口分析
- **数据字段**: 日频 IC 序列（来源: Factor Engine）、IC 均值/标准差/IR（来源: Factor Engine）、IC 分位数（来源: Factor Engine）
- **交互说明**: 时间序列支持缩放/平移；滚动窗口大小可调（60D/120D/250D）；IC 统计支持按市场态（Regime）分组查看

#### Tab: 收益（Returns）
- **子模块**: 因子分组收益图、多空组合净值曲线、分组收益率热力图、收益统计表
- **数据字段**: 分组收益率序列（来源: Factor Engine）、多空净值曲线（来源: Factor Engine）、月度收益矩阵（来源: Factor Engine）
- **交互说明**: 分组数量可调（5/10 分组）；多空组合支持选择基准；收益热力图按月度展示；点击单元格查看详情

#### Tab: 分布与相关（Distribution & Correlation）
- **子模块**: 因子值分布直方图、因子间相关性矩阵、因子与收益散点图、因子衰减分析
- **数据字段**: 因子值分布（来源: Factor Engine）、相关性矩阵（来源: Correlation Service）、因子-收益散点（来源: Factor Engine）、衰减系数（来源: Factor Engine）
- **交互说明**: 分布直方图支持正态拟合叠加；相关性矩阵支持按阈值高亮；散点图支持回归线叠加

#### Tab: 换手（Turnover）
- **子模块**: 换手率时间序列、换手率分解（进入/退出）、持仓稳定性指标、换手成本估算
- **数据字段**: 换手率序列（来源: Factor Engine）、进入/退出换手（来源: Factor Engine）、持仓稳定性（来源: Factor Engine）
- **交互说明**: 换手率支持按频率切换（日/周/月）；换手成本估算支持自定义交易成本参数

### Overlay Registry

#### Overlay: 加入回测 — Sheet
- **触发条件**: 用户点击「加入回测」按钮
- **内容结构**: 目标回测选择（已有回测/新建回测） + 权重配置 + 确认/取消
- **关闭行为**: 点击遮罩 / ESC / 确认后自动关闭 + Toast 提示

#### Overlay: 加入实验 — Sheet
- **触发条件**: 用户点击「加入实验」按钮
- **内容结构**: 目标实验选择（已有实验/新建实验） + 变量角色（实验组/对照组） + 确认/取消
- **关闭行为**: 点击遮罩 / ESC / 确认后自动关闭 + Toast 提示

#### Overlay: 发送 AI 解读 — Sheet
- **触发条件**: 用户点击「发送 AI 解读」按钮
- **内容结构**: 解读维度选择（IC/收益/风险/综合） + 附加上下文输入 + 发送/取消
- **关闭行为**: 点击遮罩 / ESC / 发送后自动关闭 + 跳转到 AI 解读结果

#### Overlay: 2x2 诊断详情 — Modal
- **触发条件**: 用户点击 2x2 诊断中的任一象限
- **内容结构**: 放大视图 + 详细数据表格 + 导出按钮 + 关闭按钮
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| Factor Header | 显示因子名称/家族/状态 | 标题 skeleton | — | 「因子信息加载失败」+ 重试 | 黄色脉冲提示 | — | — |
| KPI Strip | 渲染 IC/IR/Decay/Turnover/Coverage | 指标 skeleton（5 个） | 「暂无 KPI 数据」 | 「KPI 加载失败」+ 重试 | 指标值黄色闪烁 | — | — |
| IC Tab: 时间序列 | 渲染 IC 折线图 + 统计 | 图表 skeleton | 「暂无 IC 数据」 | 「IC 数据加载失败」+ 重试 | 黄色边框 + 时戳 | 数据点高亮 + tooltip | — |
| IC Tab: 分位数 | 渲染分位数分布图 | 图表 skeleton | 「暂无分位数数据」 | 「加载失败」+ 重试 | 黄色边框 | 柱状高亮 | — |
| 收益 Tab: 分组图 | 渲染分组收益折线 | 图表 skeleton | 「暂无收益数据」 | 「收益数据加载失败」+ 重试 | 黄色边框 + 时戳 | 分组线高亮 | — |
| 收益 Tab: 热力图 | 渲染月度收益热力图 | 热力图 skeleton | 「暂无数据」 | 「加载失败」+ 重试 | 黄色边框 | 单元格高亮 | — |
| 分布与相关 Tab: 直方图 | 渲染分布直方图 | 图表 skeleton | 「暂无分布数据」 | 「加载失败」+ 重试 | 黄色边框 | 柱状高亮 | — |
| 分布与相关 Tab: 相关矩阵 | 渲染相关性热力矩阵 | 矩阵 skeleton | 「暂无相关性数据」 | 「加载失败」+ 重试 | 黄色边框 | 单元格高亮 | — |
| 换手 Tab: 序列图 | 渲染换手率折线 | 图表 skeleton | 「暂无换手数据」 | 「换手数据加载失败」+ 重试 | 黄色边框 + 时戳 | 数据点高亮 | — |
| 2x2 Diagnostics | 渲染四象限诊断图 | 四象限 skeleton | 「暂无诊断数据」 | 「诊断数据加载失败」+ 重试 | 黄色边框 | 象限高亮 | — |
| Bottom: 统计表 | 渲染详细统计表格 | 表格 skeleton | 「暂无统计数据」 | 「加载失败」+ 重试 | 黄色边框 | 行高亮 | 批量导出 |


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

### Tab Content Sections

#### Tab: Form Builder（默认）
- **子模块**: 因子选择、因子预处理管道、标的选择（Universe）、权重配置、风控规则、组合优化器（v1.5）
- **数据字段**: 策略名称（来源: 用户输入）、策略版本（来源: 系统自增）、因子列表（来源: Factor Library）、预处理配置（来源: 预设默认值 + 用户覆盖）、Universe 标的池（来源: Market Data）、权重分配（来源: 手动/优化器）、风控阈值（来源: Risk Rules）、回测参数区间（来源: 用户输入）
- **交互说明**: 左侧 Snippets 面板拖拽因子到工作区；因子选中后自动展开预处理管道配置面板（去极值→标准化→中性化→正交化）；权重支持手动输入或启用优化器模式；Inspector 面板实时显示当前配置的 AI 建议和校验警告；底部 Logs 面板显示编译/校验/Dry Run 结果

#### Tab: Code Editor
- **子模块**: Monaco 代码编辑器、代码片段库、语法校验、版本对比
- **数据字段**: 策略代码（来源: 用户编辑 / 从 Form Mode 转换）、代码片段（来源: Snippets 库）、语法错误（来源: 校验引擎）、版本 diff（来源: Git-like 版本管理）
- **交互说明**: 支持 Form → Code 和 Code → Form 双向切换；Monaco 编辑器支持语法高亮和自动补全；保存时自动触发语法校验；Inspector 显示 AI 代码建议

### Overlay Registry

#### Overlay: 策略保存 — Modal
- **触发条件**: 用户点击 Header "保存" 按钮 或 Ctrl+S
- **内容结构**: 策略名称 + 版本备注 + 保存类型（新版本/覆盖当前版本） + [取消] [确认保存]
- **关闭行为**: 点击遮罩 / ESC / 确认保存后自动关闭

#### Overlay: 回测参数配置 — Sheet（右侧）
- **触发条件**: 用户点击 Header "提交回测" 按钮
- **内容结构**: 回测区间（起始/结束日期）、初始资金、基准指数、交易成本配置（印花税/佣金/滑点/冲击成本）、调仓频率 + [取消] [提交回测]
- **关闭行为**: 点击遮罩 / ESC / 提交后自动关闭

#### Overlay: 因子预处理预览 — Drawer
- **触发条件**: 用户在预处理管道配置中点击"预览处理后分布"
- **内容结构**: Distribution 直方图（处理前 vs 处理后叠加）、统计摘要（均值/标准差/偏度/峰度） + [关闭]
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 校验结果 — Toast + Inline
- **触发条件**: 用户点击 Header "校验" 按钮
- **内容结构**: 校验通过/失败摘要（Toast）；失败时 Inspector 面板展示具体错误列表
- **关闭行为**: Toast 自动消失（3s）；Inline 错误需用户手动修正

#### Overlay: 确认策略删除 — Modal（破坏性操作）
- **触发条件**: 用户在策略管理中执行删除操作
- **内容结构**: 警告图标 + "确认删除策略 [策略名] 及其所有版本？" + [取消] [确认删除]
- **关闭行为**: 点击遮罩 / ESC / 取消按钮 / 确认删除后自动关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| 因子选择列表 | 因子卡片列表，可拖拽 | skeleton 卡片 × 6 | "暂无可用因子，请先在 Factor Library 创建" + CTA | 错误提示 + [重试] | 黄色边框 "因子数据可能已更新" | 选中因子高亮 + 勾选标记，Inspector 联动 | 批量选择后出现操作栏：删除/预览/添加到管道 |
| 预处理管道 | 步骤流程图，每步显示当前配置 | — | — | 校验失败标记步骤为红色 + 错误提示 | — | 点击步骤展开配置面板 | — |
| Universe 标的池 | 表格/网格展示标的列表 | skeleton 行 × 10 | "请配置 Universe，或从模板加载" + 模板选择 CTA | 错误提示 + [重试] | — | 选中标的高亮 | 批量添加/移除标的 |
| 权重配置 | 权重滑块/输入框 | skeleton 行 × 5 | "请先选择 Universe 标的" | — | — | — | — |
| Inspector 面板 | AI 建议 + 校验状态列表 | spinner + "分析中..." | "配置策略后，AI 将提供优化建议" | 错误提示 + [重试] | "AI 分析结果可能已过时，点击刷新" | — | — |
| Logs 底部面板 | 空白待输出状态 | — | "暂无日志，执行校验或 Dry Run 后在此查看" | — | — | — | — |

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


### Tab Content Sections

#### Tab: 概览（默认）
- **子模块**: KPI Strip（Sharpe/年化收益/最大回撤/胜率/换手率/总费用）、NAV 曲线与回撤叠加图、关键统计摘要
- **数据字段**: Sharpe Ratio（来源: 回测引擎）、年化收益率（来源: 回测引擎）、最大回撤（来源: 回测引擎）、胜率（来源: 回测引擎）、换手率（来源: 回测引擎）、总交易费用（来源: 交易成本明细）、回测区间（来源: 用户配置）、基准对比（来源: 基准指数数据）
- **交互说明**: KPI Strip 支持 tooltip 展示详细计算方式；NAV 曲线支持缩放/平移/拖拽选取时间段；点击 KPI 卡片可下钻到对应 tab

#### Tab: 收益曲线
- **子模块**: 累计收益曲线、超额收益曲线（vs 基准）、月度收益热力图、滚动收益统计
- **数据字段**: 日频净值序列（来源: 回测引擎 §11.1）、基准净值序列（来源: Market Data）、月度收益率（来源: 回测引擎）、滚动 N 日收益（来源: 回测引擎）
- **交互说明**: 收益曲线与基准可切换显示/隐藏；月度热力图 hover 显示具体数值；支持导出 CSV

#### Tab: 交易记录
- **子模块**: 交易明细表格、交易时间线、交易成本汇总
- **数据字段**: 交易 ID（来源: 回测引擎）、标的/代码（来源: Market Data）、方向/数量/价格（来源: 回测引擎）、成交时间（来源: 回测引擎）、交易成本（来源: 交易成本明细：印花税/佣金/滑点/冲击成本）
- **交互说明**: 表格支持排序和筛选（按标的/方向/时间）；点击单笔交易查看详细信息；底部显示交易成本汇总表

#### Tab: 风险分析
- **子模块**: 回撤曲线、VaR/CVaR 分布、波动率走势、相关性矩阵、最大回撤区间标注
- **数据字段**: 回撤序列（来源: 回测引擎）、日度收益率分布（来源: 回测引擎）、VaR/CVaR（来源: 风险计算引擎）、滚动波动率（来源: 回测引擎）、持仓相关性矩阵（来源: 回测引擎）
- **交互说明**: 回撤曲线上标注 Top N 最大回撤区间，点击可查看回撤详情；VaR 图表支持置信度切换（95%/99%）

#### Tab: 因子暴露
- **子模块**: 因子暴露时间序列、因子收益贡献、Barra 风格因子暴露热力图
- **数据字段**: 因子暴露值（来源: 因子引擎）、因子收益贡献（来源: 归因引擎）、风格因子暴露（来源: Barra 模型）、行业暴露（来源: 行业分类数据）
- **交互说明**: 时间序列支持选取时间段查看暴露变化；热力图 hover 显示具体暴露值；支持与 Factor Hub 页面联动

#### Tab: 持仓分析
- **子模块**: 持仓分布饼图、Top N 重仓股列表、行业分布、个股贡献度、持仓集中度指标
- **数据字段**: 持仓列表（标的/权重/市值/成本价）（来源: 回测引擎）、行业权重（来源: 行业分类数据）、个股贡献度（来源: 归因引擎）、集中度指标（HHI/前 N 占比）（来源: 回测引擎）
- **交互说明**: 饼图/柱状图交互式展示分布；Top N 重仓股支持点击跳转到标的详情页；行业分布支持层级下钻

#### Tab: 诊断
- **子模块**: 换手率分析、交易频率分布、持仓周期分布、异常交易标记
- **数据字段**: 日度/周度换手率（来源: 回测引擎）、交易频率统计（来源: 回测引擎）、持仓周期（来源: 回测引擎）、异常交易标记（来源: 异常检测引擎）
- **交互说明**: 换手率图表支持叠加策略调仓日标记；异常交易高亮显示并支持查看原因

### Overlay Registry

#### Overlay: 导出报告 — Sheet（右侧）
- **触发条件**: 用户点击 Header "导出报告" 按钮
- **内容结构**: 导出格式选择（PDF/Excel/CSV）+ 内容范围选择（全部/当前 tab）+ 包含图表勾选 + [取消] [导出]
- **关闭行为**: 点击遮罩 / ESC / 导出后自动关闭

#### Overlay: 加入对比 — Toast
- **触发条件**: 用户点击 "加入对比" 按钮
- **内容结构**: "已加入对比队列（N/5）" + [查看对比]
- **关闭行为**: Toast 自动消失（3s）；点击"查看对比"跳转 Compare 视图

#### Overlay: 启用信号确认 — Modal
- **触发条件**: 用户点击 "启用信号" 按钮（仅关键指标达标时可点击）
- **内容结构**: 信号启用摘要（策略名/回测版本/达标指标）+ 信号参数配置（频率/阈值）+ 风险提示 + [取消] [确认启用]
- **关闭行为**: 点击遮罩 / ESC / 确认后自动关闭

#### Overlay: AI 解读 — Sheet（右侧）
- **触发条件**: 用户点击 "发送 AI 解读" 按钮
- **内容结构**: AI 生成的回测分析报告（摘要/优势/风险/建议）+ 参考指标 + [关闭] [复制]
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: Compare 视图 — 全屏覆盖
- **触发条件**: 用户点击 "查看对比" 按钮 或在 Compare 模式中操作
- **内容结构**: 净值叠加图 + 指标对比表 + 持仓差异分析 + [导出] [关闭]
- **关闭行为**: 点击"关闭"按钮 / ESC；最多支持 5 个回测版本对比

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| KPI Strip | 6 个 KPI 卡片，关键指标高亮 | skeleton 卡片 × 6 | — | "回测数据加载失败" + [重试] | 黄色边框 "数据非最新" | 点击 KPI 卡片高亮并切换到对应 tab | — |
| NAV 曲线图 | 净值 + 回撤叠加图，支持缩放/平移 | skeleton 图表占位 | — | "图表渲染失败" + [重试] | — | 拖拽选取时间段，联动底部数据 | — |
| 交易明细表 | 分页表格，支持排序/筛选 | skeleton 行 × 10 | "回测期间无交易记录" | 错误提示 + [重试] | — | 选中行高亮，右侧展示交易详情 | 批量导出选中交易 |
| 风险分析图表 | 回撤/VaR/波动率图表组 | skeleton 图表组 × 4 | "无风险数据" | 错误提示 + [重试] | — | 点击回撤区间查看详情 | — |
| 因子暴露图表 | 时间序列 + 热力图 | skeleton 图表组 × 3 | "未配置因子暴露分析" | 错误提示 + [重试] | — | hover 暴露值 tooltip | — |
| 持仓分析图表 | 饼图 + 重仓股列表 + 行业分布 | skeleton 图表组 × 3 | "无持仓数据" | 错误提示 + [重试] | — | 点击个股跳转标的详情 | — |

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


### Tab Content Sections

#### Tab: 交易模式（默认）
- **子模块**: Session Strip（交易阶段指示器 + 资金/保证金/风险预算/路由健康度 + 两融数据）、Equity/PnL 实时盈亏、Risk/Alerts 风控预警、Positions Summary 持仓汇总（含 T+1 冻结标识）、Signal Queue 信号队列、Order Status 订单状态、Recent Trades/Exceptions 近期成交与异常
- **数据字段**: 交易阶段（来源: 交易所时间表）、可用资金（来源: Broker API）、保证金占用（来源: Broker API）、风险预算余额（来源: Risk Engine）、路由健康状态（来源: Order Router）、融资余额/融券余额/担保比例（来源: 两融接口）、实时 PnL（来源: 持仓数据 + Market Data）、持仓列表（标的/数量/成本/市值/T+1 状态）（来源: Position Engine）、待处理信号数（来源: Signal Engine）、订单状态统计（来源: Order Engine）
- **交互说明**: Session Strip 实时更新交易阶段（集合竞价/连续竞价/午休/收盘集合竞价/盘后交易）；Equity/PnL 支持时间框架切换（日/周/月）；Positions Summary 中当日买入数量标灰显示"不可卖"；点击持仓跳转到标的详情；Risk/Alerts 实时推送风控预警；Signal Queue 可快速操作信号（查看/确认/忽略）

#### Tab: 复盘模式（Review Mode，收盘后自动切换）
- **子模块**: 当日交易摘要、当日归因（行业贡献/个股贡献/因子贡献）、持仓健康检查（涨跌停风险/异常波动/偏离成本）、明日策略预演（重大事件/Regime 判断/待确认信号回顾）
- **数据字段**: 当日盈亏总额（来源: Position Engine）、行业贡献明细（来源: 归因引擎）、个股贡献明细（来源: 归因引擎）、因子贡献明细（来源: 归因引擎）、明日涨跌停风险持仓（来源: Risk Engine）、偏离成本 >5% 持仓（来源: Position Engine）、两融担保比例（来源: 两融接口）、明日重大事件（来源: Calendar）、Regime 判断（来源: Regime Engine）、待确认信号列表（来源: Signal Engine）
- **交互说明**: 收盘后（15:00 后）自动切换，用户可手动关闭；当日归因区块支持 drill-down 查看行业/个股/因子贡献详情；持仓健康检查高亮风险持仓；明日策略预演提供可操作的建议（预挂单/调整仓位）

### Overlay Registry

#### Overlay: 暂停交易确认 — Modal（破坏性操作）
- **触发条件**: 用户点击 Header "暂停交易" 按钮
- **内容结构**: 警告图标 + "确认暂停交易？暂停后所有新订单将被拦截，已挂未成交订单不会被自动撤销。" + [取消] [确认暂停]
- **关闭行为**: 点击遮罩 / ESC / 取消按钮 / 确认暂停后自动关闭

#### Overlay: 持仓详情 — Sheet（右侧）
- **触发条件**: 用户在 Positions Summary 点击某只持仓
- **内容结构**: 标的详细信息（代码/名称/现价/涨跌幅）、持仓信息（数量/成本/市值/盈亏）、T+1 状态、当日成交记录、关联信号 + [关闭]
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 风控预警详情 — Drawer
- **触发条件**: 用户在 Risk/Alerts 点击某条预警
- **内容结构**: 预警类型/级别/触发时间、详细描述、影响范围、建议操作 + [关闭]
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 涨跌停标的状态概览 — Sheet（右侧）
- **触发条件**: 用户点击 Header "涨跌停标的状态概览" 按钮
- **内容结构**: 涨停/跌停/接近涨跌停标的列表（标的/价格/涨跌幅/原因） + [关闭]
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| Session Strip | 交易阶段指示器 + 资金/风险/路由指标 | skeleton 指标条 | — | "交易数据连接失败" + [重试] | 黄色边框 "数据延迟" | — | — |
| Equity/PnL | 实时盈亏图 + 数字显示 | skeleton 图表 + 数字 | "交易时段内无持仓" | 错误提示 + [重试] | 黄色边框 "数据延迟" | — | — |
| Risk/Alerts | 风险指标卡片 + 预警列表 | skeleton 卡片 × 4 | "当前无风险预警" | 错误提示 + [重试] | 红色边框闪烁 "预警数据可能过期" | 点击预警高亮展开 | — |
| Positions Summary | 持仓表格，T+1 标灰 | skeleton 行 × 8 | "当前无持仓" | 错误提示 + [重试] | 黄色边框 "持仓数据延迟" | 选中行高亮，右侧展开详情 | 批量操作：批量平仓/批量调整 |
| Signal Queue | 待处理信号计数 + 最近信号列表 | skeleton 行 × 5 | "暂无待处理信号" | 错误提示 + [重试] | — | 点击信号跳转 Signals Inbox | — |
| Order Status | 订单状态统计（待提交/已提交/部分成交/已完成/失败） | skeleton 卡片 × 5 | "今日无订单" | 错误提示 + [重试] | — | 点击状态过滤 Orders Ledger | — |
| 当日归因（Review） | 行业/个股/因子贡献柱状图 | skeleton 图表 × 3 | "今日无归因数据" | 错误提示 + [重试] | — | 点击贡献项 drill-down | — |
| 持仓健康检查（Review） | 风险持仓列表 + 状态标记 | skeleton 行 × 5 | "所有持仓状态正常" | 错误提示 + [重试] | — | 点击持仓查看详情 | — |

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


### Tab Content Sections

#### Tab: 待复核（默认）
- **子模块**: Scope Strip（待复核/已确认/已忽略/已转订单）、Signal Table（时间/标的/来源/方向/权重/置信度/状态）、Signal Detail（解释/风控检查/组合影响/操作）
- **数据字段**: 信号 ID（来源: Signal Engine）、信号时间（来源: Signal Engine）、标的代码/名称（来源: Market Data）、信号来源（来源: Signal Engine：策略信号/AI 信号/手动信号）、方向/权重/置信度（来源: Signal Engine）、状态（来源: Signal Engine）、风控检查结果（来源: Risk Engine）、组合影响预估（来源: Portfolio Engine）
- **交互说明**: 表格支持排序和筛选（按来源/状态/优先级/组合）；点击信号行展开 Signal Detail；涨跌停校验不通过的信号标灰（涨停买入/跌停卖出跳过）；支持批量确认/忽略；Signal Detail 中提供溯源链接（查看来源回测 → /research/backtest/[id]，查看来源策略 → /research/strategies/[id]/studio）

#### Tab: 已确认
- **子模块**: 已确认信号列表、确认时间、操作人、后续状态
- **数据字段**: 信号 ID（来源: Signal Engine）、确认时间（来源: 审计日志）、操作人（来源: 用户系统）、后续状态（来源: Signal Engine：已转订单/待处理）
- **交互说明**: 已确认信号可取消确认；点击可查看完整 Signal Detail

#### Tab: 已忽略
- **子模块**: 已忽略信号列表、忽略原因、忽略时间
- **数据字段**: 信号 ID（来源: Signal Engine）、忽略原因（来源: 用户输入）、忽略时间（来源: 审计日志）
- **交互说明**: 已忽略信号可恢复；支持按忽略原因筛选

#### Tab: 已转订单
- **子模块**: 已转订单信号列表、关联订单 ID、订单状态、执行进度
- **数据字段**: 信号 ID（来源: Signal Engine）、关联订单 ID（来源: Order Engine）、订单状态（来源: Order Engine）、执行进度（来源: Order Engine）
- **交互说明**: 点击关联订单 ID 跳转 Orders/Execution Ledger；点击信号可查看原始 Signal Detail

### Overlay Registry

#### Overlay: 订单确认面板 — Sheet（右侧，Signal Detail 区域内展开）
- **触发条件**: 用户在 Signal Detail 点击"生成订单复核" 或 确认信号后自动弹出
- **内容结构**: 标的信息（代码/名称/方向/数量）、标的状态检查（正常交易/停牌/退市/涨跌停/T+1 冻结/两融约束/价格合理性）、委托配置（委托类型/委托价格/委托数量）、预估费用（佣金/过户费/印花税/预估总额）+ [取消] [确认提交订单]
- **关闭行为**: 点击遮罩 / ESC / 取消按钮 / 确认提交后自动关闭；阻断项（停牌/涨停买入/跌停卖出/T+1 不可卖/担保比例不足）阻断下单并显示原因
- **状态检查规则**: 标的状态（正常交易 vs 停牌/退市阻断）、涨跌停（可成交 vs 涨停买入/跌停卖出阻断）、T+1 冻结（可卖出 vs 当日买入标的卖出阻断）、两融约束（担保比例 >= 130% vs < 130% 阻断）、价格合理性（范围内 vs 超出范围自动修正）

#### Overlay: AI 解读信号 — Sheet（右侧）
- **触发条件**: 用户点击 "交给 AI 解读" 按钮
- **内容结构**: AI 生成的信号分析（市场背景/标的分析/风险评估/建议操作）+ 置信度评分 + [关闭] [采纳建议]
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 批量确认 — Modal
- **触发条件**: 用户勾选多条信号后点击批量确认
- **内容结构**: 已选信号摘要（N 条信号，总权重/总金额）+ 风控批量检查结果 + [取消] [确认全部]
- **关闭行为**: 点击遮罩 / ESC / 取消按钮 / 确认后自动关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| Signal Table | 分页表格，信号行可点击展开 | skeleton 行 × 10 | "暂无信号，等待策略/AI 生成" + 查看策略 CTA | 错误提示 + [重试] | 黄色边框 "信号可能已更新，建议刷新" | 选中行高亮，右侧展开 Signal Detail | 勾选后出现批量操作栏：确认/忽略/AI 解读 |
| Signal Detail | 信号解释 + 风控检查 + 组合影响 + 操作按钮 | skeleton 面板 | "选择左侧信号查看详情" | 错误提示 + [重试] | — | — | — |
| Scope Strip | 状态 tab + 各状态计数 badge | skeleton tab × 4 | — | — | — | — | — |
| 订单确认面板 | 标的信息 + 状态检查 + 委托配置 + 费用预估 | spinner + "检查中..." | — | 检查失败标记 + [重试] | — | — | — |
| 涨跌停校验标识 | 信号行状态列显示校验结果 | — | — | — | — | 不通过信号标灰 + tooltip 说明原因 | — |

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


### Tab Content Sections

#### Tab: 待提交（默认）
- **子模块**: Orders Header（会话/账户/路由/筛选器）、Status Strip（待提交/已提交/部分成交/已完成/失败已撤单）、Orders Ledger Table（订单 ID/标的/方向/数量/价格/类型/状态/账户/时间）、Order Trace（状态时间线/拒绝原因/费用/滑点/路由日志）
- **数据字段**: 订单 ID（来源: Order Engine）、标的代码/名称（来源: Market Data）、方向（来源: Order Engine）、委托数量/价格（来源: Order Engine）、订单类型（来源: Order Engine：限价/市价）、状态（来源: Order Engine）、关联账户（来源: Account System）、创建时间（来源: Order Engine）、更新时间（来源: Order Engine）
- **交互说明**: 表格支持排序和筛选（按状态/标的/时间/账户）；点击订单行展开 Order Trace；待提交状态支持修改参数后重新提交；Status Strip 显示各状态订单计数

#### Tab: 已提交
- **子模块**: 已提交订单列表、提交时间、券商确认状态、等待时间
- **数据字段**: 订单 ID（来源: Order Engine）、提交时间（来源: Order Engine）、券商确认状态（来源: Broker API）、等待时长（来源: Order Engine）
- **交互说明**: 已提交未确认的订单可撤单；超时未确认的订单高亮警告

#### Tab: 部分成交
- **子模块**: 部分成交订单列表、成交进度条、已成交/未成交数量、平均成交价
- **数据字段**: 订单 ID（来源: Order Engine）、已成交数量（来源: Broker API）、未成交数量（来源: Order Engine）、平均成交价（来源: Broker API）、成交笔数（来源: Broker API）
- **交互说明**: 进度条实时更新；部分成交订单可撤剩余未成交部分

#### Tab: 已完成
- **子模块**: 已完成订单列表、成交明细、实际费用（佣金/印花税/过户费）、滑点分析
- **数据字段**: 订单 ID（来源: Order Engine）、成交价格/数量/时间（来源: Broker API）、实际费用明细（来源: Broker API）、滑点（来源: Order Engine：委托价 vs 成交价）
- **交互说明**: 点击订单查看完整成交明细和费用分析；滑点异常订单高亮

#### Tab: 失败 / 已撤单
- **子模块**: 失败/已撤单列表、失败原因、撤单时间、撤单人
- **数据字段**: 订单 ID（来源: Order Engine）、失败/撤单原因（来源: Order Engine）、撤单时间（来源: Order Engine）、撤单人（来源: 用户系统）
- **交互说明**: 失败订单支持查看详细拒绝原因；支持重试提交失败订单；已撤单订单可查看撤单操作审计记录

### Overlay Registry

#### Overlay: 撤单确认 — Modal（破坏性操作）
- **触发条件**: 用户对已提交/部分成交订单点击"撤单"按钮
- **内容结构**: 警告图标 + 订单摘要（标的/方向/数量/状态）+ "确认撤销此订单？部分成交部分将被保留（如有），未成交部分将被取消。" + [取消] [确认撤单]
- **关闭行为**: 点击遮罩 / ESC / 取消按钮 / 确认撤单后自动关闭

#### Overlay: 重试提交 — Modal
- **触发条件**: 用户对失败订单点击"重试"按钮
- **内容结构**: 原始订单参数 + 失败原因 + 可修改参数（价格/数量）+ 风控检查结果 + [取消] [重新提交]
- **关闭行为**: 点击遮罩 / ESC / 取消按钮 / 重新提交后自动关闭

#### Overlay: 订单详情 — Sheet（右侧）
- **触发条件**: 用户在 Orders Ledger Table 点击某条订单
- **内容结构**: 订单完整信息（ID/标的/方向/数量/价格/类型）、状态时间线（创建→提交→确认→部分成交/完成/失败）、费用明细、滑点分析、路由日志 + [关闭]
- **关闭行为**: 点击遮罩 / ESC / 点击关闭按钮

#### Overlay: 批量撤单确认 — Modal（破坏性操作）
- **触发条件**: 用户勾选多条订单后点击批量撤单
- **内容结构**: 警告图标 + "确认撤销 N 条订单？" + 已选订单摘要列表 + [取消] [确认批量撤单]
- **关闭行为**: 点击遮罩 / ESC / 取消按钮 / 确认后自动关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| Status Strip | 状态 tab + 各状态计数 badge | skeleton tab × 5 | — | — | — | — | — |
| Orders Ledger Table | 分页表格，订单行可点击展开 | skeleton 行 × 10 | "当前无订单" | 错误提示 + [重试] | 黄色边框 "订单状态可能已更新" | 选中行高亮，右侧展开 Order Trace | 勾选后出现批量操作栏：撤单/重试/导出 |
| Order Trace | 状态时间线 + 费用明细 + 路由日志 | skeleton 时间线 | "选择左侧订单查看追踪" | 错误提示 + [重试] | — | — | — |
| 撤单按钮 | 仅对已提交/部分成交状态可点击 | — | — | — | — | — | 批量撤单 Modal |
| 重试按钮 | 仅对失败状态可点击 | — | — | — | — | — | 批量重试 Modal |
| 成交进度条 | 部分成交 tab 下显示进度 | skeleton 进度条 | — | — | — | — | — |

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

### Tab Content Sections

#### Tab: Risk Overview（默认）
- **子模块**: Risk Strip（VaR / MaxDD / Beta / Gross / Net / Near-Limit / Breach）、Main Risk Charts（VaR 时间线 / 回撤曲线 / 敞口分布）、Active Breaches
- **数据字段**: VaR（来源: Risk Engine 实时计算）、Max Drawdown（来源: Risk Engine 历史模拟）、Beta（来源: Barra 风险模型）、Gross Exposure（来源: 组合持仓聚合）、Net Exposure（来源: 组合持仓聚合）、Breach Count（来源: 风控规则引擎）
- **交互说明**: Risk Strip 支持点击指标展开详情；Main Charts 支持时间范围切换（1D / 5D / 1M / 3M / YTD）；Active Breaches 列表项可点击跳转到对应持仓

#### Tab: Stress Test
- **子模块**: Stress Scenario 选择器、Stress Test Summary 表格、历史 Stress Test 结果对比
- **数据字段**: Scenario 名称（来源: 预设场景库）、Impact PnL（来源: Stress Engine）、Max Loss（来源: Stress Engine）、Affected Positions（来源: 组合持仓）
- **交互说明**: 下拉选择预设场景或自定义场景参数；点击"运行测试"触发异步计算；结果支持与历史压力测试对比叠加

#### Tab: Incident Timeline
- **子模块**: Timeline 视图、Incident Detail 面板、处理日志
- **数据字段**: Incident ID（来源: 风控事件表）、Severity（来源: 事件分级规则）、Status（来源: 事件处理状态）、Handler（来源: 用户系统）、Resolution（来源: 事件处理记录）
- **交互说明**: Timeline 支持按时间 / 严重度筛选；点击事件条目展开 Detail 面板；支持标记处理状态和添加备注

### Overlay Registry

#### Overlay: Stress Test Config — Sheet
- **触发条件**: 用户点击"运行测试"按钮时
- **内容结构**: 标题 + Scenario 选择（预设 / 自定义）+ 参数配置区域（冲击幅度 / 持续时间 / 标的范围）+ "确认运行"按钮
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 提交后自动关闭并显示计算进度 Toast

#### Overlay: Breach Detail — Drawer
- **触发条件**: 用户点击 Active Breaches 中的某条违规记录时
- **内容结构**: 标题（规则名称）+ 违规详情（当前值 / 阈值 / 偏离度）+ 涉及持仓列表 + "调整规则" / "查看持仓"按钮
- **关闭行为**: 点击遮罩关闭 / ESC 关闭

#### Overlay: Rule Editor — Modal
- **触发条件**: 用户点击"调整规则"按钮时
- **内容结构**: 标题 + 规则参数表单（阈值 / 触发条件 / 通知方式）+ "保存" / "取消"按钮
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 保存后自动关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected |
|------|---------|---------|-------|--------|-------|----------|
| Risk Strip | 指标卡片显示实时数值，Breach 高亮红色 | 骨架屏闪烁，指标区域灰色占位 | 无（页面必有默认组合） | "风险数据加载失败" + 重试按钮 | 数值旁黄色圆点 + "数据延迟于 HH:MM" | 点击展开指标趋势 Sparkline |
| Main Risk Charts | 图表渲染完成，支持缩放和 Tooltip | 图表区域骨架屏动画 | "暂无风险数据，请先配置组合" | "图表渲染失败" + 重试按钮 | 图表右上角黄色提示 + "最后更新于 HH:MM" | 交叉线 + 数据 Tooltip |
| Active Breaches | 违规列表，严重度色标 + 摘要 | 列表行骨架屏 | "当前无违规项" 绿色提示 | "违规数据加载失败" + 重试按钮 | 列表顶部黄色提示条 | 高亮行 + 右侧展开 Detail |
| Stress Test Summary | 表格展示各场景 Impact + 受影响持仓 | 表格行骨架屏 | "暂无压力测试记录，点击运行测试" | "计算引擎异常" + 重试按钮 | 不适用 | 高亮行 + 联动 Charts |
| Incident Timeline | 时间线渲染，事件按严重度着色 | 时间线骨架 | "暂无事件记录" | "事件加载失败" + 重试按钮 | 不适用 | 事件条目展开 Detail |

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

### Tab Content Sections

#### Tab: Market Analysis（默认模式）
- **子模块**: 对话区（Conversation）、结构化输出（Structured Output）、上下文面板（Context）
- **数据字段**: 市场分析结论（来源: LLM 生成）、引用数据源（来源: Copilot Evidence Store）、保存笔记（来源: Notes Store）
- **交互说明**: 输入问题后 Copilot 流式输出；结构化结论可保存为笔记或发送到 Research Workspace

#### Tab: Stock Discovery
- **子模块**: 对话区、筛选结果列表、个股详情卡
- **数据字段**: 筛选条件（来源: 用户输入 + LLM 解析）、候选个股列表（来源: Stock Screener Engine）、匹配逻辑（来源: LLM 推理）
- **交互说明**: 自然语言输入筛选需求；候选列表支持排序和追加条件；个股卡可跳转到 Instrument Hub

#### Tab: Strategy Draft
- **子模块**: 对话区、策略草案编辑器、参数面板
- **数据字段**: 策略草案（来源: LLM 生成）、策略参数（来源: 用户编辑 + LLM 建议）、回测建议（来源: LLM 推荐）
- **交互说明**: 对话生成策略框架；参数面板支持手动调整；可发送到 Strategy Studio 进一步完善

#### Tab: Factor Discovery（v1.1 新增）
- **子模块**: 因子假设对话区、Factor Hypothesis 结构化输出、数据检索日志、验证方法建议
- **数据字段**: Factor Hypothesis（来源: LLM 从龙虎榜/北向/财报/新闻提取）、数据来源标注（来源: Copilot Evidence Store）、预期逻辑（来源: LLM 推理）、验证方法（来源: LLM 建议）、关联 Artifact 类型（来源: 产出物配置）
- **交互说明**: 用户输入研究问题（如"分析最近一个月北向资金大幅流入的个股特征"）→ Copilot 检索相关数据 → LLM 生成 Factor Hypothesis → 结构化输出（因子定义/数据源/预期逻辑/验证方法）→ 用户审阅后可"发送到 Factor Analysis"或"加入 Strategy Studio"；支持产出三种 Artifact：Factor Hypothesis / Earnings Digest / Flow Analysis

### Overlay Registry

#### Overlay: 保存结论 — Modal
- **触发条件**: 用户点击"保存结论"按钮时
- **内容结构**: 标题 + 结论内容预览 + 笔记分类选择 + 标签输入 + "保存" / "取消"按钮
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 保存后自动关闭 + Toast 提示

#### Overlay: 发送到工作区 — Sheet
- **触发条件**: 用户点击"发送到目标工作区"按钮时
- **内容结构**: 标题 + 目标工作区选择（Research Workspace / Strategy Studio / Factor Analysis / Intelligence）+ 附加说明 + "发送" / "取消"按钮
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 发送后自动关闭 + Toast 提示

#### Overlay: 会话模板 — Sheet
- **触发条件**: 用户点击"新建对话"按钮时
- **内容结构**: 标题 + 模板列表（空对话 / 市场日报 / 个股深度 / 行业比较 / 因子挖掘预设）+ "确认"按钮
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 确认后创建会话并自动关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected |
|------|---------|---------|-------|--------|-------|----------|
| Sessions 列表 | 会话列表：模板/历史/保存笔记 | 列表骨架屏 | "暂无历史会话" + 新建 CTA | "会话加载失败" + 重试 | 不适用 | 高亮行 + 切换对话 |
| Conversation | 消息流：用户消息 + AI 回复（流式） | 消息骨架 + 打字指示器 | "开始新的分析，输入你的问题" + 输入框聚焦 | "AI 服务不可用，请稍后重试" + 重试 | 不适用 | 消息可点击查看详情 |
| Structured Output | 结构化卡片：结论/数据/建议 | 卡片骨架屏 | 无（等待对话产出） | "结构化输出解析失败" | 不适用 | 点击卡片展开完整内容 |
| Context 面板 | 数据对象/证据/操作面板 | 面板骨架 | "暂无关联上下文" | "上下文加载失败" + 重试 | 不适用 | 数据对象可点击跳转 |
| Factor Hypothesis 输出 | 结构化文档：名称/逻辑/数据源/验证方法 | 文档骨架 | 无（等待 Factor Discovery 产出） | "假设生成失败" + 重试 | 不适用 | "发送到 Factor Analysis" / "加入 Strategy Studio" |

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

### Tab Content Sections

#### Tab: Plans（默认）
- **子模块**: Plans 列表、Plan 状态概览、新建 Plan
- **数据字段**: Plan ID（来源: Agent Engine）、状态（来源: Agent Engine：draft / running / paused / completed / failed）、创建时间（来源: Agent Engine）、关联策略（来源: Strategy Store）
- **交互说明**: 列表支持按状态筛选和搜索；点击 Plan 展开 Detail 面板；支持批量暂停

#### Tab: Runs
- **子模块**: Run 列表、Run 状态追踪、Pipeline 视图
- **数据字段**: Run ID（来源: Agent Engine）、关联 Plan（来源: Agent Engine）、执行阶段（来源: Agent Engine）、开始/结束时间（来源: Agent Engine）、Artifact 输出（来源: Agent Output Store）
- **交互说明**: 支持按 Plan 筛选 Runs；Pipeline 视图展示 Agent 链路执行进度；支持重跑失败的 Run

#### Tab: Findings
- **子模块**: Finding 列表、Confidence 评分面板、Evidence 链视图
- **数据字段**: Finding ID（来源: Agent Engine）、Confidence Score（来源: AI Confidence 框架）、Evidence 链（来源: Agent Tool Trace）、关联 Signal（来源: Signal Store）、状态（来源: Agent Engine：pending / approved / rejected / signal-generated）
- **交互说明**: Finding 卡片显示 Confidence 等级色标（绿/黄/红）；点击展开 Evidence 链和 Tool Trace；支持批量提交审批

#### Tab: Approvals
- **子模块**: 待审批队列、审批详情、历史审批记录
- **数据字段**: Finding 详情（来源: Agent Engine）、Confidence Score + Evidence（来源: AI Confidence 框架）、审批历史（来源: Approval Store）、关联 Signal 状态（来源: Signal Store）
- **交互说明**: 审批通过后自动触发信号生成流程（见审批通过后流程）；高置信 Finding 默认建议通过；低置信 Finding 标记"高风险"警告

### Overlay Registry

#### Overlay: 审批确认 — Confirm Dialog
- **触发条件**: 用户点击 Finding 的"通过" / "驳回"按钮时
- **内容结构**: "确认通过 Finding [ID]？" + Confidence 显示 + Evidence 摘要 + "确认通过" / "驳回" / "取消"按钮；通过后提示"将自动生成信号至待复核队列"
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 确认后自动关闭 + Toast 提示审批结果

#### Overlay: Plan 创建 — Sheet
- **触发条件**: 用户点击"新建 Plan"按钮时
- **内容结构**: 标题 + Plan 模板选择（全链路研究 / 财报季解读 / 盘后复盘 / 自定义）+ 参数配置 + "创建" / "取消"按钮
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 创建后自动关闭并跳转到 Plan 详情

#### Overlay: Run 重跑确认 — Confirm Dialog
- **触发条件**: 用户点击"重跑"按钮时
- **内容结构**: "确认重跑 Run [ID]？" + 上次运行摘要 + "确认重跑" / "取消"按钮
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 确认后执行并自动关闭

#### Overlay: Tool Trace — Drawer
- **触发条件**: 用户点击 Finding / Run 中的工具调用记录时
- **内容结构**: 标题 + 工具调用链路（时间线形式）+ 每步输入/输出详情 + 数据快照
- **关闭行为**: 点击遮罩关闭 / ESC 关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected | bulk |
|------|---------|---------|-------|--------|-------|----------|------|
| Plans 列表 | Plan 卡片列表 + 状态色标 | 卡片骨架屏 | "暂无 Plan，点击新建" + 新建 CTA | "Agent 服务异常" + 重试按钮 | 不适用 | 高亮卡片 + 右侧 Detail 面板 | 批量操作栏（暂停/删除） |
| Runs 列表 | Run 卡片 + Pipeline 进度条 | 卡片骨架屏 | "暂无运行记录" | "Run 数据异常" + 重试 | 不适用 | 高亮卡片 + Pipeline 详情 | 不适用 |
| Findings 列表 | Finding 卡片 + Confidence 色标 | 卡片骨架屏 | "暂无 Finding" | "Finding 数据异常" + 重试 | 不适用 | 高亮卡片 + Evidence 面板 | 批量操作栏（提交审批） |
| Approvals 队列 | 待审 Finding + Confidence + Evidence | 卡片骨架屏 | "暂无待审批项" 绿色提示 | "审批服务异常" + 重试 | 不适用 | 高亮卡片 + 审批详情 | 批量审批操作栏 |
| Detail 面板 | 右侧面板展示完整详情 | 面板骨架 | 不适用（由选中触发） | "详情加载失败" + 重试 | 不适用 | 不适用 | 不适用 |
| Pipeline 视图 | Agent 链路图 + 执行进度 | 流程图骨架 | 不适用 | "Pipeline 渲染失败" + 重试 | 节点灰色 + "等待更新" | 点击节点展开 Artifact | 不适用 |

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

### Tab Content Sections

#### Tab: Health Overview（默认）
- **子模块**: Health Strip（Freshness / Completeness / Accuracy / Jobs）、System Alerts、Resources / Quotas
- **数据字段**: 数据新鲜度（来源: Data Pipeline 健康检查）、数据完整度（来源: DQ Engine）、准确度（来源: DQ Engine）、任务状态（来源: Job Scheduler）、系统告警数（来源: Alert Store）、资源使用率（来源: Infrastructure Monitor）
- **交互说明**: Health Strip 各指标可点击展开趋势；System Alerts 支持按严重度筛选

#### Tab: Data Providers / DQ
- **子模块**: Provider 列表、数据质量面板、DQ 评分历史
- **数据字段**: Provider 名称（来源: Provider Registry）、数据延迟（来源: Pipeline Monitor）、缺失率（来源: DQ Engine）、异常率（来源: DQ Engine）
- **交互说明**: Provider 列表支持排序和筛选；点击 Provider 展开 DQ 明细面板

#### Tab: Pipelines / Jobs
- **子模块**: Pipeline 列表、Job 队列、执行日志
- **数据字段**: Pipeline 名称（来源: Pipeline Registry）、状态（来源: Job Scheduler）、上次执行时间（来源: Job Scheduler）、耗时（来源: Job Scheduler）、错误日志（来源: Log Store）
- **交互说明**: 支持手动触发 Pipeline 重跑；Job 列表支持按状态筛选（运行中/成功/失败/排队）

#### Tab: Logs / Incident History
- **子模块**: 系统日志流、事件历史、故障处理记录
- **数据字段**: 日志时间戳（来源: Log Store）、级别（来源: Log Store）、服务名（来源: Log Store）、事件描述（来源: Incident Store）、处理状态（来源: Incident Store）
- **交互说明**: 日志支持实时流式展示 + 按级别/服务名筛选；Incident 支持标记处理状态

### Overlay Registry

#### Overlay: 异常处理 — Modal
- **触发条件**: 用户点击"处理异常"按钮 / 点击 System Alert 中的告警项时
- **内容结构**: 标题（告警摘要）+ 异常详情（影响范围/根因分析）+ 操作区域（确认处理 / 升级 / 忽略）
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 确认处理后自动关闭

#### Overlay: Pipeline 重跑确认 — Confirm Dialog
- **触发条件**: 用户对运行中的 Pipeline 点击"重跑"时
- **内容结构**: "确认重跑 [Pipeline 名称]？" + 影响说明（当前任务将被中断）+ "确认重跑" / "取消"按钮
- **关闭行为**: 点击遮罩关闭 / ESC 关闭 / 确认后执行并自动关闭

#### Overlay: 任务详情 — Drawer
- **触发条件**: 用户点击 Pipelines / Jobs 列表中的某个任务时
- **内容结构**: 标题 + 执行参数 + 运行日志 + Artifact 输出
- **关闭行为**: 点击遮罩关闭 / ESC 关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale | selected |
|------|---------|---------|-------|--------|-------|----------|
| Health Strip | 4 项指标卡片 + 状态色标 | 骨架屏闪烁 | 无（系统必有指标） | "健康检查异常" + 重试按钮 | 黄色边框 + "最后检查于 HH:MM" | 点击展开指标趋势 |
| System Alerts | 告警列表，严重度色标 + 时间 | 列表行骨架屏 | "当前无系统告警" 绿色提示 | "告警加载失败" + 重试按钮 | 不适用 | 高亮行 + 展开详情 |
| Provider 列表 | 表格：名称/延迟/缺失率/异常率 | 表格行骨架屏 | "暂无数据源配置" | "Provider 数据异常" + 重试按钮 | 表格顶部黄色提示 "数据延迟" | 高亮行 + 展开 DQ 面板 |
| Job Queue | 任务列表：名称/状态/时间/耗时 | 列表行骨架屏 | "暂无运行中任务" | "Job 调度器异常" + 重试按钮 | 不适用 | 高亮行 + 展开日志 |
| Logs Stream | 实时日志流，级别色标 | 加载指示器 | "暂无新日志" | "日志服务连接失败" + 重试按钮 | 不适用 | 点击展开日志详情 |

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

### Tab Content Sections

#### Tab: Regime Status（默认视图，首屏聚合区）
- **子模块**: Regime Status Strip（当前状态 + 置信度 + 关键指标）、Regime Indicator（三状态仪表）、Drivers Panel
- **数据字段**: 当前 Regime 状态（来源: Regime Engine 判定）、置信度（来源: Regime Engine）、驱动因子列表（来源: 宏观数据管道：波动率/流动性/资金面/宏观事件）
- **交互说明**: 仪表盘支持点击切换时间范围（1M/3M/6M/1Y）；驱动因子可展开查看详情

#### Tab: Switch History
- **子模块**: 时间线视图、切换事件详情
- **数据字段**: 切换时间（来源: Regime Engine）、前状态/后状态（来源: Regime Engine）、触发因子（来源: 归因分析）、持续时间（来源: 计算字段）
- **交互说明**: 时间线支持按 Regime 类型筛选；点击切换事件展开详情面板

#### Tab: Strategy Impact
- **子模块**: 策略表现对比、调整建议
- **数据字段**: 策略名称（来源: Strategy Store）、当前 Regime 下表现（来源: 回测引擎）、建议调整（来源: AI 归因分析）
- **交互说明**: 策略卡片可点击跳转到 Strategy Studio（Context Transfer: `?ctx[regime]=risk-off`）

### Overlay Registry

#### Overlay: AI Regime 解读 — Drawer
- **触发条件**: 用户点击"AI 解读"按钮时
- **内容结构**: 标题 + AI 对当前 Regime 状态的结构化解读文本 + 置信度评分 + 引用数据源
- **关闭行为**: 点击遮罩关闭 / ESC 关闭

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale |
|------|---------|---------|-------|--------|-------|
| Regime Indicator | 三状态仪表渲染，当前状态高亮 | 仪表骨架屏动画 | 无（引擎必有判定） | "Regime 判定服务异常" + 重试按钮 | 黄色脉冲 + "判定延迟" |
| Status Strip | 状态标签 + 置信度 + 关键指标值 | 指标骨架屏 | 不适用 | "数据加载失败" + 重试 | 指标旁灰色圆点 |
| Drivers Panel | 因子列表：名称/当前值/趋势 Sparkline | 因子行骨架屏 | "暂无驱动因子数据" | "因子数据异常" + 重试 | 不适用 |
| Switch History | 时间线渲染，切换节点着色 | 时间线骨架 | "暂无 Regime 切换记录" | "历史数据加载失败" + 重试 | 不适用 |
| Strategy Impact | 策略卡片列表 + 表现数据 | 卡片骨架屏 | "暂无关联策略" + 跳转 Strategy Studio | "策略数据异常" + 重试 | 不适用 |

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

### Tab Content Sections

#### Tab: AI Pulse（默认视图，非 tab 切换，首屏聚合区）
- **子模块**: Agent Status（运行中 Plans / 待审批 Findings / 最近完成 Runs）、Copilot Status（活跃会话 / 最近产出 / 保存笔记）
- **数据字段**: Agent 运行中数量（来源: Agent Engine）、待审批数量（来源: Agent Engine）、Copilot 活跃会话数（来源: Copilot Session Store）、最近产出时间（来源: Copilot Output Log）
- **交互说明**: 点击各聚合卡片跳转到对应子页面；数量 Badge 实时更新（Polling 30s）

### Overlay Registry

#### Overlay: 新建会话确认 — Toast
- **触发条件**: 用户点击"新建 Copilot 会话"按钮时
- **内容结构**: Toast 提示 "已创建新会话" + 自动跳转到 `/ai/copilot`
- **关闭行为**: 3 秒自动消失

#### Overlay: 新建 Plan 引导 — Toast
- **触发条件**: 用户点击"新建 Agent Plan"按钮时
- **内容结构**: Toast 提示 "已创建新 Plan" + 自动跳转到 `/ai/agent`
- **关闭行为**: 3 秒自动消失

### Component × State Matrix

| 组件 | default | loading | empty | failed | stale |
|------|---------|---------|-------|--------|-------|
| AI Pulse | 各模块数值 + 状态色标 | 骨架屏脉冲动画 | "暂无 AI 活动，开始你的第一次对话" + 新建 CTA | "AI 服务连接异常" + 重试按钮 | 数值旁灰色圆点 + "数据延迟" |
| Agent Quick View | 卡片列表：运行中/待审/已完成 | 卡片骨架屏 | "暂无 Agent 活动" | "Agent 服务异常" + 重试 | 不适用 |
| Copilot Quick View | 最近产出列表 + 会话链接 | 列表骨架屏 | "暂无 Copilot 活动" | "Copilot 服务异常" + 重试 | 不适用 |

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

### 2026-04-01 — Cross-Market Review R11 Sync (IA Alignment Round)

- **[修正]** §2 Bottom Tab Band: 龙虎榜/两融数据移至 A股总览，Cross-Market 保留 3 tabs（资金轮动/事件日历/AI解读）（来源: IA-01，R11 六角色共识）
- **[修正]** §2 Right Rail: 移除「北向资金深度面板」，北向资金深度仅归属 §2.1 A股总览 Right Rail（来源: IA-02，§7.2 明确）
- **[修正]** §2 Context Bar: 6 变量(UNIVERSE/SESSION/REGIME/VOL/DOLLAR/ALERTS)→4 客观变量(市态/波动/美元/预警)，与原型实现对齐（来源: IA-03）
- **[补充]** §2 Scope Strip: 新增 4 解读变量描述（领涨/领跌/风格/事件），承载 AI 今日解读层（来源: IA-03）
- **[修正]** §2 商品 Market Card: 「商品/黄金」→「商品」（聚合品类，黄金为主指数，原油内联至 judgment 文本）（来源: IA-04）
- **[修正]** §2 Wireframe: Context Bar/Scope Strip/卡片/Rail 标签全面同步原型实现
- **[修正]** §2 Sparkline opacity 标准: 0.6→0.7（R2 精修，暗色背景可感知性提升）（来源: R2-POLISH-04）
