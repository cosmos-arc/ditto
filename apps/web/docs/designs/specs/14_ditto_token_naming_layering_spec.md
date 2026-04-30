# Ditto Token Naming & Layering 规范

> **版本**：v1.0
> **日期**：2026-03-28
> **状态**：Final
> **上游**：[13 Component Spec](./13_ditto_component_spec.md)、[10 Shell Family 规范](./10_ditto_shell_family_spec.md)
> **职责**：定义 design token 的分层、命名与工程落地方式
>
> 适用范围：Ditto 全站 design token、theme、组件变量、页面模式变量
> 目标：把前面规范真正落到可执行的 token 体系，避免变量失控、语义混乱、组件各自为政

---

## 1. 文档目标

到这一步，Ditto 已经有了四层上位规范：

- Shell Family 规范
- Page Pattern Library
- Data Views 规范
- Component Spec

但如果没有统一的 token 分层与命名规则，最后还是会发生这些问题：

- 颜色名和业务语义混在一起
- panel、table、chart、badge 各自发明变量
- 不同模块偷偷长出"局部主题"
- density 模式改一处坏三处
- 同一个"warning"在市场、风控、数据质量里含义不同
- 前端为了赶进度直接写死颜色、间距、圆角、行高
- AI coding 生成代码时乱造变量名，设计系统越来越不可控

这份规范的任务，就是把 Ditto 的视觉体系变成一套有层级、可扩展、可维护、可工程化的 token 系统。

它要解决四件事：

1. 哪些 token 属于基础物理层，哪些属于业务语义层。
2. 变量如何命名，才能让设计、前端、AI coding 都容易理解。
3. 页面壳层、工作面、组件、状态、密度如何分层映射。
4. 如何避免普通 SaaS token 体系无法覆盖 Ditto 这种专业终端产品。

---

## 2. 核心原则

### 原则 1：先分层，再命名

不要先想变量叫什么颜色、什么尺寸。
先要明确它属于哪一层：

- Foundation
- Semantic Surface
- Atmosphere (Living Graphite)
- Shell
- Data View
- Component
- Interaction
- Domain Semantic
- Density
- Module Pattern

Ditto 的 token 体系如果没有层级，只会快速变成一锅粥。

### 原则 2：颜色和语义必须分离

例如：

- `blue-500` 是基础物理值
- `action.primary.fg` 是组件语义
- `market.up.fg` 是业务语义
- `risk.high.bg` 是另一个业务语义

不能直接在组件里写"蓝色"，也不能把"红色"同时当作市场跌、风险高、订单拒绝、系统故障的统一色。

### 原则 3：Token 要先服务系统语法，不先服务页面局部

Ditto 不是一页页独立设计的产品。
Token 必须优先保证：

- 跨页面一致
- 跨模式一致
- 跨模块一致
- 跨组件一致

局部页面如果想做特殊风格，应优先通过 Pattern 或 Module 层做极小差异，而不是直接新建一堆局部 token。

### 原则 4：命名要表达角色，而不是表达审美印象

正确方向：

- `panel.main.bg`
- `table.ledger.row.selected`
- `agent.approval.border`
- `shell.analytical.sidebar.width`

不推荐：

- `cool-blue`
- `dark-panel-2`
- `widgetGray`
- `niceHover`
- `chartCardBg`

Ditto 的 token 是工程系统，不是情绪描述库。

### 原则 5：默认主题必须足够成立，模块差异只能轻微存在

Markets、Research、Trading、AI、Platform 可以有轻微节奏差异，但不能各自像不同产品。
所以 module token 层必须存在，但它只能做轻微偏置，不能重写基础体系。

### 原则 6：Density 是一级系统能力，不是临时附加参数

Ditto 是高密专业工作台。
compact、comfortable、ultra-compact 不能靠散落的行高和 padding hack 实现，而必须是正式 token 层。

---

## 3. Token 总体分层

Ditto 建议固定为 9 层 token 结构。

| # | Layer | 稳定性 | 说明 |
|---|-------|--------|------|
| 1 | Foundation | 最高 | 物理原语：颜色、字号、间距、圆角等 |
| 2 | Semantic Surface | 很高 | 界面表面语义：背景、文本层级、边框、Domain 签名色 |
| 2b | Atmosphere | 高 | 亚感知级背景氛围（运行时动态） |
| 3 | Shell | 高 | 页面壳层布局与节奏 |
| 4 | Data View | 中高 | Table / Context / Visual 三族 token |
| 5 | Component | 中 | 具体组件角色 token |
| 6 | Interaction & Feedback | 中 | 交互状态：focus、hover、selected、drag |
| 7 | Domain Semantic | 中 | 业务域状态色：market、risk、execution 等 |
| 8 | Density | 高 | 紧凑/舒适/超紧凑三档 |
| 9 | Module Pattern | 较低 | 模块级轻微偏置 |

这 9 层从底到顶，越往下越稳定，越往上越接近具体页面与业务。

---

## Part A — Foundation Layer

### 4. Foundation Layer 的职责

Foundation 是最底层的"物理值"，不直接表达业务语义。
它应该尽量少而稳定，不随着页面需求频繁变化。

建议包含：

- primitive color
- typography scale
- spacing scale
- radius scale
- stroke / border width
- shadow scale
- motion scale
- z-index scale

Foundation 的命名要极简，不能带页面或业务含义。

### 5. Primitive Color

建议不要直接用 UI 库那种一大坨彩虹色板。
Ditto 更适合小而精的 primitive palette。

#### 5.1 中性色 primitives

建议结构：

```
neutral.0
neutral.25
neutral.50
neutral.100
neutral.200
neutral.300
neutral.400
neutral.500
neutral.600
neutral.700
neutral.800
neutral.900
neutral.950
```

用途：只用于更高层语义 token 的映射，不直接给组件使用。

#### 5.2 品牌色 primitives

建议控制在非常小的集合：

```
brand.300
brand.400
brand.500
brand.600
brand.700
```

#### 5.3 功能色 primitives

只做基础物理集合：

```
green.400 / 500 / 600
red.400 / 500 / 600
amber.400 / 500 / 600
orange.400 / 500 / 600
cyan.400 / 500 / 600
purple.400 / 500 / 600
```

注意：这些依然不是业务语义，只是 primitive。
真正业务语义要到 Domain Semantic Layer 才成立。

### 6. Typography Scale

建议基础字号不要太多。
Ditto 更适合稳定的专业级字体节奏，而不是营销页式大幅跳跃。

推荐 primitives：

```
font.size.10
font.size.11
font.size.12
font.size.13
font.size.14
font.size.16
font.size.18
font.size.20
font.size.24
font.size.28
```

字重：

```
font.weight.regular
font.weight.medium
font.weight.semibold
```

字体家族：

```
font.family.ui
font.family.numeric
font.family.code
```

因为 Ditto 中数值、代码、ID、run name 的节奏很重要。

### 7. Spacing / Radius / Motion 基础值

#### 7.1 Spacing primitives

保持稳定的 4pt 体系，但不鼓励直接任意使用：

```
space.2
space.4
space.6
space.8
space.10
space.12
space.16
space.20
space.24
space.32
```

#### 7.2 Radius primitives

专业终端应更克制：

```
radius.2
radius.4
radius.6
radius.8
radius.12
```

多数 Ditto 组件应停留在 4–8 的区间。

#### 7.3 Motion primitives

只保留：

```
motion.duration.fast
motion.duration.normal
motion.duration.slow
motion.easing.standard
motion.easing.emphasis
```

并通过更高层映射到具体组件，而不是 everywhere 自由使用。

---

## Part B — Semantic Surface Layer

### 8. Semantic Surface Layer 的职责

这一层把 primitive 映射成页面表面语义。
它不表达业务，不表达组件，而表达"界面上这是什么层级的表面"。

这是 Ditto 高级感的核心层之一。

建议包含：

- app background
- workspace background
- rail background
- panel surfaces
- overlay surfaces
- muted surfaces
- divider
- text hierarchy

### 9. Surface 命名建议

#### 表面

```
surface.app
surface.workspace
surface.rail
surface.panel.base
surface.panel.elevated
surface.panel.muted
surface.overlay
surface.overlay.elevated
surface.band
surface.input
surface.input.focused
```

#### 文本

```
text.primary
text.secondary
text.tertiary
text.quaternary
text.data-stale
text.disabled
text.muted
text.inverse
```

#### 边界

```
border.subtle
border.default
border.strong
```

#### 文本可读性使用分级

文本 token 必须按信息风险分级使用，不能只按"视觉弱一点"选择层级。
`text.tertiary` 与 `text.quaternary` 只能用于装饰性文本或低风险 metadata；状态、时间戳、表格 metadata、队列时间等 operational 信息必须使用 `text.secondary` 或对应语义 token。`text.disabled` 仅表示不可用 affordance，不得承载 operational 信息。

| Tier | Examples | Contrast Gate |
|---|---|---|
| decorative | disabled affordance, watermark | report only |
| metadata | optional timestamp, decorative caption | warn below 4.5, fail below 3 |
| operational | stale status, table metadata, queue time | fail below 4.5 |
| data-critical | risk, trade, error, approval | fail below 4.5 and require non-color marker |

这个层级是全站"灰阶秩序"的根基。

---

## Part C — Shell Layer

### 10. Shell Layer 的职责

这一层定义七类壳层的布局与节奏 token。
它不直接定义页面内容，只定义"页面壳怎么长"。

建议命名空间：

```
shell.command-center.*
shell.analytical.*
shell.catalog.*
shell.object-hub.*
shell.studio.*
shell.ops.*
```

### 11. Shell Layer 建议字段

每类 shell 至少可以有这些 token：

#### 布局尺寸

```
shell.analytical.rail.width
shell.analytical.header.height
shell.analytical.strip.height
shell.analytical.sidebar.width
shell.analytical.bottom.height
```

#### 间距

```
shell.analytical.header.padding.x
shell.analytical.header.padding.y
shell.analytical.gutter
shell.analytical.section.gap
```

#### 表面

```
shell.analytical.bg
shell.analytical.header.bg
shell.analytical.strip.bg
shell.analytical.sidebar.bg
shell.analytical.bottom.bg
```

#### 文本

```
shell.analytical.title
shell.analytical.meta
shell.analytical.strip.label
shell.analytical.strip.value
```

#### 分隔

```
shell.analytical.divider
```

其他五类 shell 同理。

---

## Part D — Data View Layer

### 12. Data View Layer 的职责

这一层承接《Ditto Data Views 规范》，直接为 Table / Context / Visual 三族建立 token 命名空间。

建议命名空间：

**Table**

```
table.analytical.*
table.catalog.*
table.ledger.*
table.ops.*
```

**Context**

```
context.activity.*
context.preview.*
context.detail.*
context.studio.*
```

**Visual**

```
visual.main.*
visual.analysis.*
visual.monitor.*
visual.timeline.*
visual.micro.*
```

### 13. Table token 建议

#### 13.1 Analytical Table

```
table.analytical.row.height
table.analytical.row.hover
table.analytical.row.selected
table.analytical.cell.padding.x
table.analytical.header.height
table.analytical.header.text
table.analytical.numeric.text
table.analytical.meta.text
table.analytical.border
table.analytical.toolbar.height
```

#### 13.2 Catalog Table

类似 analytical，但更强调：

```
table.catalog.preview.link
table.catalog.tag.text
table.catalog.result.count
```

#### 13.3 Ledger Table

重点：

```
table.ledger.status.*
table.ledger.time.text
table.ledger.execution.trace
table.ledger.amount.text
```

#### 13.4 Ops Table

重点：

```
table.ops.severity.*
table.ops.owner.*
table.ops.action.*
table.ops.stale.*
```

### 14. Context token 建议

#### Activity

```
context.activity.bg
context.activity.section.gap
context.activity.item.height.recent
context.activity.item.height.live
context.activity.item.height.alert
context.activity.item.hover
context.activity.item.selected
context.activity.title
context.activity.meta
context.activity.status
```

#### Preview

```
context.preview.bg
context.preview.header
context.preview.section
context.preview.metric
context.preview.meta
```

#### Detail

```
context.detail.bg
context.detail.log.row
context.detail.action.bar
context.detail.trace.line
```

#### Studio

```
context.studio.bg
context.studio.inspector
context.studio.suggestion
context.studio.toolrow
context.studio.approval
```

### 15. Visual token 建议

#### Main Visual

```
visual.main.container.bg
visual.main.header.height
visual.main.gridline
visual.main.axis.label
visual.main.tooltip.bg
visual.main.crosshair
```

#### Analysis Visual

```
visual.analysis.container.bg
visual.analysis.series.primary
visual.analysis.reference.line
visual.analysis.threshold.line
```

#### Monitor Visual

```
visual.monitor.alert.point
visual.monitor.threshold.band
visual.monitor.stale.label
```

#### Timeline Visual

```
visual.timeline.node
visual.timeline.node.active
visual.timeline.node.failed
visual.timeline.line
visual.timeline.label
visual.timeline.meta
```

#### Micro Visual

```
visual.micro.sparkline
visual.micro.positive
visual.micro.negative
```

---

## Part E — Component Layer

### 16. Component Layer 的职责

这一层把《Ditto Component Spec》里的组件角色落成具体 token 命名空间。

建议命名空间：

```
action.*
panel.*
badge.*
label.*
chip.*
toolbar.*
metric.*
overlay.*
feedback.*
agent.*
copilot.*
```

### 17. Action token 建议

#### 主结构

```
action.primary.*
action.workspace.*
action.inline.*
action.bulk.*
action.danger.*
```

#### 典型字段

```
action.primary.bg
action.primary.fg
action.primary.hover
action.primary.active
action.primary.radius
action.primary.height
action.workspace.fg
action.workspace.hover.bg
action.inline.icon
action.inline.hover.bg
action.bulk.bar.bg
action.bulk.bar.border
action.danger.bg
action.danger.fg
action.danger.border
```

### 18. Panel token 建议

#### 面板家族

```
panel.main.*
panel.support.*
panel.continuous.*
panel.inspector.*
panel.config.*
panel.log.*
```

#### 典型字段

```
panel.main.bg
panel.main.border
panel.main.padding
panel.main.title
panel.continuous.section.gap
panel.continuous.divider
panel.inspector.header
panel.inspector.meta
panel.log.row
panel.log.timestamp
panel.log.code
```

### 19. Badge / Label / Chip token 建议

#### Status Badge

```
badge.status.normal.*
badge.status.running.*
badge.status.failed.*
badge.status.pending.*
```

#### Severity Badge

```
badge.severity.low.*
badge.severity.medium.*
badge.severity.high.*
badge.severity.critical.*
```

#### Code Label

```
label.code.bg
label.code.fg
label.code.border
label.code.radius
```

#### Filter Chip

```
chip.filter.bg
chip.filter.fg
chip.filter.border
chip.filter.remove
```

四者不要偷懒合并成一个 `badge.*`。

### 20. Overlay token 建议

建议区分：

```
overlay.drawer.*
overlay.sidesheet.*
overlay.modal.*
overlay.popover.*
overlay.tooltip.*
overlay.command-palette.*
overlay.context-menu.*
```

典型字段包括：

```
bg
border
shadow
radius
padding
header
close
backdrop
motion.enter
motion.exit
```

### 21. Feedback token 建议

建议区分：

```
feedback.toast.*
feedback.inline.*
feedback.banner.*
feedback.alert-item.*
feedback.progress.*
feedback.blocker.*
```

例如：

```
feedback.banner.warning.bg
feedback.banner.critical.border
feedback.inline.running.fg
feedback.progress.track
feedback.progress.fill
```

### 22. Agent / Copilot token 建议

#### Agent

```
agent.task.*
agent.timeline.*
agent.approval.*
agent.output.*
```

#### Copilot

```
copilot.conversation.*
copilot.note.*
copilot.suggestion.*
copilot.toolrow.*
```

这一步很关键，它能防止 AI 页面独立长成另一套产品。

---

## Part F — Interaction & Feedback Layer

### 23. Interaction Layer 的职责

这一层不关心组件是什么，而关心交互状态是什么。

建议命名空间：

```
interaction.focus.*
interaction.hover.*
interaction.selected.*
interaction.active.*
interaction.dragging.*
interaction.resizing.*
```

这层的意义在于让：

- 表格 selected
- panel selected
- item selected
- chart selected state

保持一种系统语法。

### 24. Shared Interaction token 建议

```
interaction.focus.ring
interaction.focus.border
interaction.hover.subtle.bg
interaction.hover.strong.bg
interaction.selected.bg
interaction.selected.border
interaction.selected.text
interaction.active.press
interaction.dragging.shadow
```

---

## Part G — Domain Semantic Layer

### 25. Domain Semantic Layer 的职责

这是 Ditto 与普通设计系统最核心的差异层。
这一层负责把颜色和状态绑定到业务域，而不是绑定到 UI 功能。

建议固定 7 个域：

```
market
risk
execution
system
data-quality
model
agent
```

### 26. Domain 命名建议

#### 26.1 Market

```
market.up.*
market.down.*
market.flat.*
market.strong.*
market.weak.*
```

#### 26.2 Risk

```
risk.low.*
risk.medium.*
risk.high.*
risk.critical.*
risk.near-limit.*
risk.breach.*
```

#### 26.3 Execution

```
execution.pending.*
execution.partial.*
execution.filled.*
execution.cancelled.*
execution.rejected.*
```

#### 26.4 System

```
system.healthy.*
system.degraded.*
system.stale.*
system.down.*
system.recovering.*
```

#### 26.5 Data Quality

```
data-quality.fresh.*
data-quality.delayed.*
data-quality.missing.*
data-quality.partial.*
data-quality.revised.*
```

#### 26.6 Model

```
model.stable.*
model.degrading.*
model.drifting.*
model.invalid.*
model.candidate.*
```

#### 26.7 Agent

```
agent.idle.*
agent.running.*
agent.waiting-approval.*
agent.blocked.*
agent.failed.*
```

这些 token 应直接为 badge、status cell、timeline、chart marker、banner 等提供统一语义来源。

### 27. Domain token 的使用规则

#### 27.1 不跨域借色

不能因为"看起来差不多"就拿 `market.down` 去表示 `risk.critical`。

#### 27.2 先选语义域，再映射到组件

正确路径：

```
业务状态 → Domain token → 组件 token
```

而不是：

```
"这个 badge 看起来要红色" → 临时找个红
```

#### 27.3 同页单义优先

同一页面中，红色最好不要同时代表三个不同域的意思。
如果 unavoidable，也要通过 icon / label / 位置明确区分。

---

## Part H — Density Layer

### 28. Density Layer 的职责

Density 是 Ditto 这种终端产品的核心系统能力。
它不是"顺便调个紧凑模式"，而是一整套变量层。

建议固定三档：

```
density.comfortable.*
density.compact.*
density.ultra.*
```

默认全站建议使用 compact。

### 29. Density token 建议

#### 29.1 布局层

```
density.compact.panel.padding
density.compact.shell.gutter
density.compact.strip.height
```

#### 29.2 表格层

```
density.compact.table.row.height
density.ultra.table.row.height
```

#### 29.3 输入与动作层

```
density.compact.input.height
density.compact.action.height
density.compact.toolbar.height
```

#### 29.4 文本层

```
density.compact.font.delta
density.ultra.font.delta
```

#### 29.5 图表层

```
density.compact.chart.header.height
density.compact.chart.padding
```

注意，Density 不应该直接重写颜色和语义，只应影响：

- 尺寸
- 间距
- 行高
- 控件高度
- 文字微缩放

---

## Part I — Module Pattern Layer

### 30. Module Pattern Layer 的职责

这一层是可选增强层。
它的目标不是让模块视觉割裂，而是在统一基础上，允许不同业务模块有一点轻微偏置。

建议命名空间：

```
module.home.*
module.markets.*
module.research.*
module.trading.*
module.ai.*
module.platform.*
```

### 31. Module Layer 允许做什么

**允许：**

- header 次级节奏差异
- summary strip 的轻偏置
- 某些图表默认 emphasis 方式微调
- 某些模块专属 icon / marker 语法

**不允许：**

- 重写主配色
- 重写 panel 结构
- 重写基础密度
- 让模块看起来像不同产品

#### 31.1 示例

- Markets 可以略强调价格与 breadth
- Research 可以略强调 factor / regime / experiment
- Trading 可以略强调 session / execution / risk
- AI 可以略强调 session / agent status / approval
- Platform 可以略强调 validation / system health / logs

但这些都只能是轻微 pattern 偏置，不是独立主题。

---

## Part J — Token 命名规则

### 32. 命名格式建议

推荐统一采用：

```
[layer].[family].[role].[state].[property]
```

并允许根据需要裁剪层级。

例如：

```
panel.main.bg
table.ledger.row.selected.bg
action.primary.hover.bg
badge.severity.high.fg
shell.analytical.header.height
visual.timeline.node.failed.bg
agent.approval.border
risk.critical.fg
```

### 33. 命名风格规范

#### 33.1 一律使用小写 kebab 或 dot namespace

- dot namespace 用于 token 分类
- 内部单词使用 kebab-case

例如：

```
data-quality.delayed.fg
agent.waiting-approval.bg
```

#### 33.2 属性名统一

固定使用：

```
bg / fg / border / shadow / radius / height / width
padding / gap / size / label / value / icon / track / fill
```

不要同义混用：

| 避免 | 统一为 |
|------|--------|
| background | bg |
| text | fg |
| spacing | gap |
| stroke | border |

#### 33.3 避免情绪词与审美词

不要用：

```
pretty / soft / cool / vivid / subtleGray2 / fancyBlue
```

这些词在系统维护里几乎没有价值。

#### 33.4 避免页面名耦合

不要用：

```
researchMainCard
ordersPageRed
dashboardTitleBlue
```

除非进入 `module.*` 层，否则 token 不应绑定某个具体页面。

---

## Part K — Token 使用优先级

### 34. 前端使用顺序

在实现时，始终按这个顺序查找 token：

1. Domain Semantic token
2. Component / Data View token
3. Shell / Surface token
4. Foundation primitive

前端不应直接从 primitive 开始找颜色。
应该尽量通过语义 token 使用。

**例如要做订单拒绝状态文本：**

错误方式：

```
直接取 red.500
```

正确方式：

```
execution.rejected.fg
若组件是 badge，再映射到 badge.status.rejected.fg
```

---

## Part L — Token 与 AI Coding 的约束建议

### 35. 为什么这部分重要

后续很可能大量用 Claude Code / Codex / Agent 来生成页面和组件。
如果 token 没有明确规则，AI 会疯狂发明新变量名，设计系统会迅速失控。

### 36. 对 AI coding 的约束建议

建议在工程约束里明确：

#### 36.1 禁止直接写色值

禁止：

```
#3b82f6
rgb(...)
bg-slate-800
text-red-500
```

必须优先引用 token。

#### 36.2 禁止直接写"页面私有变量"

禁止：

```
--research-card-bg
--orders-danger-red
```

除非经设计系统批准进入 `module.*`。

#### 36.3 新 token 必须先选层级

新增 token 时必须回答：

- 这是 foundation 吗？
- 这是 shell 吗？
- 这是 data view 吗？
- 这是 component 吗？
- 这是 domain semantic 吗？
- 这是 density 吗？

#### 36.4 优先复用，不优先新增

AI 生成新组件时，应优先引用已有 token 组合，而不是每次创建新 token。

---

## Part M — 旧变量与迁移建议

### 37. 迁移原则

如果已经有部分 token、Tailwind semantic color、design token 草稿，建议迁移时遵循：

#### 37.1 先归类

先把旧变量归入这 9 层之一，而不是急着重命名。

#### 37.2 先消除同义词

统一：

```
card-bg / panel-bg          → panel.*
primary-blue / accent-blue  → brand.*
warning                     → 按 risk / data-quality / system 拆域
```

#### 37.3 先建立 alias，再慢慢替换

避免一次性全量硬切导致代码震荡。

#### 37.4 先固化高频区域

优先把以下区域切到新 token 体系：

- shell
- table
- panel
- action
- badge / label
- chart container

因为这些最影响整体气质。

---

## Part N — 最小可行 Token 集

### 38. 第一阶段最值得先落地的 token 组

如果要尽快开始落地，而不是先写几百个 token，建议优先只做这些：

**基础层**

```
neutral / brand / text / border / surface
```

**Shell 层**

```
shell.analytical.* / shell.catalog.* / shell.studio.* / shell.ops.*
```

**Table 层**

```
table.analytical.* / table.ledger.* / table.ops.*
```

**Panel 层**

```
panel.main.* / panel.continuous.* / panel.inspector.* / panel.config.*
```

**Action 层**

```
action.primary.* / action.workspace.* / action.inline.* / action.danger.*
```

**Badge / Label 层**

```
badge.status.* / badge.severity.* / label.code.* / chip.filter.*
```

**Domain 层**

```
market.* / risk.* / execution.* / system.* / data-quality.* / model.* / agent.*
```

**Density 层**

```
density.compact.* / density.ultra.*
```

只要这几组先立住，Ditto 的整体语法就基本稳了。

---

## Part O — 验收标准

### 39. 一套合格的 Ditto token 体系，必须满足

- [ ] 能清楚区分 foundation、surface、shell、data view、component、domain、density、module 等层级
- [ ] 不同业务域不会共享同一个模糊状态色
- [ ] 同一组件家族能通过 token 清楚表达层级和状态
- [ ] 页面和组件不需要频繁写死颜色、间距、尺寸
- [ ] AI coding 可以按规则稳定复用 token
- [ ] 模块之间有轻微差异，但仍然像同一个产品
- [ ] 未来新增页面和组件时，不需要重新发明一套变量体系
