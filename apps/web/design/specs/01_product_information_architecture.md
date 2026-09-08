# Ditto 产品信息架构
### v4.0

> Ditto 的正式产品信息架构文档。
> 本文档用于替代旧的"大而全产品设计稿"，作为后续 UI 设计、AI 设计探索、AICoding 落地的唯一上游产品结构输入。
>
> **v4.0 变更摘要（2026-08-31）**：冻结 D1—D16，并把五域从产品命名落实为唯一目标路由；`/trading/*`、`/platform/*` 不再保留兼容、redirect 或双路由。
>
> **解释优先级**：本文的 v4.0 目标路由表和后端[工作站实施计划](../../../../ditto/docs/plans/2026-08-31-ditto-personal-quant-workstation-implementation-plan.md)是当前实施事实源。下文保留的旧路径只用于解释历史页面能力如何归并，不授权兼容实现。

---

## 0. 文档目标

Ditto 不是很多金融页面的集合，也不是研究、交易、平台管理三四套子系统的拼装。

Ditto 的本质是一个本地优先的 A 股量化决策与组合管理专业工作台，服务的核心链路只有一条：

**Observe → Discover → Research → Validate → Decide → Record → Review / Improve**

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

## 2. Ditto 的产品定位

Ditto 定位为：

**面向个人全栈量化投资者的本地优先 A 股量化决策、Paper Trading 与手工账户管理工作站**

核心可决策资产是 A 股个股与 A 股 ETF。A 股核心/行业指数、全球核心指数、利率、汇率、商品和宏观数据用于解释 A 股市场环境与风险，不扩展为全球证券交易。系统不连接 A 股券商，不提交、修改或撤销真实订单。

它覆盖五个核心产品域：

- Today
- Markets
- Research
- Portfolio
- System

这五个域不是五套独立产品，而是围绕同一条量化工作流展开的五个工作面。

> AI 域已拆散。Copilot 是全局 Sidecar（不属于任何域），Agent Lab 位于 `/research/agent`，Agent Ops 位于 `/system/agent`。AI 因子发现/策略生成等能力嵌入 Research 域对应页面。详见 §13 AI 嵌入方案。

### 2.1 用户画像

Ditto v1 聚焦两类核心用户：

#### Persona A: 全栈个人量化投资者

- **背景**: 3-8 年量化交易经验，日均 8+ 小时与数据/代码打交道
- **工作流**: Observe → Discover → Research → Validate → Decide → Record → Review 的完整闭环
- **痛点**: 市场环境、行业强弱、选股、研究、Paper、实际账户记录和风控分散在多个工具
- **对 Ditto 的核心期待**: "少切换工具，多输出决策"——从发现到组合和复盘在一个工作台内完成
- **密度偏好**: 高密度（多数据并排对比，表格优先于图形）

#### Persona B: 技术型投资者

- **背景**: 1-5 年投资经验，有编程基础（Python/R），正在从主观交易转向量化
- **工作流**: 以 Observe → Discover 为主，Research/Strategy 处于学习和实验阶段，Execute 依赖半自动
- **痛点**: 学习量化门槛高，回测结果难以判断好坏，不确定策略是否值得进入 Paper 或实际组合观察
- **对 Ditto 的核心期待**: "帮我看清市场和策略状态"——降低量化入门的判断成本
- **密度偏好**: 中等密度（信息层级清晰，渐进展示）

#### 内部团队角色映射

> **v1.1 补充**：基于审计修正（Ditto 非商业 SaaS，而是小型私募团队内部工具），以下定义团队内部的实际角色分工。

Ditto 的实际使用者是团队内部成员，核心角色分为三类：

**角色 1：策略研究员（Research-Heavy）**

- **核心工作流**: Factor Analysis → Strategy Studio → Backtest → Signal（Flow B 主循环）
- **日使用时段**: 盘后（15:00-22:00）为主要工作时间，盘中偶尔查看持仓
- **主力页面**: Research Workspace / Factor Analysis / Strategy Studio / Backtest Result
- **密度偏好**: 高密度（Dense 模式），多因子并排对比
- **技术栈**: Python + Jupyter，通过 Ditto 的 Code Mode 和外部 Python 环境衔接
- **核心诉求**: 因子预处理流程顺畅、回测结果可信、策略迭代效率高

**角色 2：组合管理者（Portfolio-Heavy）**

- **核心工作流**: Today → Signals → Model/Paper/我的账户 → Risk → Review
- **日使用时段**: 交易时段（9:15-15:00）为主，盘后查看归因
- **主力页面**: Today / Portfolio Overview / Signals Inbox / Paper Account / 我的账户 / Risk Center
- **密度偏好**: 高密度（Dense 模式），信号复核需快速扫描
- **设备环境**: 单屏或双屏，1920×1080+
- **核心诉求**: 信号复核速度、Paper 连续性、实际交易录入与更正、账户偏差和盘后复盘效率

**角色 3：系统维护者（System-Heavy）**

- **核心工作流**: System → 数据质量监控 → 配置管理
- **日使用时段**: 非交易时段为主（盘前检查、盘后维护）
- **主力页面**: System Ops Console / Settings
- **密度偏好**: 中等密度（Compact 模式），关注系统状态而非交易数据
- **核心诉求**: 数据源状态一目了然、异常快速定位、配置变更可追溯

**角色间的协同关系**：

```
策略研究员 ──生成信号──→ 组合管理者 ──反馈 Paper/实际记录──→ 策略研究员
                              │
                              └──风控异常──→ 策略研究员（Flow D）
系统维护者 ←──依赖── 组合管理者 + 策略研究员（数据/任务/系统健康）
```

### 2.2 Ditto v1 的核心价值

Ditto v1 最重要的不是"能力覆盖多完整"，而是以下三点是否成立：

1. 能否快速感知市场与系统当前状态
2. 能否把宏观/市场、行业、选股、研究、回测、信号、Model/Paper/Manual、风险串成连续闭环
3. 能否在高密专业工作流中保持低噪声、高效率、长期可用

### 2.3 Ditto v1 不是这些东西

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

**宏观/市场观察 → 行业与个股发现 → 研究分析 → 策略构建 → 回测验证 → 信号复核 → Model/Paper/Manual 记录 → 风险监控 → 持续改进**

### 3.2 v1 优先做深的能力

- 首页指挥台
- 市场总览与筛选
- 资产对象页
- 研究工作台
- Alpha Explorer
- 因子分析
- 策略构建与编辑
- 回测结果
- 组合总览
- 信号中心
- Paper 订单与成交流水
- 我的账户（手工记录、导入和追加式更正）
- 风险中心
- AI Copilot（全局 Sidecar）
- Agent Console（System 域）
- 平台健康控制台

### 3.3 v1 明确降级或后置的能力

以下内容可以保留路由或轻能力，但不作为 v1 高优独立产品设计重点：

- Today 下的多个独立子页
- Markets Map 作为重页面
- 完整 ML 平台化工作流
- 平台账户与权限管理的重建设
- 通知与集成的重型管理台
- 研究输出的大量模板化扩展

---

## 4. 一级信息架构

Ditto 一级导航固定为五个，不再扩展：

- Today
- Markets
- Research
- Portfolio
- System

这是 Ditto v1 的稳定产品骨架。

> AI 从一级导航中移除。Copilot 以全局 Sidecar 形式存在（任何页面可唤出），Agent Console 归入 System 域。

### 4.1 一级域的职责定义

#### Today

回答："今天先做什么"

#### Markets

回答："市场里发生了什么"

#### Research

回答："为什么做、怎么做"

#### Portfolio

回答："模型、Paper 和我的实际账户发生了什么"

#### System

回答："系统是否正常"

---

## 5. 最终目标 Sitemap

下面是 Ditto v1 的唯一目标站点地图。路由硬切不提供 redirect。

```text
Ditto
│
├── Today (1)
│   └── /
│
├── Markets (6)
│   ├── /markets                  ← 全市场总览（Cross-Market Overview）
│   ├── /markets/a-shares         ← 中国 A 股总览
│   ├── /markets/industries       ← 行业轮动与行业 Inspector
│   ├── /markets/screener
│   ├── /markets/watchlist
│   └── /instruments/[id]
│
├── Research (8)
│   ├── /research
│   ├── /research/universes
│   ├── /research/factors
│   ├── /research/experiments
│   ├── /research/backtests
│   ├── /research/strategies
│   ├── /research/agent           ← Agent Lab / Strategy Author
│   └── /research/reviews
│
├── Portfolio (7)
│   ├── /portfolio                ← 三组合总览与比较
│   ├── /portfolio/model
│   ├── /portfolio/paper
│   ├── /portfolio/manual
│   ├── /portfolio/transactions
│   ├── /portfolio/risk
│   └── /portfolio/review
│
├── System (7)
│   ├── /system                   ← 系统运维总览
│   ├── /system/data-products
│   ├── /system/jobs
│   ├── /system/agent            ← Agent Ops
│   ├── /system/approvals
│   ├── /system/settings         ← 只读 Data Providers；无 Broker
│   └── /system/audit
│
└── Global (非路由)
    ├── AI Copilot Sidecar        ← 全局右侧可折叠面板，上下文感知
    └── Regime Indicator          ← Shell 级全局组件（Status Bar 胶囊 → 展开面板）
```

**目标路由统计**：5 域，29 条主路由 + 2 个全局组件。对象详情使用参数化子路由，不恢复旧产品域。

**硬切清单**：删除 `/trading`、`/platform` 及其子路由；删除旧 route contracts、navigation entries 和 feature 命名；不添加兼容 redirect、双读或别名。

> **v2.1 变更**：
> - 新增 `/research/alpha`，作为 Research 域内的 Alpha Explorer，不恢复 AI 一级域
> - Alpha Discovery 从泛 Copilot 模式升级为完整研究工作台，Agent Console 只保留长任务治理与深链入口
>
> **v2.0 变更**：
> - 移除 AI 域（Copilot → 全局 Sidecar，Agent Console → `/platform/agents`）
> - `/markets/universes` 移入 Research 域
> - `/markets/chart-lab` 降级为 Instrument Hub 的 tab
> - `/markets/hk`、`/markets/us` 延后
> - `/trading/positions` + `/trading/trades` 合并为 `/trading/portfolio`
> - 新增 `/research/universes`、`/platform/agents`

---

## 6. 与旧版设计相比的关键调整

这部分是 Ditto v1 信息架构与旧大稿最大的区别，也是后续设计必须遵循的结构性调整。

### 6.1 Today 只保留一个强首页

旧方案中的以下页面不再作为高优独立产品页面设计：

- `/home/pending`
- `/home/quick-actions`
- `/home/alerts-summary`

它们应整合为 `/` Today 中的核心区块、查看全部视图或全局命令入口，而不是继续发展为独立页面体系。

### 6.2 Markets 域围绕 A 股决策重构

Markets 同时覆盖环境扫描与 A 股下钻，但全球市场只作为参照，不形成可交易市场域。

- `/markets` → 市场环境总览，覆盖全球核心指数、利率、汇率、商品、宏观与 A 股市场状态，核心动词 scan / compare / explain
- `/markets/a-shares` → 中国 A 股总览，核心动词 structure scan
- 全球参照优先作为 `/markets` 的矩阵和下钻视图，不建立全球证券交易、外币账户或结算心智

详见 [全市场总览设计文档](../../plans/2026-03-29-cross-market-overview-design.md)。

**v2.0 调整**：

- `/markets/universes` 移入 Research 域（标的池管理本质是研究工作）
- `/markets/chart-lab` 降级为 Instrument Hub 的 tab（不独立成路由）
- `/markets/hk`、`/markets/us` 延后（v1.5+ 再考虑）

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

### 6.6 AI 域拆散嵌入

**v2.0 重大调整**：AI 域作为一级域不再存在。AI 能力以嵌入方式分布在各域中：

- **Copilot** → 全局 Sidecar（右侧可折叠面板），任何页面可唤出，不属于任何域
- **Agent Console** → `/platform/agents`（技术路径，产品归入 System 域）
- **AI Overview** 内容 → 拆分归入 Today（Daily Brief / Priority Findings）和 System/Agents
- **AI 因子发现 / 策略生成** → 嵌入 Research 域对应页面

详见 §13 AI 嵌入方案。

### 6.7 ML 能力降为 Research 子域能力

ML 能力保留，但不在 v1 中作为一级重页面与重型平台推进。

只有在真实训练、注册、部署、监控闭环足够成熟后，再升级为更重的产品结构。

### 6.8 System 承接运维 + Agent 管理

System 不做"后台大全"，聚焦：

- 数据是否可信
- 任务是否正常
- 只读数据源是否可用
- 系统是否异常
- Agent 运行状态与审批（v2.0 新增）

Agent Ops 使用 `/system/agent`；Research 内的业务 Agent 工作台使用 `/research/agent`。旧 `/ai/agent` 与 `/platform/agents` 均不保留。

### 6.9 Portfolio 明确三类组合事实

Portfolio 只使用 `/portfolio/*` 路径，并按账户事实切换：

- Model（目标组合与调仓意图）
- Paper（模拟订单、成交、现金、持仓与 PnL）
- 我的账户（Manual 实际交易与现金事件、持仓和归因）

三者可以比较，不得共用一套可变持仓记录来伪装不同账户。

---

## 7. 五个一级域的结构说明

### 7.1 Today

**角色**：Global Command Center（定向/分流型）

**核心动词**：orient（理解 → 分流）

**目标**：在登录后第一时间帮助用户完成优先级判断与下一步分流。Today 是雷达，不是驾驶舱——它回答"今天先做什么"和"该去哪个工作区"，不承担组合写入操作。

**包含内容**：

- Status Banner（组合状态 + 市场判断 + 分流 CTA）
- 今日优先事项（跨域 3-5 条，预览级）
- 市场脉搏（4 指标，极轻）
- 全局预警（3-4 条，单行预览）
- Priority Findings + Research Queue（底部双栏）
- 数据健康（preview 摘要）

**不再扩展为独立心智的内容**：

- Pending 独立页（已收敛为 Home 核心区块）
- Quick Actions 独立页（已收敛为 Home 分流 CTA）
- Alerts Summary 独立页（已收敛为 Home 右 Rail 预览）

> **与 Trading 域的 Command Center 区分**：Home 的核心动词是 orient（定向/分流），CTA 语气是导航型（查看/进入/打开）；Trading 的 Command Center 核心动词是 execute（判断/执行），CTA 语气是操作型（执行/复核/确认）。详见 [Home vs Command Center 分家决策](../../docs/designs/decisions/2026-03-28-home-vs-command-center.md)。

**冷启动引导**：

新用户首次进入 Today 时，核心区块可能为空（无持仓、无信号、无研究进展）。此时 Today 应：
- Status Banner 显示"开始使用 Ditto"引导 CTA，而非空白或默认数据
- 今日优先事项区域显示 2-3 条"快速入门"引导（添加第一个观察标的 / 运行第一次回测 / 配置数据源）
- 市场脉搏始终展示（不依赖用户状态，作为持续可用的环境信息）
- 全局预警区域在无预警时显示"一切正常"的状态标识，而非空白

### 7.2 Markets

**角色**：Observe + Discover 的主工作域

**目标**：先看市场发生了什么，再找到值得进一步研究或交易的对象。

**主要页面**：

- `/markets`
- `/markets/screener`
- `/markets/watchlist`
- `/markets/intelligence`
- `/markets/calendar`
- `/instruments/[id]`

> **v2.0 调整**：`/markets/universes` 移入 Research 域，`/markets/chart-lab` 降级为 Instrument Hub 的 tab，`/markets/hk` 和 `/markets/us` 延后。

**A 股特有功能嵌入**：

以下 A 股特有能力不作为独立路由，而是嵌入现有页面：

- **龙虎榜**: 嵌入 A 股总览（`/markets/a-shares`）的 Bottom Tab Band
- **两融数据**: 嵌入 A 股总览 Bottom Tab Band 和 Portfolio Overview Session Strip
- **北向资金深度**: 嵌入 A 股总览 Right Rail（分时净流入、持仓 Top10 变动）
- **停牌/复牌状态**: 嵌入 Instrument Hub Object Header（状态标识 + Meta Strip 日期）
- **交易阶段指示**: 嵌入 Portfolio Overview Session Strip（集合竞价/连续竞价/午休/收盘）

> **扩展预留**: 债券（可转债 T+0 套利）、公募基金、C-REITs 为 v2+ 扩展点。Instrument Hub 的 Tab 设计应为不同资产类型预留差异视图。

**优先级排序**：

1. 全市场总览（Cross-Market Overview）
2. 中国 A 股总览
3. Markets Screener
4. Instrument Hub
5. Watchlist
6. Intelligence
7. Calendar

### 7.3 Research

**角色**：Research + Validate 的主工作域

**目标**：把因子、策略、回测、实验、Regime、标的池串成一条连续研究链。

**主要页面**：

- `/research`
- `/research/factors`
- `/research/factors/[id]`
- `/research/strategies`
- `/research/strategies/[id]`（Strategy Detail — 查看态）
- `/research/strategies/[id]/studio`
- `/research/backtest`
- `/research/backtest/[id]`
- `/research/experiments`
- `/research/regime`
- `/research/universes`（v2.0 从 Markets 移入）

**优先级排序**：

1. Research Workspace
2. Factor Analysis
3. Strategy Studio
4. Backtest Result
5. Backtest Center
6. Experiments
7. Regime
8. Universes

### 7.4 Portfolio

**角色**：Decide + Record + Review 的主工作域

**目标**：让信号复核、目标组合、Paper 模拟、手工实际账户、风险与复盘形成可重建的个人组合闭环。

**主要页面**：`/portfolio`、`/portfolio/model`、`/portfolio/paper`、`/portfolio/manual`、`/portfolio/transactions`、`/portfolio/risk`、`/portfolio/review`。

Portfolio 内必须明确区分 Model、Paper 和“我的账户·手工记录”，不得显示券商连接或真实下单心智。

**Portfolio Overview 核心结构**（v3.0）：

- **Market-to-Portfolio Evidence Strip**：展示宏观/全球 → A 股市场 → 行业 → 个股 → 信号 → Model/Paper/Manual → 风险/归因的可下钻证据链。
- **三类事实切换**：Model 是目标与意图；Paper 是模拟订单/成交产生的账户；Manual 是用户实际账户的手工事实账本。
- **Paper Pipeline**：展示信号池 → 待复核 → Paper Order → Simulated Fill → Reconciled，禁止使用会暗示真实券商写入的文案。
- **Manual Event Ledger**：支持无 Signal 的买卖、入金、出金、费用、税费、分红和转入转出，以及保留原事实的 void/replace 更正。

**A 股交易规则 UI 约束**：

Portfolio 域的 Paper 模拟与账户解释必须体现以下 A 股市场规则：

- **T+1 交收**: 持仓表中必须区分"可卖数量"和"冻结数量"（当日买入不可卖出）
- **涨跌停校验**: 信号复核时必须检查标的是否处于涨跌停状态（涨停时买入信号无效，跌停时卖出信号无效）
- **Paper 订单类型**: 可模拟限价和市价撮合；所有成交必须显示撮合、费用与滑点假设
- **最小交易单位**: 最小买入 100 股（1 手），卖出可零股
- **ST/\*ST 约束**: ST 标的涨跌停 ±5%，策略 Universe 筛选应支持排除 ST

**优先级排序**：

1. Portfolio Overview
2. Signals Inbox
3. Paper Account（Orders / Fills / Cash / Positions / PnL）
4. 我的账户（Manual Events / Positions / Cash / Attribution）
5. Risk Center

### 7.5 System

**角色**：Ops Console + Agent 管理

**目标**：管理和感知只读数据源、任务、系统健康状况，以及 Agent 运行状态与审批。

**主要页面**：`/system`、`/system/data-products`、`/system/jobs`、`/system/agent`、`/system/approvals`、`/system/settings`、`/system/audit`。

> **v3.0 边界**：Broker 不是等待拆分的设置项，而是产品明确排除的能力。实时行情 Provider 只能使用只读合同，不能携带账户查询、下单、撤单或成交回报权限。

**优先级排序**：

1. System Ops Overview
2. Agent Console
3. Settings（只读 Data Providers / 通用）

---

## 8. 页面模式映射

Ditto v1 不应逐页重新发明，而应按统一页面模式推进。

### 8.1 Global Command Center

适用：

- `/`

### 8.2 Analytical Overview Workspace

适用：

- `/markets`
- `/markets/a-shares`
- `/markets/watchlist`
- `/research`
- `/trading`
- `/trading/portfolio`
- `/trading/risk`

### 8.3 Catalog / Screener Workspace

适用：

- `/markets/screener`
- `/research/factors`
- `/research/strategies`
- `/research/backtest`
- `/research/experiments`
- `/research/universes`

### 8.4 Object Hub

适用：

- `/instruments/[id]`
- `/research/factors/[id]`
- `/research/strategies/[id]`
- `/research/backtest/[id]`

### 8.5 Studio / Builder

适用：

- `/research/strategies/[id]/studio`
- `/platform/agents`

### 8.6 Queue / Ops Console

适用：

- `/trading/signals`
- `/platform`（Data Quality / Pipelines 作为 tab 承载于 Ops Console）

### 8.7 Paper / Manual Ledger

适用：

- `/trading/orders`

### 8.8 Config / Data Provider Console

适用：

- `/platform/settings`（只读 Data Providers 与通用设置；不含 Broker）

> **映射说明**：Shell（物理壳层布局）和 Pattern（交互模式）描述不同维度。同一 Pattern 可对应多种 Shell 布局（如 Ledger Pattern 在 Shell 层用 Catalog 壳层的表格+详情面板结构），这是正常的维度差异，不是矛盾。
>
> **v2.0 映射变更**：
> - `/ai`、`/ai/copilot`、`/ai/agent` 不再作为独立路由（AI 域已拆散）
> - `/trading/positions`、`/trading/trades` 合并为 `/trading/portfolio`，迁移期归属 Portfolio 的 Analytical Overview Workspace
> - `/markets/universes` 移至 Research 域，归属 Catalog / Screener Workspace
> - `/markets/chart-lab` 降级为 Instrument Hub tab，不再独立映射
> - `/platform/agents` 新增，归属 Studio / Builder

---

## 9. 核心页面优先级

Ditto v1 不应按所有页面平均推进。
优先级应集中在真正构成产品主闭环的页面模板上。

### 第一批：必须先定的 6 页

1. Today
2. Markets Overview
3. Markets Screener
4. Research Workspace
5. Portfolio Overview
6. System Ops Console

### 第二批：形成闭环的 5 页

7. Instrument Hub
8. Alpha Explorer
9. Strategy Studio
10. Backtest Result
11. Signals Inbox

### 第三批：账户、风险与 Agent 深化的 5 页

12. Paper Account / Simulation Ledger
13. 我的账户 / Manual Event Ledger
14. Risk Center
15. Model/Paper/Manual Attribution
16. Agent Console（`/platform/agents`）

---

## 10. 全局产品规则

### 10.1 Today 不是门户页，是决策页

Today 只负责定优先级与分流，不负责承载完整子系统。

### 10.2 页面优先围绕对象与工作流组织，而不是围绕菜单树组织

Ditto 的结构必须强调"我现在在处理什么"，而不是"这个功能属于哪个大类"。

### 10.3 列表页的目标是进入下一步，不是把字段放全

所有目录、筛选、队列表都应围绕扫描、比较、跳转和批处理来设计。

### 10.4 AI 能力必须服从 Ditto 的统一工作台语法

Copilot 和 Agent 不是外部聊天产品，而是 Ditto 工作流的一部分。Copilot 以全局 Sidecar 形式存在，Agent Console 归入 System 域。AI 能力嵌入各业务域，而非形成独立产品心智。

### 10.5 System 必须保持专业控制台语法，而不是后台管理语法

System 的重点是状态、任务、日志、修复、可用性和 Agent 管理，而不是传统管理后台的表单堆叠。

---

## 11. 不再建议沿用的旧思路

以下思路在 Ditto v1 中不再推荐继续沿用：

- 以"所有能力都做成独立页面"为目标
- 让 Today 下挂多个重页面
- 让 Markets Map 成为平权核心页
- 让 Builder 和 Editor 成为两个割裂工作流
- 让 AI 市场分析、AI 选股、AI 策略助手成为三个独立子产品
- 让 AI 成为独立一级域（v2.0 已拆散嵌入各业务域）
- 让 System 朝"权限后台大全"方向发展
- 让 ML 平台成为 v1 主战场

---

## 12. AI 嵌入方案

> **v2.1 更新**。AI 域拆散后，AI 能力以嵌入方式分布在 Ditto 各处；其中因子发现升级为 Research 域业务页 `/research/alpha`。本节明确每种 AI 能力的归属位置与交互形态。

### 12.1 AI Copilot Sidecar

**位置**：全局右侧可折叠面板，不属于任何域。

**交互形态**：

- 任何页面可通过快捷键或 Header 按钮唤出
- 上下文感知：根据当前页面自动加载相关上下文（如 Markets 页面加载市场数据，Research 页面加载因子/策略信息）
- 支持对话、结构化输出、建议采纳

**取代**：原 `/ai/copilot` 独立路由。

### 12.2 Agent Console

**位置**：`/platform/agents`

**职责**：Plan → Run → Finding → Approval 的 Agent 工作台。

**包含内容**：

- Agent 任务列表与状态
- 运行时间线（Agent Run Timeline）
- 工具调用追踪（Tool Trace）
- 审批请求（Approval Request Block）
- 产出结果（Output Artifact Block）

**取代**：原 `/ai/agent` 路由。

### 12.3 嵌入式 AI 能力

| 能力 | 嵌入位置 | 交互形态 |
|------|---------|---------|
| Daily Quant Brief | `/` | 结构化 Finding、Pending Approval、Data Health 和 Research Queue |
| Priority Findings | `/` | 首页摘要卡片，按严重度和时效聚合 Agent Finding、Signal Review、Factor Candidate |
| Alpha Discovery | `/research/alpha` | Search Space Config、Exploration Stream、Pareto Frontier、Candidate Inspector、Adoption Queue |
| AutoResearch Review | `/platform/agents` + `/research/alpha?run=$id` | Console 负责 Run 治理，Alpha Explorer 负责因子研究审阅 |
| 因子诊断 | `/research/factors/[id]` | 对已入库因子的 IC、换手、暴露、相关性和衰减做诊断 |
| 策略生成 | `/research/strategies/[id]/studio` | Manual / Guided / Agent 三模式，产出 StrategySpecDraft 和 BacktestDraft |
| 策略维护 | `/research/strategies/[id]` 优化 tab | Optimization Proposal、Simulation Drawer、Change Diff |
| Trading AI Review | `/trading/signals` | AI Interpretation、Risk Officer Decision、Evidence Chain、Approval Actions |
| 市场分析 | `/markets`、`/markets/a-shares` | Copilot Sidecar 内的 Market Analysis Mode |
| 选股辅助 | `/markets/screener` | Copilot Sidecar 内的 Stock Discovery Mode |
| Agent Quality | `/platform/agents` Quality tab | Eval Task Set、Score Board、Regression History、Failure Gallery |
| AI Governance | `/platform/settings` AI section | Model Policy、Tool Permission、Budget、Approval、Guardrail、Audit Retention |
| AI 概览内容 | Home + `/platform/agents` | Daily Brief / Priority Findings（Home）+ Agent 任务列表（Platform） |

### 12.4 已废弃的 AI 路由

| 路由 | 处理方式 |
|------|---------|
| `/ai` | 拆分内容归入 Home（Daily Brief / Priority Findings）和 `/platform/agents` |
| `/ai/copilot` | 升级为全局 Copilot Sidecar |
| `/ai/agent` | 迁移至 `/platform/agents` |

---

## 13. 全局组件

> **v2.0 新增**。除一级域和路由外，Ditto 还有不属于任何域的 Shell 级全局组件。

### 13.1 Regime Indicator

**角色**：Shell 级全局组件，展示当前市场状态（Risk-On / Risk-Off / Mixed）。

**位置**：Status Bar 胶囊。

**交互**：

- 默认显示为 Status Bar 中的小胶囊，标注当前 Regime 状态和置信度
- 点击展开面板，展示 Regime 模型详情、切换历史、驱动因素
- 面板可收起，不占用主工作区空间

**数据源**：`/research/regime` 中的 Regime Model。

### 13.2 AI Copilot Sidecar

**角色**：全局右侧可折叠面板，提供上下文感知的 AI 对话与分析能力。

**位置**：页面右侧，可折叠。

**交互**：

- 通过快捷键（如 `Cmd+K` 或 `Ctrl+K`）或 Header 按钮唤出/收起
- 展开时主工作区宽度自适应收缩
- 上下文随当前页面自动切换
- 支持 Market Analysis / Stock Discovery / Strategy Draft / Factor Discovery 等工作模式

详见 §12.1。

---

## 14. 本文档输出给谁使用

本文件是以下工作的直接输入：

**UI / UX 设计**

用于确定先画哪些页面、不画哪些页面、哪些页面共享模板。

**AI 设计探索**

用于 Stitch 或类似工具，只探索高优核心模板页，而不是整个 sitemap。

**Claude Code / AICoding**

用于页面骨架实现与路由结构收敛，不再围绕旧大稿逐页硬翻译。

**评审**

用于判断某个页面是否真的属于 Ditto v1 的主工作流，还是应该降级、合并或后置。

---

## Changelog

### 2026-08-30 — v3.0

- **[产品边界]** 核心可决策资产确认为 A 股个股与 ETF；全球核心市场与宏观数据只作为 A 股环境参照。
- **[Discover 主干]** 行业强弱、轮动、个股筛选/排名/比较升级为一级核心流程。
- **[执行边界]** 移除券商下单心智；实时行情 Provider 只读。
- **[账户模型]** 明确 Model、Paper、Manual 三类事实和 Paper/Manual 双账本。
- **[一级域]** 用户可见心智调整为 Today / Markets / Research / Portfolio / System；旧路径仅作迁移兼容。
- **[设计与验收]** 保留 Graphite Studio，以市场到组合证据链为产品签名，以真实数据和端到端任务而非页面数量验收。

### 2026-05-02 — v2.1

- **[新增路由]** `/research/alpha`，作为 Research 域内的 Alpha Explorer，不恢复 AI 一级域。
- **[IA 收敛]** AutoResearch 的治理入口保留在 `/platform/agents`，研究审阅入口深链到 `/research/alpha`。
- **[AI 嵌入]** 补齐 Daily Brief、Strategy AI、Signals AI Review、Agent Quality、AI Governance 的页面归属。
- **[路由统计]** 从 27 路由调整为 28 路由 + 2 个全局组件。

### 2026-04-18 — v2.0

- **[架构重构]** AI 域拆散嵌入，域结构从 6 域收敛为 5 域（移除 AI 域）
- **[AI 嵌入]** Copilot 升级为全局 Sidecar（§12.1），Agent Console 迁入 `/platform/agents`（§12.2）
- **[路由变更]** `/markets/universes` 移入 Research 域为 `/research/universes`
- **[路由变更]** `/markets/chart-lab` 降级为 Instrument Hub 的 tab
- **[路由变更]** `/markets/hk`、`/markets/us` 延后至 v1.5+
- **[路由合并]** `/trading/positions` + `/trading/trades` 合并为 `/trading/portfolio`（含 Positions/Trades/Attribution 三个 tab）
- **[新增路由]** `/platform/agents`（Agent Console）
- **[新增路由]** `/research/strategies/[id]`（Strategy Detail）
- **[新增组件]** Trading Overview Signal-to-Order Pipeline Strip（§7.4）
- **[新增章节]** §12 AI 嵌入方案、§13 全局组件（Regime Indicator + Copilot Sidecar）
- **[路由统计]** 从 29 路由精简为 27 路由 + 2 个全局组件

### 2026-03-31 — v1.1

- **[审计 Q3-4]** §2.1 新增内部团队角色映射（策略研究员/交易执行者/系统维护者），含角色协同关系图
