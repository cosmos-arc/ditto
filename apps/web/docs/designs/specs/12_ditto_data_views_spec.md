# Ditto Data Views 规范

> **版本**：v1.0
> **日期**：2026-03-28
> **状态**：Final
> **上游**：[00 视觉宪章](./00_ditto_visual_constitution.md)、[03 对象页统一规范](./03_object_hub_spec.md)
> **下游**：[13 Component Spec](./13_ditto_component_spec.md)
> **职责**：统一定义 Table、Context Panel、Chart / Timeline 三类核心数据工作面
>
> 适用范围：Ditto 全站的数据工作面

---

## 1. 文档目标

在 Ditto 里，真正决定"这是不是专业量化平台"的，不是按钮、表单、弹窗，而是三类核心数据工作面：

- **Table**
- **Activity / Context Panel**
- **Chart / Timeline**

它们共同构成了 Ditto 的主要生产力界面。
用户真正长时间盯着看的、频繁操作的、依赖做判断的，基本都落在这三类工作面里。

因此，Ditto 不应把它们视为普通组件，也不应把它们拆成彼此无关的散规范。
更合理的方式，是把它们统一视为 **Data Views**，也就是"承载数据判断、工作流上下文和对象可视化"的系统级工作面。

这份文档的目标，是从平台视角统一回答：

- 不同页面里，什么该用表，什么该用图，什么该用右侧上下文面板
- 这三类工作面在不同 Page Pattern 下应该如何变体
- 它们之间如何联动
- 它们的视觉和交互语法如何统一
- 如何避免退化回普通后台 UI

---

## 2. Data Views 总体原则

### 原则 1：Data View 是工作面，不是展示模块

Table、Activity、Chart 都不是"放点内容"的容器，而是承载判断与操作的工作面。
设计它们时，第一问题不是"怎么排版"，而是"**用户在这里完成什么任务**"。

### 原则 2：一页中的 Data View 必须存在明确主次

同一页面可能同时存在主表、右侧活动面板、底部分析图，但它们不能是平权关系。
必须始终明确：

- 谁是**主工作面**
- 谁在**辅助解释**
- 谁在**承接上下文**
- 谁只负责**状态与动作**

### 原则 3：不同 Page Pattern 下，Data View 的角色不同

同样是表格：

- 在 Research 是**主分析表**
- 在 Orders 是**账本流水表**
- 在 Alerts 是**运维队列表**

同样是右侧面板：

- 在 Research 是 **Activity Stack**
- 在 Studio 是 **Inspector / Suggestions**
- 在 Ops 是 **Detail / Logs / Actions**

同样是图表：

- 在 Markets 是**主观察图**
- 在 Bottom Analysis Band 是**解释图**
- 在 Execution 是**时间线 / 状态链图**

所以不能只写"表格规范""图表规范"，必须放在页面角色中理解。

### 原则 4：Data Views 必须支持联动，而不是各自独立存在

Ditto 的专业感，很大程度来自联动：

- 选中主表行，右侧跟着变
- 切换对象，底部分析图跟着变
- 改变时间范围，主图和子图一起变
- 点击 timeline 事件，相关详情自动展开

这比单独把某一块做得"好看"重要得多。

### 原则 5：Data Views 的高级感来自纪律，而不是特效

专业感来自：

- 统一的对齐
- 统一的数值格式
- 清晰的层级
- 克制的状态表达
- 稳定的密度
- 可靠的交互反馈

而不是来自：

- 发光
- 渐变
- 过重边框
- 大量彩色标签
- 悬浮奇效

### 原则 6：表格动作归属 Data Toolbar

Table View 的本地动作必须在 Data Toolbar 或 Workspace Toolbar 中表达，不进入全局 Header Utility。

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

---

## 3. Data Views 分类体系

Ditto 的 Data Views 统一分成三大族：

| 族 | 名称 | 职责 |
|----|------|------|
| **A** | **Table Views** | 对象集合、流水、筛选、批处理、比较和扫描 |
| **B** | **Context Views** | recent、live、queue、notes、detail、logs、inspector、actions 等上下文承接区 |
| **C** | **Visual Views** | chart、timeline、distribution、heat、network、micro-trend 等可视化判断区 |

这三类不是孤立的，它们往往组合出现：

| 组合模式 | 典型布局 |
|----------|---------|
| **Analytical Workspace** | 主 Table / 主 Chart + Context View + Analysis Chart |
| **Catalog Workspace** | 主 Table + Preview / Inspector Context View |
| **Object Hub** | Object Panels + Related / History Context View + Timeline / Diagnostics Visual View |
| **Studio** | Main Editor + Inspector / Suggestions Context View + Preview Chart / Run Timeline |
| **Ops Console** | Queue Table + Detail / Logs Context View + Monitor Timeline / Status Chart |

---

## 4. Pattern 到 Data Views 的映射

把三类工作面放回页面模式里，避免后面写散。

### 4.1 Global Command Center

- **主工作面**：Queue-like Table / Summary Boards
- **辅助**：Global Alerts Context View、少量 Summary Visual View
- **不推荐**：大量复杂主图或深度对象表

### 4.2 Analytical Overview Workspace

- **主工作面**：Analytical Table 或 Main Chart
- **辅助**：Activity Stack Context View、Analysis Chart / Monitor Chart
- **备注**：这是 Data Views 最丰富的一类页面

### 4.3 Catalog / Screener Workspace

- **主工作面**：Catalog Table / Screener Table / Ledger Table
- **辅助**：Preview / Inspector Context View、可选 Micro Visual View
- **备注**：通常不以 Analysis Band 为默认

### 4.4 Object Hub

- **主工作面**：Object-centric Table / Chart / Metrics Panels
- **辅助**：Related / Notes / History Context View、Timeline / Diagnostics Visual View

### 4.5 Studio / Builder

- **主工作面**：Editor / Canvas / Chat（不属于 Data View 主角）
- **辅助**：Inspector / Suggestions / Tool Output Context View、Preview Chart / Run Timeline / Validation Table
- **备注**：Studio 中的 Data View 多为辅助，而非唯一主角

### 4.6 Queue / Ops Console

- **主工作面**：Ops Table / Queue Table
- **辅助**：Detail / Logs / Actions Context View、Status Timeline / Monitor Chart

### 4.7 Ledger / Execution Console

- **主工作面**：Ledger Table / Execution Timeline
- **辅助**：Detail / Trace Context View、Slippage / Fill Breakdown Visual View

### 4.8 Config / Integration Console

- **主工作面**：Config forms（不属于 Data View 主角）
- **辅助**：Connection status table、Validation logs context、Test timeline / Health chart

---

## Part A — Table Views

### 5. Table Views 总则

在 Ditto 中，表格不是后台控件，而是**专业工作表**。
它服务的不是"把字段列出来"，而是：

- 扫
- 比
- 筛
- 排
- 定位
- 选中
- drill-down
- 批量处理

表格设计的核心目标不是字段完整，而是**扫描效率**与**工作流效率**。

### 6. Table Views 的四个子类型

#### 6.1 Analytical Table

**适用**：Research overview、Factor monitor、Screener、Positions、Signals、Risk exposure tables

**特点**：

- 比较和判断优先
- 数值列重要
- selected row 很重要
- 与图和右侧上下文联动很重要

#### 6.2 Catalog Table

**适用**：Factors library、Strategy library、Universes、Portfolios、Models、Research outputs

**特点**：

- 对象名称、分类、状态、更新时间重要
- 筛选和保存视图重要
- preview / inspector 很重要

#### 6.3 Ledger Table

**适用**：Orders、Trades、Fills、Broker events、Account movements

**特点**：

- 时间、状态链、数量、价格、金额都重要
- detail trace 很重要
- 更强调流水感和状态感

#### 6.4 Ops / Queue Table

**适用**：Alerts、Data quality、Pipelines、Incidents、Review queues、Approvals

**特点**：

- severity、owner、updated at、next action 很重要
- 批处理和处置效率很重要
- 右侧 detail / logs 很重要

### 7. Table Views 的共同规则

#### 7.1 列必须有层级

统一分为：

| 层级 | 说明 |
|------|------|
| **判断列** | 用户做决策依赖的核心字段 |
| **上下文列** | 帮助理解判断列的补充信息 |
| **元信息列** | 时间、来源、标签等辅助信息 |

#### 7.2 selected row 必须成立

尤其在 Analytical、Catalog、Ledger、Ops 四类表中，selected row 都应是一级交互状态，而不是只有 hover。

#### 7.3 数值纪律必须严格

包括：

- 对齐
- 精度
- 单位
- 正负号
- 时间格式
- 状态词

#### 7.4 行操作必须克制

优先级：

1. 行点击选中
2. hover 暴露轻动作
3. more menu 收纳次级动作

#### 7.5 表格工具栏必须服务工作流

重点放：

- scope
- filter
- sort
- columns
- density
- save view
- compare
- bulk actions

不应堆很多平权按钮。

### 8. 不同 Table 类型的关键差异

| 子类型 | 关键列优先级 |
|--------|-------------|
| **Analytical Table** | 主对象 + 核心指标 + 状态 |
| **Catalog Table** | 主对象 + 分类 + 当前状态 + 最近更新时间 |
| **Ledger Table** | 时间 + 对象 + side / qty / price / status |
| **Ops Table** | severity + status + object + owner + updated at + next action |

> 这部分一定不能混用。比如 Orders 表就不应照 Research 表的字段语法去做。

---

## Part B — Context Views

### 9. Context Views 总则

Context View 指的是承接上下文、历史、运行态、队列、日志、详情、建议、审批的那类面板。
它们通常位于右侧，也可能位于下方或抽屉中。

它们的价值不是"显示更多信息"，而是：

- 降低认知切换
- 补充当前对象上下文
- 提供下一步动作
- 承载持续状态
- 解释当前工作面之外的因果

### 10. Context Views 的四个子类型

#### 10.1 Activity Stack

**适用**：Research、Markets、Portfolio、Risk、部分 Object Hub

**内容通常包括**：recent、live、queue、notes

这是 Ditto 中连续辅助栏的核心形态。

#### 10.2 Preview / Inspector Panel

**适用**：Catalog pages、Object selection preview、Chart object summary、Quick object details

**内容通常包括**：

- 关键字段
- 小摘要图
- 当前状态
- 可进入详情的动作

#### 10.3 Detail / Logs / Actions Panel

**适用**：Ops Console、Ledger / Execution、Pipelines、Data quality、Incident handling

**内容通常包括**：

- logs
- raw detail
- retry / resolve / assign
- timeline
- dependency info

#### 10.4 Studio Context Panel

**适用**：Strategy Builder、Copilot、Agent Workspace、Chart Lab

**内容通常包括**：

- inspector
- suggestions
- run state
- preview
- approval
- tool output

> 这类面板绝不能简单照搬 Activity Stack。

### 11. Context Views 的共同规则

#### 11.1 必须围绕主对象或主任务联动

右侧面板不能长期展示无关静态内容。

#### 11.2 不应卡片拼贴化

Context View 更适合**连续 panel、section、list**，而不是大量独立小卡片。

#### 11.3 状态比装饰更重要

尤其 recent、live、queue、detail、approval 这些内容，应该优先强调：

- 对象
- 状态
- 时间
- 动作

而不是小组件美观。

#### 11.4 右侧宽度应受控

否则它会抢主工作面。

#### 11.5 必须支持局部 drill-down

例如：

- 展开某条日志
- 查看事件 trace
- 展示 note detail
- 展示 agent tool result

但尽量局部完成，不要一点击就整页跳走。

### 12. Context Views 在不同 Pattern 下的默认选择

| Page Pattern | 默认 Context View |
|-------------|-------------------|
| **Analytical Overview Workspace** | Activity Stack |
| **Catalog / Screener Workspace** | Preview / Inspector Panel |
| **Object Hub** | Related / History / Notes Panel（Activity Stack 与 Inspector 的混合） |
| **Studio / Builder** | Studio Context Panel |
| **Queue / Ops Console** | Detail / Logs / Actions Panel |
| **Ledger / Execution Console** | Detail / Trace Panel |
| **Config / Integration Console** | Validation / Logs / Test Panel |

---

## Part C — Visual Views

### 13. Visual Views 总则

Visual View 是 Ditto 里承载趋势、分布、阈值、关系、状态变化的可视化工作面。
它们不只是"图表"，还包括时间线、网络、热图、微趋势等。

它们的任务是：

- 比表更快地看变化
- 比数字更直觉地看结构
- 比日志更清楚地看状态链

### 14. Visual Views 的五个子类型

#### 14.1 Main Analytical Chart

**适用**：Markets main chart、Backtest compare、Regime chart、Risk dashboard main chart、Portfolio performance

这是 Analytical Overview 中可能作为主仪表的图。

#### 14.2 Analysis Chart

**适用**：Factor Breadth、IC Trend、Correlation Scatter、Exposure Decomposition、Decay curve、Attribution charts

通常位于 Analysis Band 中，用于解释主仪表。

#### 14.3 Monitor Chart

**适用**：Data freshness、Queue throughput、Drift monitor、Risk threshold timeline、Broker health

通常位于 Ops / Risk / Platform 中。

#### 14.4 Ledger / Execution Timeline

**适用**：Order lifecycle、Fill sequence、Retry chain、Incident escalation、Pipeline execution timeline

这是 chart-spec 里最需要补充的一类。

#### 14.5 Micro Visual

**适用**：Sparkline、Inline trend、Mini histogram、Tiny distribution cue

用于表格、summary strip、preview panel 中的轻量可视化。

> **Sparkline 规范** (R10): opacity 0.6, stroke-width 1.5px, stroke-linecap/linejoin round。用于 Market Card 趋势线、table cell inline trend。

### 15. Visual Views 的共同规则

#### 15.1 先定义分析角色，再定义图种

不能从"做个折线图"开始，而要从"**这张图要回答什么问题**"开始。

#### 15.2 主次序列必须明确

尤其在多序列图里，要有：

- 主对象
- 对比对象
- 背景对象

#### 15.3 必须有参照系

包括：

- 单位
- 基线
- 阈值
- 时间范围
- 当前对象说明

#### 15.4 tooltip 必须有分析价值

不能只是显示一个值。

#### 15.5 不是所有图都需要图例、网格和厚容器

图表也要按角色克制。

---

## 16. 什么时候该用表，什么时候该用图，什么时候该用 Context View

这是很关键的判断规则。

### 优先用 Table 的场景

- 需要扫描多个对象
- 需要比较多个字段
- 需要排序、筛选、批处理
- 需要明确 selected row
- 需要高密信息

### 优先用 Chart / Timeline 的场景

- 需要看趋势
- 需要看分布
- 需要看阈值与异常
- 需要看结构变化
- 需要看状态演进

### 优先用 Context View 的场景

- 需要补充对象上下文
- 需要显示 recent / live / queue / notes / logs
- 需要承接 actions
- 需要局部展示详情而不跳页

### 混合使用的经典模式

- 主表 + 右侧 context + 底部分析图
- 主图 + 右侧 queue + 下方明细表
- 主表 + 右侧 detail + timeline
- editor + 右侧 inspector + preview chart

---

## 17. Data Views 的联动规范

这是 Ditto 专业感的关键。

### 17.1 Table → Context

选中表格行后，右侧 Context View 必须围绕该对象刷新。

### 17.2 Table → Visual

选中表格行后，底部或主图应显示该对象的分析图或时间线。

### 17.3 Visual → Context

点击图上事件点、异常点、阶段点时，右侧应展示相关 detail / logs / notes。

### 17.4 Context → Table / Visual

点击 right panel 中 recent / queue / related item 时，主表或主图应同步切换对象或高亮对应位置。

### 17.5 Range / Scope 联动

当用户更改以下范围时：

- universe
- timeframe
- strategy scope
- account scope
- book scope

主表、右侧上下文、主图 / 子图应尽量共享同一范围语义。

---

## 18. Data Views 的统一状态体系

不论是 Table、Context 还是 Visual，都必须共享以下状态语言：

| 状态 | 说明 |
|------|------|
| **Default** | 正常可扫描状态 |
| **Hover** | 表示可进一步操作 |
| **Selected** | 表示当前对象上下文已切换到这里 |
| **Running / Updating** | 表示对象或任务正在进行 |
| **Stale / Delayed** | 表示数据新鲜度问题 |
| **Warning / Risk / Critical** | 表示业务严重性问题 |
| **Empty** | 表示当前无内容或无匹配结果 |
| **Partial / Failed** | 表示数据、任务或系统执行不完整 |

> 这些状态必须跨 Data Views 统一，不能表格和图表各说各话。

---

## 19. Data Views 的密度策略

| Data View 类型 | 密度 |
|---------------|------|
| **Table Views** | 默认最高密，尤其 Analytical / Ledger / Ops 表 |
| **Context Views** | 中高密，但比表略松 |
| **Main Visual Views** | 中密 |
| **Analysis Visual Views** | 中低到中密 |
| **Micro Visual** | 极简低占位 |

**原则**：

- 表格优先生产力
- 图表优先可读性
- 右侧上下文优先连贯性

---

## 20. Data Views 的 Token 映射建议

这一份暂不写成最终 token 表，但先给结构。

```
Table
  table.analytical.*
  table.catalog.*
  table.ledger.*
  table.ops.*

Context
  context.activity.*
  context.preview.*
  context.detail.*
  context.studio.*

Visual
  visual.main.*
  visual.analysis.*
  visual.monitor.*
  visual.timeline.*
  visual.micro.*

Shared state
  dataview.selected.*
  dataview.running.*
  dataview.stale.*
  dataview.warning.*
  dataview.critical.*
  dataview.empty.*
```

---

## 21. 验收标准

一份合格的 Data Views 规范，必须满足：

- [ ] 全站主要数据工作面都能被归类到 Table / Context / Visual 三族
- [ ] 不同页面模式下，三族工作面的角色变化清楚
- [ ] 表、图、右侧上下文不再各自为政
- [ ] 页面级联动规则明确
- [ ] 研究、交易、风控、AI、平台运维都能被覆盖
- [ ] 历史专题 spec 可以被吸收，而不是继续散乱发展

## Changelog

### 2026-03-30 — Cross-Market Review R10-R12 Sync

- **[新增]** Heat map 5 级 alpha 梯度: 0.05/0.10/0.17（oklch 红/绿双色系），用于 Matrix 热区背景（来源: FIX-04）
- **[新增]** Sparkline opacity 0.6, stroke-width 1.5px（来源: FIX-07）

### 2026-04-29 — Non-Color Visual Encoding Contract

数据可视化不得只靠颜色表达方向、强弱或风险。热力图、相关矩阵、风险矩阵、因子表和回测图至少需要两类编码同时存在：

- 方向：正负号、箭头、`data-viz-sign` 或文字标签。
- 强弱：数值、边界、权重、`data-viz-cell-strength`。
- 阈值：固定图例、阈值线、`data-viz-threshold-label`。
- 选中：边界、焦点环、`data-viz-cell-selected`。

原型合同：

| 元素 | 属性 / class | 目的 |
|------|--------------|------|
| 图例 | `data-viz-legend` / `.viz-legend` | 解释颜色、方向和阈值 |
| 方向标记 | `data-viz-sign` / `.viz-sign-marker` | 避免红绿色依赖 |
| 阈值标签 | `data-viz-threshold-label` / `.viz-threshold-label` | 暴露风险或相关性分界 |
| 强重点单元 | `data-viz-cell-strength` / `.viz-cell-strong` | 用边界 / 字重补充热度 |
| 选中单元 | `data-viz-cell-selected` / `.viz-cell-selected` | 显示当前分析对象 |

适用代表页：A Shares、Cross Market、Risk Center、Regime Monitor、Factor Analysis、Backtest Result。
