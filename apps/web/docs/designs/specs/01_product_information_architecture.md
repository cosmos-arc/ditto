# Ditto 产品信息架构
### v1.0

> Ditto v1 的正式产品信息架构文档。
> 本文档用于替代旧的"大而全产品设计稿"，作为后续 UI 设计、AI 设计探索、AICoding 落地的唯一上游产品结构输入。

---

## 0. 文档目标

Ditto 不是很多金融页面的集合，也不是研究、交易、AI、平台管理四五套子系统的拼装。

Ditto 的本质是一个面向个人量化研究与实盘闭环的专业工作台，服务的核心链路只有一条：

**Observe → Discover → Research → Validate → Execute → Monitor / Improve**

因此，本文件的目标不是罗列全部能力，而是明确：

- Ditto v1 到底要解决哪些核心任务
- 哪些页面是真正的主工作面
- 哪些能力应该合并、降级或后置
- 哪些页面值得优先投入 UI 设计与工程实现
- 后续视觉与代码实现应该围绕什么结构推进

---

## 1. 文档定位与关系

本文件属于 Ditto 的产品输入层文档，负责定义产品结构与页面优先级。

它不负责定义：

- 视觉原则
- 页面壳层规则
- 组件规范
- Token 命名
- 具体像素级 UI

上述内容以下列文档为准：

- `00_ditto_visual_constitution.md`
- `10_ditto_shell_family_spec.md`
- `11_ditto_page_pattern_library.md`
- `12_ditto_data_views_spec.md`
- `13_ditto_component_spec.md`
- `14_ditto_token_naming_layering_spec.md`

本文件的直接下游文档是：

- `02_core_page_blueprints.md`
- `03_object_hub_spec.md`
- `04_interaction_state_spec.md`
- `05_prompt_pack_for_ai_design_and_coding.md`

---

## 2. Ditto v1 的产品定位

Ditto 定位为：

**面向个人量化研究与实盘闭环的全市场专业工作台**

它覆盖六个核心产品域：

- Home
- Markets
- Research
- Trading
- AI
- Platform

这六个域不是六套独立产品，而是围绕同一条量化工作流展开的六个工作面。

### 2.1 Ditto v1 的核心价值

Ditto v1 最重要的不是"能力覆盖多完整"，而是以下三点是否成立：

1. 能否快速感知市场与系统当前状态
2. 能否把研究、回测、信号、订单、风险串成连续闭环
3. 能否在高密专业工作流中保持低噪声、高效率、长期可用

### 2.2 Ditto v1 不是这些东西

Ditto v1 不应被做成：

- 普通金融 SaaS 后台
- 信息展示型门户首页
- AI 聊天产品外壳
- 一个把几十个能力平铺出来的"功能超市"
- 研究工具、交易工具、运维工具的松散集合

---

## 3. Ditto v1 的产品边界

Ditto v1 只优先做强主工作流上的核心页面与核心对象。

### 3.1 v1 优先覆盖的链路

优先级最高的链路是：

**市场观察 → 对象发现 → 研究分析 → 策略构建 → 回测验证 → 信号复核 → 订单执行 → 风险监控 → 持续改进**

### 3.2 v1 优先做深的能力

- 首页指挥台
- 市场总览与筛选
- 资产对象页
- 研究工作台
- 因子分析
- 策略构建与编辑
- 回测结果
- 交易总览
- 信号中心
- 订单执行流水
- 风险中心
- AI Copilot
- Agent 工作台
- 平台健康控制台

### 3.3 v1 明确降级或后置的能力

以下内容可以保留路由或轻能力，但不作为 v1 高优独立产品设计重点：

- Home 下的多个独立子页
- Markets Map 作为重页面
- 完整 ML 平台化工作流
- 平台账户与权限管理的重建设
- 通知与集成的重型管理台
- 研究输出的大量模板化扩展

---

## 4. 一级信息架构

Ditto 一级导航固定为六个，不再扩展：

- Home
- Markets
- Research
- Trading
- AI
- Platform

这是 Ditto v1 的稳定产品骨架。

### 4.1 一级域的职责定义

#### Home

回答："今天先做什么"

#### Markets

回答："市场里发生了什么，下一步看什么"

#### Research

回答："为什么做、怎么做、值不值得做"

#### Trading

回答："信号怎么复核、订单怎么执行、风险怎么控制"

#### AI

回答："AI 如何辅助研究、生成草案、推进审批与发现"

#### Platform

回答："数据、任务、通道与系统是否正常"

---

## 5. 最终推荐 Sitemap

下面是 Ditto v1 的推荐站点地图。

```text
Ditto
│
├── Home
│   └── /
│
├── Markets
│   ├── /markets                  ← 全市场总览（Cross-Market Overview）
│   ├── /markets/a-shares         ← 中国 A 股总览
│   ├── /markets/hk               ← 港股总览（v1.5）
│   ├── /markets/us               ← 美股总览（v2）
│   ├── /markets/screener
│   ├── /markets/universes
│   ├── /markets/watchlist
│   ├── /markets/intelligence
│   ├── /markets/chart-lab
│   ├── /markets/calendar
│   └── /instruments/[id]
│
├── Research
│   ├── /research
│   ├── /research/factors
│   ├── /research/factors/[id]
│   ├── /research/strategies
│   ├── /research/strategies/[id]/studio
│   ├── /research/backtest
│   ├── /research/backtest/[id]
│   ├── /research/experiments
│   └── /research/regime
│
├── Trading
│   ├── /trading
│   ├── /trading/positions
│   ├── /trading/signals
│   ├── /trading/orders
│   ├── /trading/trades
│   └── /trading/risk
│
├── AI
│   ├── /ai
│   ├── /ai/copilot
│   └── /ai/agent
│
└── Platform
    ├── /platform
    ├── /platform/data-quality
    ├── /platform/pipelines
    ├── /platform/data-providers
    ├── /platform/brokers
    └── /platform/settings
```

---

## 6. 与旧版设计相比的关键调整

这部分是 Ditto v1 信息架构与旧大稿最大的区别，也是后续设计必须遵循的结构性调整。

### 6.1 Home 只保留一个强首页

旧方案中的以下页面不再作为高优独立产品页面设计：

- `/home/pending`
- `/home/quick-actions`
- `/home/alerts-summary`

它们应整合为 `/` 首页中的核心区块、查看全部视图或全局命令入口，而不是继续发展为独立页面体系。

### 6.2 Markets 域重构为完整域

Markets 不再等于中国 A 股页，而是覆盖跨市场扫描与单市场下钻的完整域。

- `/markets` → 全市场总览（Cross-Market Overview），核心动词 scan / compare
- `/markets/a-shares` → 中国 A 股总览，核心动词 structure scan
- 后续扩展 `/markets/hk`、`/markets/us`、`/markets/fx`、`/markets/rates`、`/markets/commodities`

详见 [全市场总览设计文档](../../plans/2026-03-29-cross-market-overview-design.md)。

### 6.3 /markets/map 降级为视图模式

`/markets/map` 不再作为高优独立页面。

它应并入以下两者之一：

- `/markets` 的视图模式
- `/markets/intelligence` 的结构可视化视图

### 6.4 /markets/intelligence/* 收敛成一个主工作区

以下内容不再作为 5 个平权产品心智：

- flow
- macro
- fundamental
- news
- network

它们统一收敛到 `/markets/intelligence` 内部，通过 tab 视图承接。

### 6.5 Strategy Builder 与 Strategy Editor 合并为 Strategy Studio

策略构建和策略编辑不再作为两个割裂产品心智，而是同一个策略对象下的两种模式：

- Form Mode
- Code Mode

统一承载于：

`/research/strategies/[id]/studio`

### 6.6 AI 市场分析 / AI 选股 / AI 策略助手合并为 Copilot Studio

AI 域不再拆成多个看似平行但边界模糊的 AI 页面。

统一收敛为：

`/ai/copilot`

Copilot 内部再区分工作模式：

- Market Analysis Mode
- Stock Discovery Mode
- Strategy Draft Mode

### 6.7 ML 能力降为 Research 子域能力

ML 能力保留，但不在 v1 中作为一级重页面与重型平台推进。

只有在真实训练、注册、部署、监控闭环足够成熟后，再升级为更重的产品结构。

### 6.8 Platform 明确定位为 Ops Console

Platform 不做"后台大全"，只聚焦：

- 数据是否可信
- 任务是否正常
- 通道是否可用
- 系统是否异常

---

## 7. 六个一级域的结构说明

### 7.1 Home

**角色**：Command Center

**目标**：在登录后第一时间帮助用户完成优先级判断与下一步分流。

**包含内容**：

- 今日总结果
- 待处理事项
- 风险与告警摘要
- 市场快照
- 最近信号 / 最近回测 / Agent findings
- 快捷动作
- 个性化工作台

**不再扩展为独立心智的内容**：

- Pending 独立页
- Quick Actions 独立页
- Alerts Summary 独立页

### 7.2 Markets

**角色**：Observe + Discover 的主工作域

**目标**：先看市场发生了什么，再找到值得进一步研究或交易的对象。

**主要页面**：

- `/markets`
- `/markets/screener`
- `/markets/universes`
- `/markets/watchlist`
- `/markets/intelligence`
- `/markets/chart-lab`
- `/markets/calendar`
- `/instruments/[id]`

**优先级排序**：

1. 全市场总览（Cross-Market Overview）
2. 中国 A 股总览
3. Markets Screener
4. Instrument Hub
5. Watchlist
6. Universes
7. Intelligence
8. Chart Lab
9. Calendar

### 7.3 Research

**角色**：Research + Validate 的主工作域

**目标**：把因子、策略、回测、实验、Regime 串成一条连续研究链。

**主要页面**：

- `/research`
- `/research/factors`
- `/research/factors/[id]`
- `/research/strategies`
- `/research/strategies/[id]/studio`
- `/research/backtest`
- `/research/backtest/[id]`
- `/research/experiments`
- `/research/regime`

**优先级排序**：

1. Research Workspace
2. Factor Analysis
3. Strategy Studio
4. Backtest Result
5. Backtest Center
6. Experiments
7. Regime

### 7.4 Trading

**角色**：Execute + Monitor 的主工作域

**目标**：让信号复核、订单执行和风险控制形成真正的实盘闭环。

**主要页面**：

- `/trading`
- `/trading/positions`
- `/trading/signals`
- `/trading/orders`
- `/trading/trades`
- `/trading/risk`

**优先级排序**：

1. Trading Overview
2. Signals Inbox
3. Orders / Execution Ledger
4. Risk Center
5. Positions
6. Trades

### 7.5 AI

**角色**：Research Acceleration + Workflow Assistance

**目标**：让 AI 融入 Ditto 工作台，而不是形成独立聊天产品。

**主要页面**：

- `/ai`
- `/ai/copilot`
- `/ai/agent`

**页面职责**：

- **`/ai`**：AI 域总览，展示最近产出、最近发现、待审批事项和高频入口。
- **`/ai/copilot`**：统一的 AI 分析与生成工作台，承接市场分析、选股辅助、策略草案。
- **`/ai/agent`**：Plan → Run → Finding → Approval 的 agent 工作台。

### 7.6 Platform

**角色**：Ops Console

**目标**：管理和感知数据、任务、通道、系统的健康状况。

**主要页面**：

- `/platform`
- `/platform/data-quality`
- `/platform/pipelines`
- `/platform/data-providers`
- `/platform/brokers`
- `/platform/settings`

**优先级排序**：

1. Platform Ops Overview
2. Data Quality
3. Pipelines
4. Data Providers
5. Brokers
6. Settings

---

## 8. 页面模式映射

Ditto v1 不应逐页重新发明，而应按统一页面模式推进。

### 8.1 Global Command Center

适用：`/`

### 8.2 Analytical Overview Workspace

适用：

- `/markets`
- `/research`
- `/trading`
- `/trading/risk`
- `/platform`（偏 ops overview）

### 8.3 Catalog / Screener Workspace

适用：

- `/markets/screener`
- `/markets/universes`
- `/markets/watchlist`
- `/research/factors`
- `/research/strategies`
- `/research/backtest`
- `/research/experiments`
- `/trading/positions`

### 8.4 Object Hub

适用：

- `/instruments/[id]`
- `/research/factors/[id]`
- `/research/backtest/[id]`

### 8.5 Studio / Builder

适用：

- `/research/strategies/[id]/studio`
- `/ai/copilot`
- `/ai/agent`
- `/markets/chart-lab`

### 8.6 Queue / Ops Console

适用：

- `/trading/signals`
- `/platform/data-quality`
- `/platform/pipelines`

### 8.7 Ledger / Execution Console

适用：

- `/trading/orders`
- `/trading/trades`

### 8.8 Config / Integration Console

适用：

- `/platform/data-providers`
- `/platform/brokers`
- `/platform/settings`

---

## 9. 核心页面优先级

Ditto v1 不应按所有页面平均推进。
优先级应集中在真正构成产品主闭环的页面模板上。

### 第一批：必须先定的 6 页

1. Home Command Center
2. Markets Overview
3. Markets Screener
4. Research Workspace
5. Trading Overview
6. Platform Ops Console

### 第二批：形成闭环的 4 页

7. Instrument Hub
8. Strategy Studio
9. Backtest Result
10. Signals Inbox

### 第三批：执行与 AI 深化的 4 页

11. Orders / Execution Ledger
12. Risk Center
13. AI Copilot Studio
14. Agent Console

---

## 10. 全局产品规则

### 10.1 Ditto 的首页不是门户页，是决策页

Home 只负责定优先级与分流，不负责承载完整子系统。

### 10.2 页面优先围绕对象与工作流组织，而不是围绕菜单树组织

Ditto 的结构必须强调"我现在在处理什么"，而不是"这个功能属于哪个大类"。

### 10.3 列表页的目标是进入下一步，不是把字段放全

所有目录、筛选、队列表都应围绕扫描、比较、跳转和批处理来设计。

### 10.4 AI 页面必须服从 Ditto 的统一工作台语法

Copilot 和 Agent 不是外部聊天产品，而是 Ditto 工作流的一部分。

### 10.5 Platform 必须保持专业控制台语法，而不是后台管理语法

Platform 的重点是状态、任务、日志、修复、可用性，而不是传统管理后台的表单堆叠。

---

## 11. 不再建议沿用的旧思路

以下思路在 Ditto v1 中不再推荐继续沿用：

- 以"所有能力都做成独立页面"为目标
- 让 Home 下挂多个重页面
- 让 Markets Map 成为平权核心页
- 让 Builder 和 Editor 成为两个割裂工作流
- 让 AI 市场分析、AI 选股、AI 策略助手成为三个独立子产品
- 让 Platform 朝"权限后台大全"方向发展
- 让 ML 平台成为 v1 主战场

---

## 12. 本文档输出给谁使用

本文件是以下工作的直接输入：

**UI / UX 设计**

用于确定先画哪些页面、不画哪些页面、哪些页面共享模板。

**AI 设计探索**

用于 Stitch 或类似工具，只探索高优核心模板页，而不是整个 sitemap。

**Claude Code / AICoding**

用于页面骨架实现与路由结构收敛，不再围绕旧大稿逐页硬翻译。

**评审**

用于判断某个页面是否真的属于 Ditto v1 的主工作流，还是应该降级、合并或后置。
