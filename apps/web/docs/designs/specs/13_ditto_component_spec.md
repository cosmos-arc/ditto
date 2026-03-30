# Ditto Component Spec

> **版本**：v1.0
> **日期**：2026-03-28
> **状态**：Final
> **上游**：[10 Shell Family 规范](./10_ditto_shell_family_spec.md)、[12 Data Views 规范](./12_ditto_data_views_spec.md)、[04 交互与状态规范](./04_interaction_state_spec.md)
> **下游**：[14 Token Naming & Layering 规范](./14_ditto_token_naming_layering_spec.md)
> **职责**：定义按钮、面板、标签、抽屉、AI / Agent 组件等角色化组件体系
>
> 适用范围：Ditto 全站通用组件、中层工作区组件、AI / Agent 特殊组件
> 目标：把组件从"UI kit 零件"升级为"符合 terminal 工作台语法的角色化组件体系"

---

## 1. 文档目标

到这一步，Ditto 已经有了：

- **Shell Family**: 解决"页面壳层是什么"
- **Page Pattern Library**: 解决"页面模式是什么"
- **Data Views**: 解决"表、图、上下文工作面怎么组织"

但如果没有统一的组件角色体系，最终还是会被组件库默认范式拖回普通 SaaS 或后台系统。

因为真正影响落地质量的，不只是页面结构，更是这些细节：

- 按钮是不是到处都像 CTA
- badge 是状态标签还是分类标签
- panel 是主工作面还是普通卡片
- command bar 是全局命令入口还是普通搜索框
- drawer 是 drill-down 还是临时弹窗
- AI block 是聊天泡泡还是研究助手工作块

所以这份文档的目标，不是列出"有哪些组件"，而是定义：

- 组件在 Ditto 中承担什么角色
- 同一类型组件内部如何分级
- 哪些组件适用于哪些 Page Pattern
- 哪些反模式会让 Ditto 退化成后台感或 AI 工具感

---

## 2. 总体原则

### 原则 1：组件先按角色分，再按 HTML / UI 类型分

Ditto 的组件不能先按 button、badge、card、modal、input 这种传统分类理解。
更合理的方式是先问：

- 它是页面骨架的一部分吗
- 它是工作区节奏的一部分吗
- 它是数据工作面的一部分吗
- 它是动作入口吗
- 它是上下文展开吗
- 它是状态反馈吗
- 它是 AI / Agent 专属语法吗

### 原则 2：组件语气必须服从 terminal 工作台，而不是服从 UI kit 默认值

同样是 button、badge、panel、drawer，Ditto 的组件语气必须偏：

- 克制
- 精准
- 可判断
- 低噪声
- 可长期使用

而不是偏：

- 强营销
- 过度卡片化
- 过度表单化
- 过度社交化
- 过度 AI 工具化

### 原则 3：组件的级别必须明确，不允许"全都差不多重要"

大多数组件问题，不是不好看，而是全都在抢注意力。
所以 Ditto 的组件必须有清晰层级：

- 什么是一级动作
- 什么是工作区动作
- 什么是行内动作
- 什么是严重状态
- 什么是编码标签
- 什么是筛选条件

### 原则 4：组件要支持高密，但不能变脏

Ditto 的很多页面都是高密工作环境。
组件需要在高密布局中依然保持：

- 对齐
- 节奏
- 字体纪律
- 状态清晰
- 反馈可预期

### 原则 5：AI / Agent 组件必须融入 Ditto，而不是另起一套 Chat 产品语法

这是非常关键的。
AI 页如果完全照聊天产品做，整个 Ditto 会断裂。
所以 AI / Agent 组件必须更像：

- 研究助手日志
- 任务执行块
- 审批与运行块
- 工具调用记录

而不是社交气泡和随意对话流。

---

## 3. 组件体系总览

Ditto 的组件建议分为 7 大组：

| 组 | 职责 |
|---|---|
| **Shell Components** | 页面壳层与全站结构 |
| **Workspace Components** | 页面内部节奏组织 |
| **Data Components** | 表、图、时间线、状态表达 |
| **Action Components** | 动作入口与等级 |
| **Overlay Components** | drill-down、确认、弹出 |
| **Feedback Components** | 反馈层级 |
| **AI / Agent Components** | AI 专属语法 |

下面逐组展开。

---

## Part A — Shell Components

### 4. Shell Components 定义

Shell Components 是构成页面壳层和全站工作区结构的组件。
它们决定用户进入页面后首先感受到的骨架和上下文。

包括：

- Rail
- Workspace Header
- Global Header
- Context Strip / Pulse Strip
- Context Bar（Radar Shell 专用，双层 Context 的上层）
- Scope Strip（Radar Shell 专用，双层 Context 的下层）
- Right Rail Container（Radar Shell 专用，30% 辅工作面）
- Bottom Tab Band Container（Radar Shell 专用，底部 Tab 区）
- Analysis Band Container
- Activity / Context Side Container
- Global Banner
- Command Surface

它们不是"通用小组件"，而是 Layout 级组件。

### 5. Rail

#### 5.1 角色

- 一级模块切换器
- 全站导航骨架的一部分
- 不承担树状菜单

#### 5.2 适用场景

全站壳层几乎都使用

#### 5.3 规则

- 永远窄
- 图标优先
- active 态细而准
- 不做宽侧边栏
- 不展开大量二级菜单

#### 5.4 不允许

- 长文字导航常驻
- 每个模块下面挂大量子项
- 让 rail 成为页面视觉中心

### 6. Header 家族

Ditto 不应该只有一种 header，而应按 shell 角色分为：

| Header 类型 | 适用 Page Pattern | 强调重点 |
|---|---|---|
| **Global Header** | Command Center | 全局状态、command search、today context |
| **Workspace Header** | Analytical / Catalog | 当前 workspace、scope、主动作 |
| **Object Header** | Object Hub | 对象身份、状态、版本、对象级动作 |
| **Studio Header** | Builder / Editor / Copilot / Agent | session、save/run/publish、runtime state |
| **Ops Header** | Queue / Ops / Platform Overview | 环境、severity、系统范围、处置动作 |
| **Config Header** | Integration / Settings / Accounts | save / validate / test / rollback |

### 7. Strip 家族

Strip 是低高度、高信息密度的状态与范围层。

| Strip 类型 | 适用场景 | 表达内容 |
|---|---|---|
| **Pulse Strip** | Analytical 总览页 | 总体运行态与计数 |
| **Scope Strip** | Catalog / Ledger / Ops | 当前筛选范围、状态、结果量 |
| **Meta Strip** | Object Hub | 对象标签、时间、关联、版本等 |
| **Validation Strip** | Config / Integration | 连接状态、验证结果、最近测试结果 |
| **Session Strip** | Trading / Execution / Studio | 当前交易 session、run state、runtime 状态 |

### 8. Side Container 家族

右侧区不应只有一种"sidebar"。

建议至少区分：

| 容器类型 | 适用场景 |
|---|---|
| **Activity Stack Container** | activity feed、event log |
| **Inspector Container** | object properties、schema |
| **Detail / Logs Container** | execution log、trace |
| **Studio Context Container** | editor context、tool output |

这几种容器可共用基本 panel 语法，但 header、section、item 和行为都不同。

---

## Part B — Workspace Components

### 9. Workspace Components 定义

Workspace Components 是页面内部组织节奏的中层组件。
它们决定页面里不同工作面之间如何衔接。

包括：

- Panel
- Section Header
- Toolbar
- Scope Tabs
- Filter Bar
- Summary Strip
- Queue Block
- Insight Block
- Metric Block

### 10. Panel 家族

这是最容易做坏的一组。
Ditto 不应把所有 panel 都叫 Card。

建议分 6 类：

#### 10.1 Main Panel

**主仪表容器**

适用：

- 主表
- 主图
- editor 主区

规则：

- 视觉权重最高
- padding 更稳定
- 不靠厚阴影和粗边框撑场面

#### 10.2 Support Panel

**辅助图表 / 辅助列表容器**

适用：

- analysis chart
- secondary list
- related objects

#### 10.3 Continuous Panel

**连续工作流面板**

适用：

- activity stack
- analysis band
- multi-section side panel

关键特征：

- 整体是一根连续区
- section 之间轻分隔
- 不碎卡片化

#### 10.4 Inspector Panel

**检查器、属性、预览面板**

适用：

- preview
- object summary
- config inspect
- schema inspect

#### 10.5 Config Panel

**配置面板**

适用：

- settings form
- broker config
- model config
- strategy params

#### 10.6 Log / Incident Panel

**日志、trace、incident detail 容器**

适用：

- pipelines
- jobs
- execution trace
- errors
- alerts

### 11. Section Header

Section Header 用于 panel 内部 section 分段。
不是页面级标题。

#### 11.1 作用

- 说明这一段是什么
- 帮助扫描
- 可附带轻动作

#### 11.2 允许内容

- 标题
- 轻计数
- view all / collapse / more

#### 11.3 不允许

- 重图标
- 粗底条
- 大按钮
- 冗长说明文案

#### 11.4 语气

- 字重中等
- 对比弱于主标题
- 强调组织，不强调存在感

### 12. Toolbar 家族

Toolbar 在 Ditto 中非常关键，不应退化为按钮堆积条。

| Toolbar 类型 | 服务对象 | 重点功能 |
|---|---|---|
| **Workspace Toolbar** | header 下或主 panel 顶部 | workspace 级动作和视图切换 |
| **Table Toolbar** | 表格 | filter、sort、columns、density、save view、export |
| **Studio Toolbar** | 编辑 / 构建 | run、save、publish、debug、compare、preview |
| **Compare Toolbar** | 多选或 compare mode | 临时态，不应常驻 |
| **Bulk Action Bar** | 多选时出现 | 选中数量、可批量执行动作、清除选择 |

### 13. Scope Tabs 与 Filter Bar

这两类经常被混掉，必须分开。

#### 13.1 Scope Tabs

**作用**：大范围视图切换——"看哪一组对象 / 视角"

例如：

- ALL / FLOW / MACRO / NEWS
- ACTIVE / ARCHIVED / FAILED
- BOOK / ACCOUNT / STRATEGY

特点：

- 视觉较强
- 数量少
- 语义偏视图

#### 13.2 Filter Bar

**作用**：细条件约束——"在当前 scope 下进一步筛"

例如：

- status
- sector
- date range
- severity
- owner
- horizon

特点：

- 视觉较弱
- 数量可较多
- 语义偏条件

**不能把 filter chip 做得比 scope tabs 还强。**

### 14. Metric Block 与 Summary Strip

这两者也要分开。

#### 14.1 Metric Block

**用于少量重点数字展示**

例如：

- P&L
- Exposure
- Drawdown
- IC / IR
- Risk utilization

适用于 object hub 或 analytical 顶部少量摘要

#### 14.2 Summary Strip

**用于压扁的状态总线**

例如：

- Active 24
- Failed 1
- Queue 3
- Delayed 2

适合放在 analytical 页 header 下方，不应做成厚 KPI 卡

---

## Part C — Data Components

### 15. Data Components 定义

这组组件与 Data Views 强相关，这里从组件视角补充中层细节。

包括：

- Table
- Chart Container
- Timeline
- Status Cell
- Metric Cell
- Code Label
- Severity Badge
- Filter Chip
- Sparkline
- Distribution Strip
- Market Card（Radar Shell 专用）
- Cross-Market Matrix（Radar Shell 专用）
- Macro Driver Block（Radar Shell 专用）
- Context Pill（Radar Shell 专用）
- Scope Chip（Radar Shell 专用）

### 16. Table 作为一等组件

Table 在 Ditto 中是顶级数据组件，不是普通控件。

建议组件层面直接区分：

| Table 类型 | 适用场景 |
|---|---|
| **TableAnalytical** | Analytical workspace |
| **TableCatalog** | Catalog / Screener |
| **TableLedger** | Execution / Ledger |
| **TableOps** | Queue / Ops console |

而不是一个 Table 组件加无数布尔参数。

每一类应有自己稳定的：

- row height
- default columns style
- status treatment
- default actions
- footer style
- empty state style

### 17. Chart Container

Chart 必须有自己的容器规范。
不建议把图表当裸图塞进 panel。

| 容器类型 | 适用场景 |
|---|---|
| **MainChartContainer** | 主分析图 |
| **AnalysisChartContainer** | 辅助分析图 |
| **MonitorChartContainer** | 监控图 |
| **TimelineChartContainer** | 时间线图 |
| **MicroChartContainer** | sparkline / inline 小图 |

不同容器决定：

- header 风格
- legend 位置
- tooltip 结构
- container padding
- title 强度
- loading state

### 18. Timeline

Timeline 应作为独立组件族，而不是"某种图表的附属样式"。

| Timeline 类型 | 适用场景 |
|---|---|
| **Execution Timeline** | 交易执行 |
| **Job Timeline** | 任务队列 |
| **Incident Timeline** | 事件处理 |
| **Object History Timeline** | 对象变更历史 |
| **Agent Run Timeline** | Agent 执行链路 |

因为它们在 Ditto 里会非常高频出现，且对风控、平台、agent、执行都很重要。

### 19. Status Cell / Metric Cell

这两个组件应独立设计，而不是每次在表格里临时拼。

#### 19.1 Status Cell

用于表格、queue、log、panel 列表中的状态表达。

必须支持：

- 文字
- 轻语义色
- 可选 icon / marker
- 严重性分级

#### 19.2 Metric Cell

用于单元格中高价值数字。

必须支持：

- 主值
- 单位
- 可选变化方向
- 可选小辅助值
- 对齐纪律

### 20. Badge / Label 家族

这块是最容易被 UI kit 误伤的地方。

建议拆成 4 个独立组件，而不是一个 Badge 全做：

#### 20.1 Status Badge

用于状态。例如：Stable、Pending、Filled、Failed

#### 20.2 Severity Badge

用于严重度。例如：Low、Medium、High、Critical

#### 20.3 Code Label

用于编码、family、bucket、id、版本。例如：MOM_20D、ALPHA_LOW、RUN_1842、V3

#### 20.4 Filter Chip

用于当前筛选条件。例如：Universe: Core3000、Owner: Me、Severity: High

**四者绝不能外观完全一致。**

---

## Part C-1 — Cross-Market Components（Radar Shell 专用）

> **上游**：[全市场总览设计文档](../../plans/2026-03-29-cross-market-overview-design.md)

以下组件服务于 Analytical / Radar Shell 子变体，用于跨市场总览和单市场总览页面。

### C1.1 Context Pill

**角色**：Context Bar 内的单个客观变量展示单元。

**结构**：`LABEL VALUE`（如 `REGIME Mild Risk-On`）

**规则**：
- 标签大写、颜色中性（text-tertiary）
- 值用语义色表达方向（Risk-On 绿 / Risk-Off 红 / Mixed 黄）
- 单行水平排列，分隔符用 `|` 或微间距
- AlertBadge 放末尾，用数字 + 微动效

**不允许**：
- 放入 A 股本地特定项（如北向流入）
- 做成可编辑或可点击
- 超过 6 项

### C1.2 Scope Chip

**角色**：Scope Strip 内的单个解读摘要单元。

**结构**：`分类标签：内容`（如 `强势：港股科技/黄金`）

**规则**：
- 分类标签用固定色彩区分（强势 = 正向色 / 承压 = 负向色 / 风格 = 中性色 / 风险事件 = 警示色）
- 内容为纯文本摘要，不做数值
- 4-6 个 ScopeChip 横向排列

**不允许**：
- 做成长段落
- 放入精确数值
- 超过 6 项

### C1.3 Market Card

**角色**：跨市场平权比较的核心单元。每张卡片代表一个一级市场或资产类别。

**统一结构**（所有卡片必须遵循）：
1. **头部**：市场名 + Regime Tag（颜色编码）
2. **表现行**：核心指数 + 当日变化 + 相对强弱标签
3. **驱动行**：一句话驱动摘要
4. **CTA 行**：下钻入口按钮

**规则**：
- 6 宫格排列（3×2），所有卡片等宽等高
- hover 时 border 高亮 + 轻微提升
- 整卡可点击 + 底部 CTA 按钮显式
- Regime Tag 使用语义色：Risk-On / High Beta = 正向 / Risk-Off / Bonds Weak = 负向 / Mixed = 中性

**示例**：

```
┌─────────────────────┐
│ 中国A股    Risk-On   │
│ 沪深300   +0.67%    │
│ 广度偏强｜AI+半导体  │
│ → 进入 A 股总览      │
└─────────────────────┘
```

**不允许**：
- 不同卡片使用不同字段结构
- 放入过多子指数或明细数据
- 使用 treemap 替代卡片（跨市场页用卡片，单市场页用 treemap）

### C1.4 Cross-Market Matrix

**角色**：跨市场比较器——把"谁强谁弱"从感性判断变成可比较结构。

**结构**：
- 行：市场/资产类别（6-8 行）
- 列：1D / 1W / 1M / Vol / Breadth / Flow（6 列）

**规则**：
- 热力矩阵风格：数值用颜色梯度表达强弱
- 文字保留精确值（如 `+1.4%`）
- 行 hover 时联动对应 MarketCard 轻微高亮
- "-" 表示该市场不适用该维度（如黄金没有 Breadth）
- Vol / Breadth / Flow 列用文字标签而非数值

**不允许**：
- 做成传统全功能表格（列管理、排序、导出）
- 超过 8 行或 7 列
- 放入非核心维度

### C1.5 Macro Driver Block

**角色**：单个跨市场驱动变量的微型状态块。

**结构**：
1. 名称（如 `DXY`）
2. 当前值（如 `102.4`）
3. 变化量（如 `-0.4%`）
4. 一句解释性标签（如 `美元走弱`）

**规则**：
- 水平排列，7 个 Driver Block 均分宽度
- 变化量用颜色：正 = 红色（涨）/ 负 = 绿色（跌），遵循市场色规则
- 解释性标签用 text-tertiary，不超过一行
- 整体高度固定，不因内容长度变化

**不允许**：
- 放入迷你图表或 sparkline
- 超过 7 个驱动器
- 做成可展开面板

---

## Part D — Action Components

### 21. Action Components 定义

Ditto 的动作组件必须明确等级，不允许所有动作都长得像"主要按钮"。

包括：

- Primary Action Button
- Workspace Action
- Inline Action
- Bulk Action
- Danger Action
- Quick Action Tile

### 22. Button 角色分级

| 等级 | 角色 | 示例 | 约束 |
|---|---|---|---|
| **Primary Action** | 页面最高价值动作 | Run Backtest、Submit Order、Rebalance | 每页最多一个强 primary |
| **Workspace Action** | 当前工作区常规动作 | Saved View、Compare、New Factor | 语气更轻，不与 primary 抢位 |
| **Inline Action** | 局部动作（行、项） | Inspect、Retry、Review、Pin | 优先 hover 出现或弱化出现 |
| **Bulk Action** | 多选后出现 | Batch Approve、Export、Assign | 仅多选时可见 |
| **Danger Action** | 不可逆、高风险 | Cancel All、Disable Provider、Stop Agent | 必须有风险语义 |
| **Quick Action Tile** | 快速跳板 | Home / Command Center | 不可在 analytical 页泛滥 |

### 23. Action 组件使用规则

#### 23.1 每页只能有一个真正强主动作

如果有 3 个看起来都像主 CTA，这页就已经错了。

#### 23.2 行内动作必须克制

一行最多常驻 1–2 个高频动作，其余进入 more。

#### 23.3 Workspace 动作优先轻量化

多数情况下应使用：

- ghost
- subtle
- segmented
- icon + label

#### 23.4 Danger 动作必须有风险语义

不能拿品牌蓝或普通按钮样式去表达高风险动作。

---

## Part E — Overlay Components

### 24. Overlay Components 定义

Ditto 的 drill-down 很多时候应在局部完成，因此 overlay 组件非常关键。

包括：

- Drawer
- Side Sheet
- Modal
- Popover
- Tooltip
- Command Palette
- Context Menu

### 25. Drawer / Side Sheet

Drawer 与 Side Sheet 建议区分使用。

#### 25.1 Drawer

更像"从当前工作流中抽出一层细节"。

适用于：

- object detail
- compare
- parameter review
- quick inspect

#### 25.2 Side Sheet

更像"持续存在的上下文详情面板"。

适用于：

- inspector
- logs
- trace
- object meta
- AI tool output

**不要什么都用 Modal。**

### 26. Modal

Modal 仅用于需要明确中断和确认的场景，例如：

- destructive confirmation
- critical approval
- config reset
- publish confirmation

不要用 modal 取代所有详情与设置。

### 27. Popover / Tooltip / Context Menu

#### 27.1 Popover

适合：小范围设置、columns、filter config、density switch、quick preview

#### 27.2 Tooltip

适合：短说明、数值解释、chart hover

不适合承载复杂决策内容。

#### 27.3 Context Menu

适合：row actions、object actions、inspect / compare / pin / export 这类二级动作

### 28. Command Palette

Command Palette 在 Ditto 中应是一级组件，而不是额外增强功能。

它应支持：

- 搜页面
- 搜对象
- 搜 factor / strategy / symbol / order / run
- 直接执行部分动作
- 跳转近期对象
- 唤起 agent / copilot 动作（后续可扩）

Command Palette 的语气必须专业，不要做成炫技的 AI 搜索盒。

---

## Part F — Feedback Components

### 29. Feedback Components 定义

反馈不是全靠 toast。
Ditto 需要完整的反馈层级。

包括：

- Toast
- Inline Status
- Banner
- Alert Item
- Progress State
- Blocker State

### 30. 反馈层级

| 等级 | 组件 | 适用场景 | 特点 |
|---|---|---|---|
| **Toast** | 轻操作反馈 | copied、saved、exported | 短暂存在，不承载重要业务风险 |
| **Inline Status** | 对象局部状态 | running、syncing、recalculating | 可出现在 row、panel、chart、inspector |
| **Banner** | 页级 / workspace 级重要反馈 | data stale、broker disconnected、trading halted | 持续可见直到处理 |
| **Alert Item** | queue / activity / ops detail | 可处理事项 | 持续存在的可处理事项，不是 toast |
| **Progress State** | 长任务 | backtest running、model training、sync jobs | 持续可见直到完成 |
| **Blocker State** | 不可忽视的严重问题 | route disabled、config invalid、system down | 必须处理才能继续 |

---

## Part G — AI / Agent Components

### 31. 为什么要单独定义

AI / Agent 是 Ditto 的重要能力，但绝不能简单照搬聊天产品 UI。

因为 Ditto 的 AI 不只是"聊天"，而是：

- 研究助手
- 任务执行者
- 工具调用者
- 审批请求发起方
- 结果汇总器
- 实验 / 策略 / 市场分析协作者

所以 AI / Agent 必须有专属组件语法。

### 32. AI / Agent 组件家族

| 组件 | 角色 |
|---|---|
| **Conversation Block** | 分析会话块 / notebook block |
| **Research Note Block** | 研究结论、假设、TODO 沉淀 |
| **Suggestion Block** | AI 建议（可点选采纳） |
| **Tool Invocation Row** | 工具调用执行日志 |
| **Agent Task Block** | Agent 当前任务状态 |
| **Agent Run Timeline** | 多步 agent 执行链路 |
| **Approval Request Block** | 执行前审批请求 |
| **Output Artifact Block** | 结构化产出结果 |

### 33. Conversation Block

不是普通聊天泡泡。
它更像研究会话块 / notebook block。

**适用**：ai copilot、ai strategy assistant、ai market analysis

**特征**：

- 内容更像分析段落或提议
- 支持结构化引用输出
- 支持插入表、图、结论块
- 弱化社交聊天气泡感

### 34. Research Note Block

用于 AI 或用户沉淀的研究结论、假设、TODO。
更像专业研究笔记块，而不是评论消息。

**适用**：Copilot、Object Hub notes、factor / strategy / regime notes

**允许内容**：

- hypothesis
- findings
- next steps
- linked objects
- timestamps

### 35. Suggestion Block

用于 AI 给出的建议，不等同于命令也不等于对话正文。

例如：

- candidate factors to review
- possible risk drivers
- suggested rebalance actions
- additional datasets to inspect

特点：

- 语义清楚
- 可点选采纳 / 打开 / 比较
- 不该像广告推荐卡片

### 36. Tool Invocation Row

这在 agent 页面特别关键。

用于展示：

- 调用了什么工具
- 参数大概是什么
- 返回了什么结果
- 当前状态如何

它应更像专业执行日志，而不是"AI 思考过程可视化"。

### 37. Agent Task Block

用于展示 agent 当前在做什么任务。

建议包含：

- task title
- status
- objective
- used tools
- outputs
- blockers
- next action

这不是普通任务卡，而是 agent workflow node。

### 38. Agent Run Timeline

用于展示多步 agent 执行链路。

适用于：

- AI agent workspace
- approval flows
- tool orchestration
- long-running research workflows

它应该和 Ditto 的 execution / ops timeline 语法保持亲缘关系，而不是另外做一套 AI 专属 flashy timeline。

### 39. Approval Request Block

这是 AI 系统里非常重要的安全组件。

适用：

- 执行交易前审批
- 运行回测前审批
- 修改策略配置前审批
- 提交 agent actions 前审批

必须清晰显示：

- 谁请求
- 请求做什么
- 影响什么对象
- 风险级别
- 可以 approve / reject / modify

**绝不能把审批混在普通对话文本里。**

### 40. Output Artifact Block

用于展示 AI / Agent 产出的结构化结果。

例如：

- screen result set
- strategy draft
- report summary
- generated notebook
- linked factors / strategies / orders

它比普通消息块更像"对象产物块"。

---

## Part H — 组件与 Page Pattern 的适配关系

### 41. Global Command Center

**高优组件**：Quick Action Tile、Priority Queue Block、Global Alerts List、Summary Strip、Global Banner

**弱化组件**：heavy drawer、builder-style inspector、deep compare tools

### 42. Analytical Overview Workspace

**高优组件**：Main Panel、TableAnalytical / MainChartContainer、Activity Stack、Analysis Band、Compare Toolbar、Status Cell / Metric Cell

### 43. Catalog / Screener Workspace

**高优组件**：TableCatalog / TableAnalytical、Filter Bar、Save View Control、Inspector Panel、Bulk Action Bar

### 44. Object Hub

**高优组件**：Object Header、Main / Support Panels、Related / History Panel、Timeline、Notes Block、Artifact Block

### 45. Studio / Builder

**高优组件**：Studio Header、Command Bar、Inspector Panel、Config Panel、Tool Invocation Row、Agent Task Block、Approval Request Block、Preview Chart / Run Timeline

### 46. Queue / Ops Console

**高优组件**：TableOps、Severity Badge、Detail / Logs Panel、Incident Timeline、Retry / Resolve Action Block

### 47. Ledger / Execution Console

**高优组件**：TableLedger、Execution Timeline、Route / Fill Detail Panel、Slippage mini visual、Session Strip

### 48. Config / Integration Console

**高优组件**：Config Panel、Validation Strip、Connection Status Block、Diff Panel、Test Result Block

---

## Part I — 组件反模式清单

### 49. 常见反模式

| # | 反模式 | 后果 |
|---|---|---|
| 49.1 | 所有按钮都像主 CTA | 页面失焦，退化成 SaaS 工具页 |
| 49.2 | 所有标签都用同一 badge 样式 | 状态、严重度、编码、筛选条件混淆 |
| 49.3 | 所有 panel 都像 card | 页面碎片化、后台化 |
| 49.4 | 什么详情都用 modal | 打断工作流，破坏 terminal 连续性 |
| 49.5 | AI 页面照聊天软件做 | 与 Ditto 整体风格断裂 |
| 49.6 | drawer / side panel / inspector 没有分工 | drill-down 体验混乱 |
| 49.7 | 反馈只靠 toast | 持续状态和风险问题不可见 |
| 49.8 | Studio 页面被按钮、卡片和 summary 占据 | 主工作面不成立 |

---

## Part J — 与下一份 Token 文档的关系

### 50. 本文档为 token 命名提供的结构

后续《Ditto Token Naming & Layering 规范》应直接映射本组件规范。

```
Button
  action.primary.*
  action.workspace.*
  action.inline.*
  action.bulk.*
  action.danger.*

Panel
  panel.main.*
  panel.support.*
  panel.continuous.*
  panel.inspector.*
  panel.config.*
  panel.log.*

Badge / Label
  badge.status.*
  badge.severity.*
  label.code.*
  chip.filter.*

Overlay
  drawer.*
  sidesheet.*
  modal.*
  popover.*
  tooltip.*
  command-palette.*

AI / Agent
  agent.task.*
  agent.timeline.*
  agent.approval.*
  copilot.note.*
  copilot.suggestion.*
  copilot.toolrow.*
```

### 51. 与旧组件思维的切换要求

这份组件规范最核心的一件事，是帮助你从"通用后台组件库思维"切到"专业工作台组件角色思维"。

以后看组件，**不要先问**：

- 它是不是 Button
- 它是不是 Card
- 它是不是 Modal
- 它是不是 Badge

**而是先问**：

- 它在当前页面里承担什么角色
- 它是一级动作还是二级动作
- 它是状态还是编码
- 它是连续面板还是独立容器
- 它是 drill-down 还是阻断确认
- 它是 AI 对话块还是审批块

只要这个思维切换成功，Ditto 的整体气质会非常稳。

### 52. 验收标准

一个合格的 Ditto Component Spec，必须满足：

1. 组件先按角色分，再按类型分
2. 动作组件层级清晰
3. badge / label / chip 语义清晰
4. panel 不再退化成统一 card
5. overlay 分工明确
6. feedback 分级完整
7. AI / Agent 组件不与主产品风格断裂
8. 能直接为 token 规范提供结构基础

## Changelog

### 2026-03-30 — Cross-Market Review R10 Sync

- **[新增]** Sparkline opacity 标准: 0.6, stroke-width 1.5px（来源: FIX-07）
- **[新增]** LIVE 状态指示器规范: 同源绿色 oklch(0.72 0.19 155)（来源: COPY-09）
- **[新增]** kbd 幽灵键帽组件规范: font-mono 10px, border oklch(1 0 0 / 0.10)（来源: FIX-10/COPY-10）
