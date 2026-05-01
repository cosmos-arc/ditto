# Ditto Page Pattern Library

> **版本**：v1.3
> **日期**：2026-04-18
> **状态**：Final
> **上游**：[10 Shell Family 规范](./10_ditto_shell_family_spec.md)、[01 产品信息架构](./01_product_information_architecture.md)
> **下游**：[02 核心页面蓝图](./02_core_page_blueprints.md)
> **职责**：把 Shell Family 从"壳层类型"进一步落到"可复用页面模板"
>
> 适用范围：Ditto 全站页面模式库

---

## 1. 文档目标

Shell Family 解决的是"页面属于哪一类骨架"。

Page Pattern Library 解决的是"同一类骨架下，页面到底该怎么组织"。

因为 Ditto 的 sitemap 很大，如果每个页面都单独设计，最后一定会出现：

- 同一模块里语法不一致
- 设计成本失控
- 前端 layout 和组件复用率低
- 页面之间缺乏系统记忆
- 很容易又滑回"每页一套创意"的后台式设计

所以 Ditto 不应该按页面逐个设计，而应该先按 Page Pattern 设计，再把 sitemap 映射进去。

这份规范建议把全站收敛成 **8 套页面模式**。

这 8 套模式已经足以覆盖你目前的完整 sitemap，并为后续扩展留出空间。

---

## 2. Page Pattern 总览

| # | Pattern | 一句话定义 |
|---|---------|-----------|
| 01 | **Global Command Center** | 全局起点 — 跨模块总指挥台 |
| 02 | **Analytical Overview Workspace** | 核心分析 — 围绕主仪表工作 |
| 03 | **Catalog / Screener Workspace** | 对象检索 — 筛选、浏览、批量处理 |
| 04 | **Object Hub** | 单对象控制中枢 |
| 05 | **Studio / Builder** | 构建、编辑、对话、编排 |
| 06 | **Queue / Ops Console** | 处置、排查、监控、追踪 |
| 07 | **Ledger / Execution Console** | 订单、成交、执行状态链 |
| 08 | **Config / Integration Console** | 系统设置、账户、通道、集成 |

这 8 套模式不是 8 张具体页面，而是 8 类"页面原型"。

---

## 3. Pattern 设计总原则

### 原则 1：同一 Pattern 内部必须高一致

同一个 Pattern 下的页面，哪怕内容不同，也应共享相似语法、相似节奏、相似交互重心。

### 原则 2：Pattern 之间的差异必须来自任务，而不是风格

不是某些页面"更好看"，某些页面"更朴素"，而是因为它们承担的任务不同，所以主工作面不同。

### 原则 3：一个页面只能有一个主 Pattern

允许局部混合，但主模式必须明确。

例如 `/research/backtest` 可以带一点 analytical 气质，但主模式仍应是 **Catalog / Screener Workspace**。

### 原则 4：对象页和编辑页必须与目录页严格区分

很多系统失败，就是因为列表页、详情页、编辑页长得像同一种后台页面。

Ditto 必须明确区分对象浏览、对象管理、对象构建、对象监控。

### 原则 5：动作必须放在正确层级

Pattern 可以决定主动作语气，但不能改变全局 chrome 合同。

| Action | Placement |
|---|---|
| Global command/search | Header utility |
| Copilot | Header utility |
| Notifications | Header utility |
| Help | Header utility |
| Account/view preferences | Header utility |
| Export table | Data toolbar |
| Refresh table | Data toolbar or workspace toolbar |
| Filter table/list | Data toolbar |
| Column configuration | Data toolbar |
| Run backtest / execute screening | Workspace toolbar |
| Save/publish strategy | Studio header or workspace toolbar |
| Settings/config validation | Config workspace toolbar |

### 原则 6：每页必须有一个 Primary Answer

每个 active page pattern 都必须提供一个且只有一个 Primary Answer。它负责在 5 秒内给出页面核心判断，而不是把用户丢进卡片、表格或图表里自己拼答案。

Primary Answer = 一句话判断 + 1 个关键数字 + 2-3 个证据 + 1 个主动作 + 明确影响范围。

页面模式对应关系：

| Pattern | Primary Answer 承载面 |
|---|---|
| Global Command Center | decision card / decision banner |
| Analytical Overview Workspace | main instrument readout 或 context strip |
| Catalog / Screener Workspace | task-specific summary strip |
| Object Hub | object status header |
| Studio / Builder | current build / run status |
| Queue / Ops Console | incident / service health priority |
| Ledger / Execution Console | execution / reconciliation priority strip |
| Config / Integration Console | validation / service health priority |
| Radar / Market Map | market scope strip + selected map summary |

落地属性：

- 主区域标记 `data-primary-answer`；若沿用已有成熟主区域，标记 `data-primary-answer-equivalent`。
- 子元素优先显式标记 `data-answer-judgment`、`data-answer-metric`、`data-answer-evidence`、`data-answer-action`、`data-answer-scope`。
- Catalog、Ops、Studio 可以使用紧凑 summary strip；Object Hub 可以使用对象状态 header；Radar 可以使用 scope strip。
- 不允许多个区域同时宣称 primary answer。若页面已有多个合理候选，必须收敛到一个代表区域。

---

## 4. Pattern 01 — Global Command Center

### 4.1 定义

Global Command Center 是 Ditto 的全局起点。

它不是单一模块首页，而是一个跨 Markets / Research / Trading / AI / Platform 的总指挥台。

它的目标不是深度分析，而是：

- 对齐今日任务
- 发现全局异常
- 识别优先事项
- 快速跳入下一工作区

### 4.2 适用页面

- `/`

<!-- 已移除: `/ai` — AI Overview 已 deprecated，功能并入全局 Sidecar -->

未来也可以承接：

- Morning Brief
- Daily Prep
- Close Review
- Global Operations Snapshot

<!-- 已降级/合并: `/home/pending` — 并入 `/` 首页内部区块 -->
<!-- 已降级/合并: `/home/quick-actions` — 并入 `/` 首页内部区块 -->
<!-- 已降级/合并: `/home/alerts-summary` — 并入 `/` 首页内部区块 -->

### 4.3 页面目标

进入页面 5 秒内，用户必须能回答：

1. 今天最该处理什么
2. 当前哪些问题最重要
3. 哪些系统、策略、市场正在运行或异常
4. 我下一步应该进入哪个工作区

### 4.4 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Global Header                                                │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Today Strip / Global Pulse                                   │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Focus Board              │ Global Alerts / Live Status   │
│      │                               │                               │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Quick Actions / Cross-Domain Summary                          │
└──────┴───────────────────────────────────────────────────────────────┘
```

### 4.5 主区块说明

**Global Header**

- Ditto logo
- 日期 / 当前 session
- 全局搜索 / command
- 核心全局动作

**Today Strip / Global Pulse**

- Pending 数量
- Critical alerts 数量
- Running jobs
- Broker / data / system 状态
- 今日焦点摘要

**Main Focus Board**（主角）

- Pending queue
- Today tasks
- My review queue
- Highest priority signals / incidents

**右侧 Global Alerts / Live Status**

- Global incidents
- Running pipelines
- Data delays
- Risk breaches
- Agent pending approvals

**底部 Quick Actions / Cross-Domain Summary**

- 高频跳板
- Workspace shortcuts
- Today boards
- 可选的轻量账户 / 策略 / 市场摘要

### 4.6 不建议

- 把首页做成普通 dashboard 卡片墙
- 把首页做成每个模块各一个缩略版
- 首页堆很多图表但没有任务优先级
- 首页像 marketing landing page
- 首页抢走具体工作区的功能

### 4.7 适合的组件

- Global pulse strip
- Pending queue block
- Priority summary block
- Quick action tile
- Global alerts list
- Shortcuts board

### 4.8 不适合的组件

- 重分析图
- 大面积目录表
- 复杂配置面板
- Studio canvas
- 长对象详情结构

---

## 5. Pattern 02 — Analytical Overview Workspace

### 5.1 定义

这是 Ditto **最核心**的一类页面模式。

适用于"分析、监控、判断"为主任务的页面。

用户进入后应该立刻围绕一个**主仪表**开始工作，而不是先浏览一堆卡片。

### 5.2 适用页面

- `/markets`（Radar 变体）
- `/markets/a-shares`（Radar 变体）
- `/markets/hk`（Radar 变体 — v1.5/v2 延后）
- `/markets/us`（Radar 变体 — v1.5/v2 延后）
- `/markets/watchlist`
- `/markets/intelligence`
- `/research`
- `/research/regime`
- `/trading`
- `/trading/portfolio`
- `/trading/risk`

<!-- 已移除: `/trading/signals` — IA 归为 Queue/Ops Console（核心动词是 review/confirm/reject） -->
<!-- 已修正: `/trading/risk/dashboard` → `/trading/risk` -->
<!-- 已移除: `/trading/risk/stress-test` — IA 无此路由 -->
<!-- 已合并: `/trading/positions` + `/trading/trades` → `/trading/portfolio`（IA v2.0） -->
<!-- 已移除: `/markets/universes` — 迁移至 Research 域（IA v2.0） -->
<!-- 已降级: `/markets/chart-lab` — IA v2.0 不再作为一级路由 -->

### 5.3 页面目标

进入页面 5 秒内，用户必须能回答：

1. 当前主对象或主范围是什么
2. 当前最重要的数据工作面在哪里
3. 哪些次级信息在右侧或底部解释主仪表
4. 我现在最主要的动作是什么

### 5.4 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Workspace Header                                             │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Pulse / Context Strip                                        │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Instrument               │ Activity Stack                │
│      │                               │                               │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Analysis Band                                                │
└──────┴───────────────────────────────────────────────────────────────┘
```

### 5.5 子变体

**A. Table-first Analytical Workspace**

主仪表是主表。

适用：Research overview、Screener、Positions、Signals、Factor monitor

**B. Chart-first Analytical Workspace**

主仪表是主图。

适用：Risk dashboard、Regime lab、Backtest compare

**C. Market Radar Workspace**（Radar 子变体）

> **详细设计**：[全市场总览设计文档](../../plans/2026-03-29-cross-market-overview-design.md)

主工作面是 Market Cards + Cross-Market Matrix + Macro Drivers 的组合，不是单一主表/主图。

适用于跨市场扫描和单市场结构扫描——以"扫 → 比 → 选"为核心动词的页面。

适用：`/markets`（全市场总览）、`/markets/a-shares`、`/markets/hk`（v1.5/v2 延后）、`/markets/us`（v1.5/v2 延后）

核心特征：
- 双层 Context（Context Bar + Scope Strip）
- 70% 主工作面 + 30% Right Rail
- Right Rail 聚焦风险、事件、下钻推荐
- 底部 Tab Band（资金轮动 / 事件日历 / AI 解读）
- 页面动词是 scan / compare / drill down

推荐骨架：

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Workspace Header                                              │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Context Bar                                                   │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope Strip                                                   │
│      ├───────────────────────────────────┬───────────────────────────┤
│      │ Main Stage (70%)                  │ Right Rail (30%)          │
│      │ Market Cards / Matrix / Drivers   │ 脉搏 / 风险 / 事件 / 下钻   │
│      ├───────────────────────────────────┴───────────────────────────┤
│      │ Bottom Tab Band                                               │
└──────┴───────────────────────────────────────────────────────────────┘
```

**D. Mixed Analytical Workspace**

表图并存，但主次仍需明确。

适用：Trading overview、Portfolio overview

### 5.6 典型区块

**Workspace Header**

- Workspace title
- 当前 universe / scope / period / updated at
- command search
- 主动作与工作区动作

**Pulse / Context Strip**

- 关键状态计数
- 数据新鲜度
- 当前运行摘要
- 当前范围总量

**Main Instrument**（主角）

主表或主图。是绝对主角。

**Activity Stack**

- Recent / Live / Queue / Notes
- 围绕当前对象联动

**Analysis Band**

- 承接解释、比较、分解、相关性、timeline

### 5.7 适合的组件

- Analytical table
- Main chart container
- Activity stack
- Analysis band
- Scope tabs
- Filter bar
- Summary strip
- Compare state

### 5.8 不适合的组件

- 太多常驻大按钮
- 每块都独立卡片化
- 复杂表单长流程
- 普通后台式详情抽屉替代整个工作流
- 聊天气泡式 AI 面板作为主要工作面

---

## 6. Pattern 03 — Catalog / Screener Workspace

### 6.1 定义

Catalog / Screener Workspace 用于对象集合的检索、筛选、浏览、批量处理。

它的主角不是分析带，也不是对象详情，而是**对象表或筛选工作面**。

### 6.2 适用页面

- `/markets/screener`
- `/research/universes` <!-- 已迁移: 原 `/markets/universes` → `/research/universes`（IA v2.0） -->
- `/markets/calendar`
- `/research/factors`
- `/research/strategies`
- `/research/backtest`
- `/research/experiments`
- `/trading/orders`
- `/trading/portfolio` <!-- 已合并: 原 `/trading/positions` + `/trading/trades` → `/trading/portfolio`（IA v2.0） -->

<!-- 已移除: `/markets/catalog` — IA 无此独立路由，由 `/markets` + `/markets/screener` 覆盖 -->

### 6.3 页面目标

进入页面后，用户要能高效完成：

1. 找对象
2. 筛对象
3. 排对象
4. 看关键字段
5. 选对象
6. 批量动作
7. 进入对象页或详情预览

### 6.4 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Catalog Header                                               │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope / Filters / Saved Views                                │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Table / Grid             │ Preview / Inspector           │
│      │                               │ (optional)                    │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

### 6.5 子变体

**A. Library Catalog** — 偏对象库

适用：factors、strategies、universes、portfolios

**B. Screener Catalog** — 偏筛选器

适用：markets catalog、screener、watch candidates、research output lists

**C. Ledger Catalog** — 偏流水

适用：orders、trades、backtests list、experiments list

### 6.6 主区块说明

**Catalog Header**

- 页面标题
- 当前 scope
- result count
- saved view
- 批量动作入口

**Scope / Filters / Saved Views**（第二核心带）

必须清晰区分：scope / filter / sort / saved view / density / columns

**Main Table / Grid**（主角）

- analytical table
- ledger table
- object grid

**Preview / Inspector**（可选）

- 对象摘要
- 最近状态
- 关键图
- 关键字段
- 下一步动作

### 6.7 适合的组件

- Analytical / ledger table
- Filter chip bar
- Save view control
- Compare state
- Object preview panel
- Batch action bar

### 6.8 不适合的组件

- 常驻底部 analysis band
- 右侧 full activity stack
- 太多 summary KPI 卡片
- 页面一半用来讲故事，一半才是表

---

## 7. Pattern 04 — Object Hub

### 7.1 定义

Object Hub 是围绕**单一对象**展开的综合工作台。

它不是普通详情页，而是一个对象的"控制中枢"。

### 7.2 适用页面

- `/instruments/[id]`
- `/research/factors/[id]`
- `/research/backtest/[id]`

<!-- 已修正: `/research/factors/[id]/analysis` → `/research/factors/[id]` -->
<!-- 已移除: `/research/strategies/[id]` — Studio 统一后路由不再独立 -->
<!-- 已移除: `/research/experiments/[id]` — IA 无此路由 -->

未来也可扩展到：

- model detail
- broker route detail
- data provider detail
- agent detail

### 7.3 页面目标

进入页面后，用户应该能回答：

1. 这个对象当前状态如何
2. 这个对象最核心的表现或健康度是什么
3. 最近发生了什么
4. 我可以对它做哪些动作
5. 我怎么继续 drill-down 或跳到关联对象

### 7.4 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Object Header                                                │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Object Meta Strip                                            │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Object Panels            │ Related / History / Notes     │
│      │                               │                               │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Timeline / Diagnostics / Logs / Linked Views                 │
└──────┴───────────────────────────────────────────────────────────────┘
```

### 7.5 主区块说明

**Object Header**

- 对象名
- 对象类型
- 当前状态
- 关键动作
- 版本 / 环境 / owner（按对象类型决定）

**Object Meta Strip**

- 标签
- 当前范围
- 关键计数
- 最近更新时间
- 关联对象数量

**Main Object Panels**（通常 2–3 个即可）

Factor 分析页示例：

- IC / IR
- Decay
- Coverage / correlation

Strategy Hub 示例：

- Performance
- Exposure / turnover
- Recent runs / linked signals

Backtest Hub 示例：

- NAV / benchmark
- Metrics summary
- Parameter / dataset snapshot

**右侧 Related / History / Notes**

- Recent events
- Version history
- Linked outputs
- Owner notes
- Related entities

**底部 Timeline / Diagnostics / Logs**

- Timeline
- Diagnostics
- Artifacts
- Logs
- Raw outputs

### 7.6 适合的组件

- Object status block
- Linked entities list
- Version history list
- Diagnostic panel
- Artifact list
- Notes block
- Timeline

### 7.7 不适合的组件

- 大而全目录表占主区
- 复杂 builder/editor
- 普通 marketing 式详情布局
- 把所有对象信息都堆成一页长文档

---

## 8. Pattern 05 — Studio / Builder

### 8.1 定义

Studio / Builder 用于构建、编辑、配置、对话、编排和调试。

它的主角不是数据表，而是**工作画布或编辑区域**。

### 8.2 适用页面

- `/research/strategies/[id]/studio`
- `/platform/agents`

<!-- 已降级: `/markets/chart-lab` — IA v2.0 不再作为一级路由 -->
<!-- 已升级: `/ai/copilot` — 升级为全局 Sidecar，不再是独立页面路由 -->
<!-- 已迁移: `/ai/agent` — 迁入 `/platform/agents`（Studio Shell） -->
<!-- 已合并: `/research/strategies/new` → `/research/strategies/[id]/studio` -->
<!-- 已合并: `/research/strategies/[id]/editor` → `/research/strategies/[id]/studio` -->
<!-- 已合并: `/research/backtest/new` — IA 无此独立路由 -->
<!-- 已合并: `/ai/market-analysis` → `/ai/copilot` 内部模式 -->
<!-- 已合并: `/ai/stock-screener` → `/ai/copilot` 内部模式 -->
<!-- 已合并: `/ai/strategy-assistant` → `/ai/copilot` 内部模式 -->

### 8.3 页面目标

进入页面后，用户应该能快速开始：

- 写
- 配
- 拖
- 对话
- 运行
- 检查
- 审批
- 发布

Studio 页面要减少浏览感，强化"手正在工作"的感觉。

### 8.4 推荐骨架

**双栏 Studio**

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Studio Header                                                │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Editor / Canvas / Chat   │ Inspector / Preview / Run     │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

**三栏 Studio**

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Studio Header                                                │
│      ├───────────────┬───────────────────────────────┬──────────────┤
│      │ Sources       │ Main Workspace                │ Inspector    │
│      │ / Outline     │                               │ / Run State  │
└──────┴───────────────┴───────────────────────────────┴──────────────┘
```

### 8.5 子变体

**A. Builder Studio**

适用：strategy builder、chart lab、backtest new

**B. Editor Studio**

适用：strategy editor、config-heavy ML workflow

**C. AI Copilot Studio**

适用：ai copilot、ai strategy assistant、ai market analysis

**D. Agent Console Studio**

适用：agent workspace、multi-step tool run、approval / task execution

### 8.6 主区块说明

**Studio Header**

- 会话 / 对象标题
- 当前版本 / 状态
- save / run / publish / approve
- optional environment / branch / runtime

**左侧 Sources / Outline**

- Templates
- Nodes
- Files
- References
- Research sources
- Tool list

**中间 Main Workspace**（主角）

- Editor
- Canvas
- Notebook
- Chat
- Flow builder

**右侧 Inspector / Run / Preview**

- Config
- Schema
- Preview
- Run output
- Agent state
- Approval block
- Linked context

### 8.7 适合的组件

- Command bar
- Inspector panel
- Config panel
- AI conversation block
- Agent task block
- Approval block
- Run timeline
- Output preview
- Code / formula editor
- Node graph / chart editor

### 8.8 不适合的组件

- 底部 analysis band 作为默认结构
- 常驻 activity stack
- 一堆 summary cards 占掉中间工作面
- 把 Studio 做成普通详情页或 dashboard

---

## 9. Pattern 06 — Queue / Ops Console

### 9.1 定义

Queue / Ops Console 用于处置、排查、监控、追踪系统级或流程级事项。

它的主角通常是**队列、任务表、告警表、事件流**，而不是研究数据。

### 9.2 适用页面

- `/trading/signals`（核心动词是 review / confirm / reject，本质是队列操作）
- `/platform`
- 未来 incident/review pages

<!-- 已降级/合并: `/home/pending` — 并入 `/` 首页内部区块 -->
<!-- 已降级/合并: `/home/alerts-summary` — 并入 `/` 首页内部区块 -->
<!-- 已移除: `/trading/alerts` — IA 无此路由 -->
<!-- 已降级: `/platform/data-quality` — 收敛为 `/platform` 的 tab -->
<!-- 已降级: `/platform/pipelines` — 收敛为 `/platform` 的 tab -->

这类页面有时属于 Home，有时属于 Platform，但模式相同。

### 9.3 页面目标

用户进入后应能高效完成：

1. 看当前问题
2. 排优先级
3. 定位详情
4. 处理 / 认领 / 重试 / 忽略
5. 查看 trace / logs / dependencies

### 9.4 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Ops Header                                                   │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope / Severity / Status Strip                              │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Queue / Ops Table        │ Detail / Logs / Actions       │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

### 9.5 子变体

**A. Alert Queue**

适用：trading alerts、alerts summary、model drift review

**B. Job Queue**

适用：pipelines、running jobs、task retries

**C. Data Quality Queue**

适用：freshness issues、missing data、revision conflicts

**D. Review Queue**

适用：factor review、signal review、approval workflows

### 9.6 主区块说明

**Ops Header**

- 页面标题
- 当前环境 / scope
- 高优动作
- filters / saved view

**Scope / Severity / Status Strip**

- Total
- Active
- High severity
- Stale
- Assigned to me
- Delayed

**Main Queue / Ops Table**（主角）

必须支持：severity / status / owner / updated at / next action

**右侧 Detail / Logs / Actions**

- Event detail
- Logs
- Retries
- Assignments
- Audit trail
- Raw payload

### 9.7 适合的组件

- Ops table
- Severity badge
- Ownership chip
- Action panel
- Log viewer
- Retry block
- Incident timeline
- Assignment control

### 9.8 不适合的组件

- 重分析图占主区
- AI 聊天气泡当主界面
- 卡片墙式 alerts
- 大量 decorative KPI

---

## 10. Pattern 07 — Ledger / Execution Console

### 10.1 定义

Ledger / Execution Console 用于订单、成交、执行状态、持仓流水、经纪通道状态等场景。

它既不是研究型表，也不是普通 ops 队列，而是带有"**账本 / 流水 / 状态链**"特征的专业执行页面。

### 10.2 适用页面

- `/trading/orders`
- `/trading/portfolio`

<!-- 已修正（v1.3）: 原 `/trading/positions` + `/trading/trades` 已合并为 `/trading/portfolio`（IA v2.0） -->

未来可能的 fills / execution logs / broker routes

### 10.3 页面目标

用户进入后应能高效完成：

1. 看状态链
2. 看时间线
3. 看数量 / 价格 / 金额
4. 看执行偏差
5. 查明细
6. 重试 / 取消 / 追踪

### 10.4 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Execution Header                                             │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope / Status / Session Strip                               │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Ledger Table / Timeline       │ Order / Fill Detail           │
│      │                               │ / Execution Trace             │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

### 10.5 子变体

**A. Orders Ledger** — 主角是订单状态链

**B. Trades Ledger** — 主角是成交流水与价格数量

**C. Position Ledger** — 主角是持仓变化、成本、PnL、book exposure

**D. Execution Trace** — 主角是委托—成交—路由—确认的执行路径

### 10.6 主区块说明

**Execution Header**

- 页面标题
- 当前 trading session
- broker / account / book scope
- 导出 / compare / filter

**Scope / Status Strip**

- Active orders
- Partially filled
- Rejected
- Session status
- Route health

**Ledger Table / Timeline**（主角）

列重点：time / side / symbol / qty / filled / price / status / route / strategy / account

**右侧 Detail / Trace**

- Order history
- Fill breakdown
- Route info
- Slippage
- Rejection reason
- Raw execution log

### 10.7 适合的组件

- Ledger table
- Execution timeline
- Route status block
- Fill breakdown
- Slippage mini chart
- Raw log viewer
- Action menu

### 10.8 不适合的组件

- 底部大型 analysis band 默认常驻
- 大量卡片式 summary
- 普通 analytical activity stack 替代 execution detail

---

## 11. Pattern 08 — Config / Integration Console

### 11.1 定义

Config / Integration Console 用于系统设置、账户、通道、数据提供方、通知集成等配置型页面。

它必须保持 Ditto 的专业感，但任务核心是"**配置与状态检查**"，不是分析或执行。

### 11.2 适用页面

- `/platform/settings`（Data Providers / Brokers / 通用 Settings 作为 tab 承载）

<!-- 已降级: `/platform/accounts` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/brokers` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/data-providers` → `/platform/settings` 的 tab -->
<!-- 已移除: `/platform/notifications` — IA 无此路由 -->

### 11.3 页面目标

进入页面后，用户应能高效完成：

1. 查当前配置
2. 编辑或新增配置
3. 看连接状态
4. 看最近错误 / 测试结果
5. 保存 / 回滚 / 验证

### 11.4 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Config Header                                                │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope / Connection / Validation Strip                        │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Config Forms / List           │ Inspector / Test / Logs       │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

### 11.5 子变体

**A. Integration Config**

适用：brokers、data providers、notifications

**B. Account / Permission Config**

适用：platform accounts、role management

**C. System Settings**

适用：platform settings

### 11.6 主区块说明

**Config Header**

- 页面标题
- 当前环境 / scope
- Save / Test / Validate / Rollback

**Scope / Validation Strip**

- Connected
- Stale
- Auth expired
- Last tested
- Config version

**Main Config Forms / List**

- Config form
- Provider list
- Account list
- Permissions matrix

**右侧 Inspector / Test / Logs**

- Connection test
- Logs
- Audit trail
- Config diff
- Last validation result

### 11.7 适合的组件

- Config panel
- Validation strip
- Connection status block
- Log viewer
- Diff panel
- Test result block
- Permission matrix

### 11.8 不适合的组件

- 强 terminal 化 activity stack
- 底部 analysis band
- 太多图表
- 普通营销式设置页样式

---

## 12. 全站 Sitemap 到 Pattern 的映射

### 12.1 Home

| 路由 | Pattern |
|------|---------|
| `/` | Global Command Center (orient 型) |
| ~~`/home/pending`~~ | _降级：并入 `/` 首页内部区块_ |
| ~~`/home/quick-actions`~~ | _降级：并入 `/` 首页内部区块_ |
| ~~`/home/alerts-summary`~~ | _降级：并入 `/` 首页内部区块_ |

### 12.2 Markets & Intelligence

| 路由 | Pattern |
|------|---------|
| `/markets` | Analytical Overview Workspace |
| `/markets/a-shares` | Analytical Overview Workspace (Radar 变体) |
| `/markets/hk` | Analytical Overview Workspace (Radar 变体 — **v1.5/v2 延后**) |
| `/markets/us` | Analytical Overview Workspace (Radar 变体 — **v1.5/v2 延后**) |
| `/markets/screener` | Catalog / Screener Workspace |
| ~~`/markets/universes`~~ | _迁移至 Research 域（IA v2.0）_ |
| `/markets/watchlist` | Analytical Overview Workspace |
| ~~`/markets/catalog`~~ | _移除：IA Sitemap 无此独立路由，由 `/markets` + `/markets/screener` 覆盖_ |
| ~~`/markets/map`~~ | _降级：并入 `/markets` 视图模式_ |
| `/markets/intelligence` | Analytical Overview Workspace (tab 视图，收敛原 `/*` 子路由) |
| ~~`/markets/chart-lab`~~ | _降级：IA v2.0 不再作为一级路由_ |
| `/markets/calendar` | Catalog / Screener Workspace |
| `/instruments/[id]` | Object Hub |

### 12.3 Research & ML

| 路由 | Pattern |
|------|---------|
| `/research` | Analytical Overview Workspace |
| `/research/universes` | Catalog / Screener Workspace **[v1.3 新增 — 从 Markets 域迁入]** |
| `/research/factors` | Catalog / Screener Workspace |
| `/research/factors/[id]` | Object Hub |
| ~~`/research/factors/[id]/analysis`~~ | _修正：简化为 `/research/factors/[id]`_ |
| `/research/strategies` | Catalog / Screener Workspace |
| `/research/strategies/[id]/studio` | Studio / Builder |
| ~~`/research/strategies/new`~~ | _合并：统一为 `/strategies/[id]/studio`_ |
| ~~`/research/strategies/[id]/editor`~~ | _合并：统一为 `/strategies/[id]/studio`_ |
| ~~`/research/strategies/[id]`~~ | _移除：Studio 统一后原 Object Hub 路由不再独立存在_ |
| `/research/backtest` | Catalog / Screener Workspace |
| `/research/backtest/[id]` | Object Hub |
| ~~`/research/backtest/new`~~ | _移除：IA Sitemap 无此独立路由_ |
| ~~`/research/backtest/compare`~~ | _移除：IA Sitemap 无此独立路由_ |
| `/research/experiments` | Catalog / Screener Workspace |
| ~~`/research/experiments/[id]`~~ | _移除：IA Sitemap 无此独立路由_ |
| `/research/regime` | Analytical Overview Workspace |
| ~~`/research/ml`~~ | _降级：并入 Research 子域，非独立路由_ |
| ~~`/research/output`~~ | _移除：IA Sitemap 无此路由_ |

### 12.4 Trading

| 路由 | Pattern |
|------|---------|
| `/trading` | Analytical Overview Workspace |
| ~~`/trading/accounts`~~ | _移除：IA Sitemap 无此路由（v1.1 审计清理）_ |
| ~~`/trading/portfolios`~~ | _移除：IA Sitemap 无此路由_ |
| `/trading/portfolio` | Analytical Overview Workspace **[v1.3 — 合并原 positions + trades]** |
| `/trading/signals` | Queue / Ops Console **[v1.1 审计修正]** |
| `/trading/orders` | Ledger / Execution Console |
| ~~`/trading/trades`~~ | _已合并：并入 `/trading/portfolio`（IA v2.0）_ |
| `/trading/risk` | Analytical Overview Workspace |
| ~~`/trading/risk/dashboard`~~ | _修正：简化为 `/trading/risk`_ |
| ~~`/trading/risk/stress-test`~~ | _移除：IA Sitemap 无此路由_ |
| ~~`/trading/alerts`~~ | _移除：IA Sitemap 无此路由_ |

### 12.5 AI & Agent

> **[v1.3] 整段 deprecated**：AI 域在 IA v2.0 中不再作为独立路由域存在。
> - `/ai`（AI Overview）已 deprecated，功能并入全局 Sidecar
> - `/ai/copilot` 已升级为全局 Sidecar，不再是独立页面路由
> - `/ai/agent` 已迁入 `/platform/agents`（Studio Shell）

| 路由 | Pattern |
|------|---------|
| ~~`/ai`~~ | _deprecated：功能并入全局 Sidecar（IA v2.0）_ |
| ~~`/ai/copilot`~~ | _升级：全局 Sidecar，不再是独立页面路由_ |
| ~~`/ai/agent`~~ | _迁移：→ `/platform/agents`（Studio Shell）_ |
| ~~`/ai/market-analysis`~~ | _合并：作为 `/ai/copilot` 内部模式_ |
| ~~`/ai/stock-screener`~~ | _合并：作为 `/ai/copilot` 内部模式_ |
| ~~`/ai/strategy-assistant`~~ | _合并：作为 `/ai/copilot` 内部模式_ |

### 12.6 Platform

| 路由 | Pattern |
|------|---------|
| `/platform` | Queue / Ops Console |
| `/platform/settings` | Config / Integration Console |
| `/platform/agents` | Studio / Builder **[v1.3 新增 — 从 AI 域迁入]** |

> **v1 收敛说明**：Platform 域在 v1 仅保留 2 条路由（`/platform` + `/platform/settings`）。
> data-quality / pipelines 收敛为 `/platform` 的 tab；
> accounts / data-providers / brokers 收敛为 `/platform/settings` 的 tab。
> 详见 01 IA §7.6 及 [Platform 域收敛决策](../../docs/designs/decisions/2026-03-31-product-arch-audit-fixes.md)。

<!-- 已降级: `/platform/accounts` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/brokers` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/data-providers` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/data-quality` → `/platform` 的 tab -->
<!-- 已降级: `/platform/pipelines` → `/platform` 的 tab -->

---

## 13. 落地优先级

为了让 Ditto 尽快形成统一气质，建议先做 5 套高优 Pattern，再慢慢补齐其余。

### 第一优先级

1. **Analytical Overview Workspace**
2. **Catalog / Screener Workspace**
3. **Object Hub**
4. **Studio / Builder**
5. **Queue / Ops Console**

这 5 套就能覆盖 Ditto 绝大多数核心路径。

### 第二优先级

6. **Ledger / Execution Console**
7. **Config / Integration Console**
8. **Global Command Center**

首页虽然重要，但真正决定"量化平台专业感"的，其实还是前 5 套。

---

## 14. 验收标准

一套合格的 Ditto Page Pattern Library，必须满足：

1. 全站大多数页面都能被清晰映射到某个 Pattern
2. 不同 Pattern 之间边界清晰
3. 同一 Pattern 内页感一致
4. 设计和前端都能据此复用结构
5. 用户在跨模块切换时，能感受到"同一产品，不同工作面"
6. 不会再出现"所有页面都像同一个后台模板"的问题

---

## 15. 变更日志

### v1.3 — 2026-04-18（IA v2.0 同步）

| 变更 | 章节 | 说明 |
|------|------|------|
| 移除 `/ai` | §4.2 | AI Overview 已 deprecated，从 Global Command Center 适用页面列表移除 |
| 移除 `/trading/positions`、`/trading/trades` | §5.2 | 合并为 `/trading/portfolio` |
| 新增 `/trading/portfolio` | §5.2, §12.4 | 合并原 positions + trades |
| 移除 `/markets/universes` | §5.2 | 迁移至 Research 域 |
| 新增 `/research/universes` | §12.3 | 从 Markets 域迁入（Catalog / Screener Workspace） |
| 降级 `/markets/chart-lab` | §5.2, §8.2, §12.2 | 不再作为一级路由 |
| 标记 `/markets/hk`、`/markets/us` 延后 | §5.2, §5.5, §12.2 | v1.5/v2 延后 |
| 移除 `/ai/copilot`、`/ai/agent` | §8.2 | copilot 升级为全局 Sidecar，agent 迁入 Platform |
| 新增 `/platform/agents` | §8.2, §12.6 | 从 AI 域迁入（Studio Shell） |
| §12.5 AI & Agent 整段 deprecated | §12.5 | AI 域不再作为独立路由域，添加迁移说明 |

### v1.4 — 2026-04-29（Edition Review Remediation）

| 变更 | 章节 | 说明 |
|------|------|------|
| Bottom Tray 合同 | Studio / Builder、Queue / Ops、Ledger / Execution | Studio 默认 `peek`；Ops 与 Trading 默认 `collapsed` 或按告警升级为 `peek`；Analytical 页面避免默认使用底部日志托盘。 |
| Catalog 右栏顺序 | Catalog / Screener Workspace | 右栏固定为 `summary -> status/risk -> insight/event -> actions`，summary 必须可 sticky。 |
| Catalog 批量与选中反馈 | Catalog / Screener Workspace | 选中对象不能只靠背景色；有 checkbox / 多选能力时必须暴露批量操作反馈。 |
| 危险动作链路 | Catalog、Config、Trading | 删除、回滚、暂停交易等动作必须提供影响预览、确认、取消和恢复提示。 |

Catalog 页面落地属性：

- 右栏摘要：`data-detail-sticky-summary`。
- 批量操作：`data-batch-action-bar`。
- 选中对象标记：`data-row-selection-marker`。
- 危险确认摘要：`data-danger-confirmation` 或 `data-high-risk-confirmation`。
