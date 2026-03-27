# Ditto Design Token v2 — 架构规范

> **版本**: 0.1.0
> **主题**: Dark（Light 结构已预留，值待定）
> **色彩格式**: HEX（设计源格式，实现时由工具链转换为 OKLCH）
> **前置文档**: [视觉设计原则](./2026-03-26-ditto-visual-principles.md)

---

## 1. 概述

Ditto 的视觉基础建立在 **"机构级量化工作台的低噪声判断效率"** 之上，而非通用 SaaS 的优雅克制。

### 设计原则

1. 视觉首先服务判断，其次才服务美感
2. 页面是工作台，不是卡片集合
3. 中性色层级非常稳，撑起高级感
4. 强调色非常克制，只负责交互与少量重点
5. 业务语义颜色按域拆开，不能混
6. 图表、表格、状态反馈围绕判断效率设计

### 配色方向

**深色中性底 + 冷静低饱和强调 + 稳定业务语义色**

- 不是纯黑科技风，也不是亮蓝金融科技风
- 偏机构级工作站风格
- 核心目标：长时间看不累、多模块并置不乱、图表与表格都稳

---

## 2. Token 四层架构

```
Layer 1: Primitive          基础色板与基础灰阶
  ↓ 引用
Layer 2: Semantic Core      通用语义（text / surface / border / icon / state）
  ↓ 引用
Layer 3: Domain Semantic    量化业务语义（market / risk / execution / system / data / model）
  ↓ 引用
Layer 4: Component          组件级语义（chart / grid / kpi / badge / toast / panel / button / ...）
```

### 引用规则

- Layer N 只能引用 Layer N-1 或更底层
- Component Token 不得直接引用 Primitive Token
- Domain Semantic Token 不得跨域引用（如 `risk.*` 不得引用 `market.*`）
- 所有引用在文档中使用 `{path}` 语法标注，实现时展开为 `var(--xxx)`

### 主题策略

- **Dark**：主设计目标，本文档中所有值均为 Dark 值
- **Light**：结构已预留（token 名称与 dark 一致），值待后续设计稿确定后填充
- 切换方式：CSS class `.dark` / `:root`，同一套 token 名称，不同值

---

## 3. Layer 1: Primitive Tokens

### 3.1 色彩原语

#### Neutral — 基础中性色（14 级）

这是 Ditto 最重要的一组色板。目标不是对比强，而是层级稳。如果 neutral 做不好，整套系统一定显廉价。

| Token | 值 | 用途 |
|-------|------|------|
| `neutral.0` | `#0B0F14` | App 最外层背景 |
| `neutral.25` | `#0E1319` | Sidebar / chrome 深层背景 |
| `neutral.50` | `#10161D` | 主 surface |
| `neutral.75` | `#131A22` | 次级 surface |
| `neutral.100` | `#17202A` | Elevated surface / hover 容器 |
| `neutral.150` | `#1B2530` | Active surface / panel raised |
| `neutral.200` | `#22303D` | 强结构底 |
| `neutral.300` | `#2B3A49` | Subtle border 强化版 |
| `neutral.400` | `#385062` | Default border / divider |
| `neutral.500` | `#4A657B` | 强边界 / disabled icon |
| `neutral.600` | `#6C8195` | Muted text |
| `neutral.700` | `#91A3B5` | Secondary text |
| `neutral.800` | `#B7C4D1` | Body text |
| `neutral.900` | `#DDE6EE` | Primary text |
| `neutral.950` | `#F5F8FB` | 极少量反白场景 |

> **中性色不可缩减。** 对高密信息界面，14 级灰阶是支撑专业感的基础，不是冗余。

#### Blue — 主强调色（7 级）

低饱和冷蓝，偏机构感。不建议用过亮、过互联网化的蓝。

| Token | 值 |
|-------|------|
| `blue.50` | `#0F1E3A` |
| `blue.100` | `#132952` |
| `blue.200` | `#1D3D78` |
| `blue.300` | `#3159A6` |
| `blue.400` | `#4C78D0` |
| `blue.500` | `#5F8FF5` |
| `blue.600` | `#82A9FF` |
| `blue.700` | `#A9C3FF` |

**用途限制：** 当前选中、焦点 ring、主交互高亮、重要对比序列、关键筛选激活态。accent 不能变成到处刷存在感的"品牌蓝"。

#### Cyan — 辅助强调色（6 级）

更冷静的青蓝系，严格限用。主要用于图表 compare、linked state、辅助维度。

| Token | 值 |
|-------|------|
| `cyan.50` | `#0D1C22` |
| `cyan.100` | `#11303A` |
| `cyan.200` | `#185067` |
| `cyan.300` | `#23748F` |
| `cyan.400` | `#2E9AB8` |
| `cyan.500` | `#46B8D8` |
| `cyan.600` | `#73CAE3` |

#### Red（7 级）

| Token | 值 |
|-------|------|
| `red.50` | `#2A1418` |
| `red.100` | `#341C21` |
| `red.200` | `#442126` |
| `red.300` | `#6D313A` |
| `red.400` | `#8D424B` |
| `red.500` | `#D85C5C` |
| `red.600` | `#E06A6A` |
| `red.700` | `#F0B6B6` |

#### Green（7 级）

| Token | 值 |
|-------|------|
| `green.50` | `#122019` |
| `green.100` | `#16281F` |
| `green.200` | `#17271F` |
| `green.300` | `#244731` |
| `green.400` | `#2D6144` |
| `green.500` | `#43A36F` |
| `green.600` | `#58B77A` |
| `green.700` | `#9BD4AF` |

#### Amber（7 级）

| Token | 值 |
|-------|------|
| `amber.50` | `#211A10` |
| `amber.100` | `#2C2315` |
| `amber.200` | `#2D2417` |
| `amber.300` | `#4B3B22` |
| `amber.400` | `#6D5730` |
| `amber.500` | `#D0A04A` |
| `amber.600` | `#D9A85B` |
| `amber.700` | `#E8C98B` |

#### Orange（7 级）

| Token | 值 |
|-------|------|
| `orange.50` | `#24160F` |
| `orange.100` | `#312116` |
| `orange.200` | `#352416` |
| `orange.300` | `#5A3725` |
| `orange.400` | `#7B4C33` |
| `orange.500` | `#E38B57` |
| `orange.600` | `#E28D5D` |
| `orange.700` | `#F1C3A0` |

#### Purple（7 级）

| Token | 值 |
|-------|------|
| `purple.50` | `#1F1827` |
| `purple.100` | `#241F31` |
| `purple.200` | `#27212D` |
| `purple.300` | `#43365A` |
| `purple.400` | `#5B4B7A` |
| `purple.500` | `#B497E7` |
| `purple.600` | `#C4B0EC` |
| `purple.700` | `#DDD1F6` |

#### Alpha — 透明度工具值

| Token | 值 |
|-------|------|
| `alpha.white.2` | `rgba(255,255,255,0.02)` |
| `alpha.white.3` | `rgba(255,255,255,0.03)` |
| `alpha.white.4` | `rgba(255,255,255,0.04)` |
| `alpha.white.6` | `rgba(255,255,255,0.06)` |
| `alpha.white.8` | `rgba(255,255,255,0.08)` |
| `alpha.white.10` | `rgba(255,255,255,0.10)` |
| `alpha.white.12` | `rgba(255,255,255,0.12)` |
| `alpha.white.16` | `rgba(255,255,255,0.16)` |
| `alpha.white.24` | `rgba(255,255,255,0.24)` |
| `alpha.white.28` | `rgba(255,255,255,0.28)` |
| `alpha.black.48` | `rgba(0,0,0,0.48)` |
| `alpha.black.56` | `rgba(0,0,0,0.56)` |
| `alpha.black.64` | `rgba(0,0,0,0.64)` |
| `alpha.black.72` | `rgba(0,0,0,0.72)` |

> **Light Theme**: 所有色彩原语值 TBD。Neutral 灰阶方向相反（0 最浅，950 最深），色相保持一致。

---

### 3.2 间距

基于 4px 基准网格。

| Token | 值 | px |
|-------|-----|-----|
| `spacing.0` | `0` | 0 |
| `spacing.1` | `2px` | 2 |
| `spacing.2` | `4px` | 4 |
| `spacing.3` | `6px` | 6 |
| `spacing.4` | `8px` | 8 |
| `spacing.5` | `10px` | 10 |
| `spacing.6` | `12px` | 12 |
| `spacing.8` | `16px` | 16 |
| `spacing.10` | `20px` | 20 |
| `spacing.12` | `24px` | 24 |
| `spacing.14` | `28px` | 28 |
| `spacing.16` | `32px` | 32 |
| `spacing.20` | `40px` | 40 |
| `spacing.24` | `48px` | 48 |
| `spacing.32` | `64px` | 64 |

---

### 3.3 圆角

| Token | 值 |
|-------|-----|
| `radius.none` | `0` |
| `radius.xs` | `4px` |
| `radius.sm` | `6px` |
| `radius.md` | `8px` |
| `radius.lg` | `10px` |
| `radius.xl` | `12px` |
| `radius.xxl` | `16px` |
| `radius.round` | `999px` |

---

### 3.4 字体原语

#### 字体族

| Token | 值 |
|-------|-----|
| `font.family.sans` | `'Inter', 'IBM Plex Sans', 'Segoe UI', sans-serif` |
| `font.family.mono` | `'IBM Plex Mono', 'JetBrains Mono', monospace` |

#### 字号

| Token | 值 | 用途 |
|-------|-----|------|
| `font.size.xs` | `11px` | Caption / meta |
| `font.size.sm` | `12px` | Label |
| `font.size.md` | `13px` | Body compact |
| `font.size.lg` | `14px` | Body default |
| `font.size.xl` | `16px` | Section header |
| `font.size.xxl` | `18px` | Sub-title |
| `font.size.display-sm` | `20px` | Page title (small) |
| `font.size.display-md` | `24px` | Page title |
| `font.size.display-lg` | `28px` | Page title (large) |
| `font.size.kpi-sm` | `24px` | KPI value (small) |
| `font.size.kpi-md` | `32px` | KPI value |
| `font.size.kpi-lg` | `40px` | KPI value (large) |

#### 字重

| Token | 值 |
|-------|-----|
| `font.weight.regular` | `400` |
| `font.weight.medium` | `500` |
| `font.weight.semibold` | `600` |
| `font.weight.bold` | `700` |

#### 行高

| Token | 值 |
|-------|-----|
| `font.lineHeight.tight` | `1.2` |
| `font.lineHeight.normal` | `1.4` |
| `font.lineHeight.relaxed` | `1.6` |

#### 字间距

| Token | 值 |
|-------|-----|
| `font.tracking.tight` | `-0.02em` |
| `font.tracking.normal` | `0` |
| `font.tracking.wide` | `0.02em` |

---

### 3.5 阴影

| Token | 值 | 用途 |
|-------|-----|------|
| `shadow.none` | `none` | 默认（surface 层级差已足够） |
| `shadow.sm` | `0 1px 2px rgba(0,0,0,0.18)` | 轻微浮层 |
| `shadow.md` | `0 6px 18px rgba(0,0,0,0.28)` | Tooltip / Popover |
| `shadow.lg` | `0 12px 28px rgba(0,0,0,0.36)` | Modal |
| `shadow.overlay` | `0 16px 40px rgba(0,0,0,0.44)` | 全屏浮层 |

---

### 3.6 动效

#### 时长

| Token | 值 | 用途 |
|-------|-----|------|
| `motion.duration.instant` | `80ms` | 即时反馈（hover light） |
| `motion.duration.fast` | `140ms` | 快速过渡 |
| `motion.duration.normal` | `220ms` | 标准过渡 |
| `motion.duration.slow` | `320ms` | 慢速过渡（展开/收起） |
| `motion.duration.xslow` | `480ms` | 页面级过渡 |

#### 缓动

| Token | 值 | 用途 |
|-------|-----|------|
| `motion.easing.standard` | `cubic-bezier(0.2, 0, 0, 1)` | 默认 |
| `motion.easing.decelerate` | `cubic-bezier(0, 0, 0, 1)` | 入场 |
| `motion.easing.accelerate` | `cubic-bezier(0.3, 0, 1, 1)` | 退场 |
| `motion.easing.emphasized` | `cubic-bezier(0.2, 0, 0, 1.2)` | 强调（微过冲） |

---

## 4. Layer 2: Semantic Core

通用语义层。所有业务域共享的基础语义 token。

> **Light Theme**: 结构与 Dark 一致，值 TBD。

### 4.1 Text

建议 4–6 个层级，多了设计师也会乱用。

| Token | Dark 引用 | 用途 |
|-------|----------|------|
| `text.primary` | `neutral.900` | 标题、核心数据、主文本 |
| `text.secondary` | `neutral.700` | 描述、辅助文本、标签 |
| `text.tertiary` | `neutral.600` | 提示、次级标签 |
| `text.muted` | `neutral.500` | 占位符、禁用状态提示 |
| `text.disabled` | `neutral.400` | 禁用文本 |
| `text.inverse` | `neutral.0` | 反白文本（深色背景上） |
| `text.link` | `blue.600` | 链接 |

### 4.2 Icon

图标不要比文字更抢眼。

| Token | Dark 引用 | 用途 |
|-------|----------|------|
| `icon.primary` | `text.secondary` | 默认图标 |
| `icon.muted` | `text.muted` | 弱化图标 |
| `icon.active` | `blue.500` | 激活/选中图标 |
| `icon.disabled` | `text.disabled` | 禁用图标 |
| `icon.inverse` | `text.inverse` | 反白图标 |

### 4.3 Surface

表意明确，不要一堆 `surface-1` `surface-2` `surface-3`。业务团队更容易理解 `canvas/panel/elevated/raised`。

| Token | Dark 引用 | 用途 |
|-------|----------|------|
| `surface.app` | `neutral.0` | App 最外层背景 |
| `surface.chrome` | `neutral.25` | Sidebar / topbar 深层背景 |
| `surface.canvas` | `neutral.50` | 主内容区背景 |
| `surface.panel` | `neutral.75` | 面板 / 卡片背景 |
| `surface.elevated` | `neutral.100` | 浮层 / hover 容器 |
| `surface.raised` | `neutral.150` | Active surface / panel raised |
| `surface.active` | `neutral.200` | 强结构底 |
| `surface.overlay` | `alpha.black.72` | 遮罩层 |
| `surface.inverse` | `neutral.900` | 反白 surface |

### 4.4 Border

边框尽量少，但一旦使用必须稳定。

| Token | Dark 引用 | 用途 |
|-------|----------|------|
| `border.subtle` | `neutral.300` | 弱边框（面板内部） |
| `border.default` | `neutral.400` | 默认边框（输入框、表格） |
| `border.strong` | `neutral.500` | 强边框（强调区域） |
| `border.inverse` | `neutral.800` | 反白边框 |
| `border.focus` | `blue.500` | 焦点边框 |

### 4.5 State

| Token | Dark 引用 | 用途 |
|-------|----------|------|
| `state.hover-bg` | `alpha.white.3` | Hover 背景 |
| `state.pressed-bg` | `alpha.white.6` | Pressed 背景 |
| `state.selected-bg` | `rgba(95,143,245,0.16)` | 选中背景 |
| `state.selected-soft-bg` | `rgba(95,143,245,0.10)` | 选中背景（轻） |
| `state.focus-ring` | `blue.500` | 焦点 ring 颜色 |
| `state.focus-ring-outer` | `rgba(95,143,245,0.28)` | 焦点 ring 外发光 |
| `state.disabled-opacity` | `0.42` | 禁用透明度 |
| `state.drag-preview` | `alpha.white.8` | 拖拽预览背景 |

> Hover 一定要轻。Selected 要可感知，但不能像高亮块。

### 4.6 Overlay

| Token | Dark 引用 | 用途 |
|-------|----------|------|
| `overlay.scrim` | `alpha.black.64` | 遮罩 |
| `overlay.modal` | `alpha.black.72` | Modal 遮罩 |
| `overlay.popover-border` | `border.default` | Popover 边框 |
| `overlay.popover-surface` | `surface.elevated` | Popover 背景 |

---

## 5. Layer 3: Domain Semantic

量化业务语义层。**各域严格独立，禁止跨域共享语义。**

品牌色 ≠ 交易语义色。蓝色是品牌/交互色，但不是"买入"色，也不是"在线"色，也不是"已提交"色。

> **Light Theme**: 所有域结构已预留，值 TBD。

### 5.1 Market — 市场语义

#### 模式切换

A 股和海外市场涨跌颜色相反，必须支持模式切换。组件只认 `market.up` / `market.down`，由 `market-locale` 决定映射。

| 模式 | up | down |
|------|-----|------|
| **CN**（默认） | 红涨 | 绿跌 |
| **Global** | 绿涨 | 红跌 |

**实现方式：** CSS class 或 data attribute 切换语义映射，不重定义颜色系统。Token 层支持，不写死在组件里。

#### CN 模式（默认）

| Token | 值 | 用途 |
|-------|-----|------|
| `market.up.fg` | `red.500` → `#D85C5C` | 涨幅文字 |
| `market.up.fg-soft` | `red.400` → `#8D424B` | 涨幅弱化文字 |
| `market.up.bg` | `red.50` → `#2A1418` | 涨幅背景 |
| `market.up.border` | `red.300` → `#6D313A` | 涨幅边框 |
| `market.up.flash` | `rgba(216,92,92,0.18)` | 涨幅闪烁 |
| `market.down.fg` | `green.500` → `#43A36F` | 跌幅文字 |
| `market.down.fg-soft` | `green.400` → `#2D6144` | 跌幅弱化文字 |
| `market.down.bg` | `green.50` → `#122019` | 跌幅背景 |
| `market.down.border` | `green.300` → `#244731` | 跌幅边框 |
| `market.down.flash` | `rgba(67,163,111,0.18)` | 跌幅闪烁 |
| `market.flat.fg` | `neutral.700` → `#91A3B5` | 平盘文字 |
| `market.flat.bg` | `neutral.75` → `#131A22` | 平盘背景 |
| `market.flat.border` | `neutral.300` → `#2B3A49` | 平盘边框 |
| `market.neutral.fg` | `blue.500` → `#5F8FF5` | 中性行情 |
| `market.neutral.bg` | `rgba(95,143,245,0.10)` | 中性背景 |
| `market.neutral.border` | `blue.300` → `#3159A6` | 中性边框 |

#### Global 模式

| Token | 值 |
|-------|-----|
| `market.up.fg` | `green.500` → `#43A36F` |
| `market.up.fg-soft` | `green.400` → `#2D6144` |
| `market.up.bg` | `green.50` → `#122019` |
| `market.up.border` | `green.300` → `#244731` |
| `market.up.flash` | `rgba(67,163,111,0.18)` |
| `market.down.fg` | `red.500` → `#D85C5C` |
| `market.down.fg-soft` | `red.400` → `#8D424B` |
| `market.down.bg` | `red.50` → `#2A1418` |
| `market.down.border` | `red.300` → `#6D313A` |
| `market.down.flash` | `rgba(216,92,92,0.18)` |
| `market.flat.*` | 同 CN 模式 |
| `market.neutral.*` | 同 CN 模式 |

---

### 5.2 Risk — 风险语义

风险不是普通 status。拆成层级，而不是只做 warning/error。

| Token | 值 | 用途 |
|-------|-----|------|
| `risk.normal.fg` | `neutral.700` → `#91A3B5` | 风险正常 |
| `risk.normal.bg` | `neutral.75` → `#131A22` | |
| `risk.normal.border` | `neutral.300` → `#2B3A49` | |
| `risk.watch.fg` | `amber.500` → `#D0A04A` | 关注 |
| `risk.watch.bg` | `amber.100` → `#2C2315` | |
| `risk.watch.border` | `amber.300` → `#4B3B22` | |
| `risk.elevated.fg` | `orange.500` → `#E38B57` | 风险升高 |
| `risk.elevated.bg` | `orange.100` → `#312116` | |
| `risk.elevated.border` | `orange.300` → `#5A3725` | |
| `risk.breach.fg` | `red.600` → `#E06A6A` | 风险突破 |
| `risk.breach.bg` | `red.100` → `#341C21` | |
| `risk.breach.border` | `red.400` → `#8D424B` | |
| `risk.locked.fg` | `red.700` → `#F0B6B6` | 账户锁定 |
| `risk.locked.bg` | `red.200` → `#442126` | |
| `risk.locked.border` | `red.500` → `#D85C5C` | |

**适用场景：** 风险卡片、限额状态、风险线、账户受限、kill switch 前后状态。

---

### 5.3 Execution — 执行语义

交易系统里必须独立。**执行语义和价格语义要分开**，否则用户会混淆。

| Token | 值 | 用途 |
|-------|-----|------|
| `execution.pending.fg` | `neutral.800` → `#B7C4D1` | 待提交 |
| `execution.pending.bg` | `neutral.75` → `#131A22` | |
| `execution.pending.border` | `neutral.300` → `#2B3A49` | |
| `execution.submitted.fg` | `blue.600` → `#82A9FF` | 已提交 |
| `execution.submitted.bg` | `blue.50` → `#0F1E3A` | |
| `execution.submitted.border` | `blue.300` → `#3159A6` | |
| `execution.partial.fg` | `amber.600` → `#D9A85B` | 部分成交 |
| `execution.partial.bg` | `amber.100` → `#2C2315` | |
| `execution.partial.border` | `amber.300` → `#4B3B22` | |
| `execution.filled.fg` | `green.600` → `#58B77A` | 全部成交 |
| `execution.filled.bg` | `green.100` → `#16281F` | |
| `execution.filled.border` | `green.300` → `#244731` | |
| `execution.cancelled.fg` | `neutral.700` → `#91A3B5` | 已撤单 |
| `execution.cancelled.bg` | `neutral.100` → `#17202A` | |
| `execution.cancelled.border` | `neutral.300` → `#2B3A49` | |
| `execution.rejected.fg` | `red.600` → `#E06A6A` | 已拒绝 |
| `execution.rejected.bg` | `red.100` → `#341C21` | |
| `execution.rejected.border` | `red.300` → `#6D313A` | |
| `execution.expired.fg` | `purple.500` → `#B497E7` | 已过期 |
| `execution.expired.bg` | `purple.100` → `#241F31` | |
| `execution.expired.border` | `purple.300` → `#43365A` | |

> 注意：`filled` 不是 `market.up/down`。执行语义是执行语义，价格语义是价格语义。

---

### 5.4 System — 系统语义

平台健康和运行状态。

| Token | 值 | 用途 |
|-------|-----|------|
| `system.online.fg` | `green.600` → `#58B77A` | 在线 |
| `system.online.bg` | `green.100` → `#16281F` | |
| `system.online.border` | `green.300` → `#244731` | |
| `system.degraded.fg` | `amber.600` → `#D9A85B` | 降级 |
| `system.degraded.bg` | `amber.100` → `#2C2315` | |
| `system.degraded.border` | `amber.300` → `#4B3B22` | |
| `system.offline.fg` | `red.600` → `#E06A6A` | 离线 |
| `system.offline.bg` | `red.100` → `#341C21` | |
| `system.offline.border` | `red.300` → `#6D313A` | |
| `system.syncing.fg` | `blue.600` → `#82A9FF` | 同步中 |
| `system.syncing.bg` | `blue.50` → `#0F1E3A` | |
| `system.syncing.border` | `blue.300` → `#3159A6` | |
| `system.maintenance.fg` | `purple.500` → `#B497E7` | 维护中 |
| `system.maintenance.bg` | `purple.100` → `#241F31` | |
| `system.maintenance.border` | `purple.300` → `#43365A` | |

---

### 5.5 Data — 数据新鲜度语义

非常重要，必须独立。不能与 system.warning 混用。

| Token | 值 | 用途 |
|-------|-----|------|
| `data.fresh.fg` | `green.600` → `#58B77A` | 数据新鲜 |
| `data.fresh.bg` | `green.100` → `#16281F` | |
| `data.fresh.border` | `green.300` → `#244731` | |
| `data.recent.fg` | `green.500` → `#43A36F` | 数据较新 |
| `data.recent.bg` | `green.50` → `#122019` | |
| `data.recent.border` | `green.200` → `#17271F` | |
| `data.stale.fg` | `amber.600` → `#D9A85B` | 数据陈旧 |
| `data.stale.bg` | `amber.100` → `#2C2315` | |
| `data.stale.border` | `amber.300` → `#4B3B22` | |
| `data.delayed.fg` | `orange.600` → `#E28D5D` | 数据延迟 |
| `data.delayed.bg` | `orange.100` → `#312116` | |
| `data.delayed.border` | `orange.300` → `#5A3725` | |
| `data.missing.fg` | `neutral.700` → `#91A3B5` | 数据缺失 |
| `data.missing.bg` | `neutral.100` → `#17202A` | |
| `data.missing.border` | `neutral.300` → `#2B3A49` | |
| `data.backfilling.fg` | `blue.600` → `#82A9FF` | 回补中 |
| `data.backfilling.bg` | `blue.50` → `#0F1E3A` | |
| `data.backfilling.border` | `blue.300` → `#3159A6` | |

**适用场景：** 行情更新时间、因子数据状态、ETL 回补、最新 bar 是否 final、回测数据完整性提示。

---

### 5.6 Model — 模型 / 研究语义

Research & ML 模块独立语义，不复用 system 状态。

| Token | 值 | 用途 |
|-------|-----|------|
| `model.draft.fg` | `neutral.700` → `#91A3B5` | 草稿 |
| `model.draft.bg` | `neutral.100` → `#17202A` | |
| `model.draft.border` | `neutral.300` → `#2B3A49` | |
| `model.validating.fg` | `blue.600` → `#82A9FF` | 验证中 |
| `model.validating.bg` | `blue.50` → `#0F1E3A` | |
| `model.validating.border` | `blue.300` → `#3159A6` | |
| `model.accepted.fg` | `green.600` → `#58B77A` | 已接受 |
| `model.accepted.bg` | `green.100` → `#16281F` | |
| `model.accepted.border` | `green.300` → `#244731` | |
| `model.degraded.fg` | `amber.600` → `#D9A85B` | 退化 |
| `model.degraded.bg` | `amber.100` → `#2C2315` | |
| `model.degraded.border` | `amber.300` → `#4B3B22` | |
| `model.deprecated.fg` | `purple.500` → `#B497E7` | 已废弃 |
| `model.deprecated.bg` | `purple.100` → `#241F31` | |
| `model.deprecated.border` | `purple.300` → `#43365A` | |
| `model.failed.fg` | `red.600` → `#E06A6A` | 失败 |
| `model.failed.bg` | `red.100` → `#341C21` | |
| `model.failed.border` | `red.300` → `#6D313A` | |

---

## 6. Layer 4: Component Tokens

组件级语义 token。只引用 Layer 2 (Semantic Core) 和 Layer 3 (Domain Semantic)。

> **Light Theme**: 结构已预留，值 TBD。

### 6.1 Page

| Token | 引用 | 用途 |
|-------|------|------|
| `page.bg` | `surface.app` | 页面背景 |
| `page.section-gap-y` | `spacing.16` | 区块间垂直间距 |
| `page.block-gap-y` | `spacing.10` | 块间垂直间距 |
| `page.content-max-width` | `1600px` | 内容最大宽度 |

---

### 6.2 Panel

| Token | 引用 | 用途 |
|-------|------|------|
| `panel.bg` | `surface.panel` | 面板背景 |
| `panel.bg-elevated` | `surface.elevated` | 浮层面板背景 |
| `panel.border` | `border.subtle` | 面板边框 |
| `panel.border-strong` | `border.default` | 强边框面板 |
| `panel.radius` | `radius.xl` | 面板圆角 |
| `panel.padding-x` | `spacing.8` | 水平内边距 |
| `panel.padding-y` | `spacing.8` | 垂直内边距 |
| `panel.shadow` | `shadow.none` | 面板阴影 |

---

### 6.3 Card

| Token | 引用 | 用途 |
|-------|------|------|
| `card.bg` | `surface.panel` | 卡片背景 |
| `card.bg-hover` | `surface.elevated` | Hover 背景 |
| `card.border` | `border.subtle` | 卡片边框 |
| `card.radius` | `radius.lg` | 卡片圆角 |
| `card.padding-x` | `spacing.6` | 水平内边距 |
| `card.padding-y` | `spacing.6` | 垂直内边距 |

---

### 6.4 Toolbar

| Token | 引用 | 用途 |
|-------|------|------|
| `toolbar.bg` | `surface.canvas` | 工具栏背景 |
| `toolbar.border-bottom` | `border.subtle` | 底部边框 |
| `toolbar.control-gap` | `spacing.4` | 控件间距 |
| `toolbar.height-md` | `44px` | 中等高度 |
| `toolbar.height-sm` | `36px` | 小高度 |

---

### 6.5 Input

| Token | 引用 | 用途 |
|-------|------|------|
| `input.bg` | `surface.raised` | 输入框背景 |
| `input.bg-hover` | `surface.active` | Hover 背景 |
| `input.text` | `text.primary` | 输入文字 |
| `input.placeholder` | `text.muted` | 占位符 |
| `input.border` | `border.subtle` | 默认边框 |
| `input.border-hover` | `border.default` | Hover 边框 |
| `input.border-focus` | `border.focus` | 焦点边框 |
| `input.radius` | `radius.md` | 圆角 |
| `input.height-md` | `36px` | 中等高度 |
| `input.height-sm` | `30px` | 小高度 |
| `input.padding-x` | `spacing.4` | 水平内边距 |

---

### 6.6 Button

| Token | 引用 | 用途 |
|-------|------|------|
| `button.primary.bg` | `blue.500` | 主按钮背景 |
| `button.primary.bg-hover` | `blue.400` | 主按钮 Hover |
| `button.primary.text` | `text.inverse` | 主按钮文字 |
| `button.primary.border` | `blue.500` | 主按钮边框 |
| `button.secondary.bg` | `surface.raised` | 次按钮背景 |
| `button.secondary.bg-hover` | `surface.active` | 次按钮 Hover |
| `button.secondary.text` | `text.primary` | 次按钮文字 |
| `button.secondary.border` | `border.subtle` | 次按钮边框 |
| `button.ghost.bg` | `transparent` | 幽灵按钮背景 |
| `button.ghost.bg-hover` | `state.hover-bg` | 幽灵按钮 Hover |
| `button.ghost.text` | `text.secondary` | 幽灵按钮文字 |
| `button.ghost.border` | `transparent` | 幽灵按钮边框 |
| `button.danger.bg` | `red.500` | 危险按钮背景 |
| `button.danger.bg-hover` | `red.400` | 危险按钮 Hover |
| `button.danger.text` | `text.inverse` | 危险按钮文字 |
| `button.danger.border` | `red.500` | 危险按钮边框 |
| `button.height-md` | `36px` | 中等高度 |
| `button.height-sm` | `30px` | 小高度 |
| `button.radius` | `radius.md` | 圆角 |
| `button.padding-x-md` | `spacing.5` | 中等水平内边距 |
| `button.padding-x-sm` | `spacing.4` | 小水平内边距 |

---

### 6.7 Tabs

| Token | 引用 | 用途 |
|-------|------|------|
| `tabs.text` | `text.secondary` | Tab 文字 |
| `tabs.text-active` | `text.primary` | 激活文字 |
| `tabs.bg-hover` | `state.hover-bg` | Hover 背景 |
| `tabs.bg-active` | `state.selected-soft-bg` | 激活背景 |
| `tabs.indicator` | `blue.500` | 指示条 |
| `tabs.radius` | `radius.md` | 圆角 |
| `tabs.height` | `34px` | 高度 |
| `tabs.gap` | `spacing.2` | 间距 |

---

### 6.8 Badge

| Token | 引用 | 用途 |
|-------|------|------|
| `badge.neutral.fg` | `text.secondary` | 中性标签 |
| `badge.neutral.bg` | `surface.raised` | |
| `badge.neutral.border` | `border.subtle` | |
| `badge.info.fg` | `blue.600` | 信息标签 |
| `badge.info.bg` | `blue.50` | |
| `badge.info.border` | `blue.300` | |
| `badge.success.fg` | `green.600` | 成功标签 |
| `badge.success.bg` | `green.100` | |
| `badge.success.border` | `green.300` | |
| `badge.warning.fg` | `amber.600` | 警告标签 |
| `badge.warning.bg` | `amber.100` | |
| `badge.warning.border` | `amber.300` | |
| `badge.danger.fg` | `red.600` | 危险标签 |
| `badge.danger.bg` | `red.100` | |
| `badge.danger.border` | `red.300` | |
| `badge.radius` | `radius.round` | 圆角 |
| `badge.height` | `22px` | 高度 |
| `badge.padding-x` | `spacing.3` | 水平内边距 |

---

### 6.9 Toast

| Token | 引用 | 用途 |
|-------|------|------|
| `toast.bg` | `surface.elevated` | Toast 背景 |
| `toast.border` | `border.default` | Toast 边框 |
| `toast.text` | `text.primary` | Toast 文字 |
| `toast.shadow` | `shadow.overlay` | Toast 阴影 |
| `toast.radius` | `radius.lg` | Toast 圆角 |
| `toast.info.accent` | `blue.500` | 信息强调 |
| `toast.success.accent` | `green.600` | 成功强调 |
| `toast.warning.accent` | `amber.600` | 警告强调 |
| `toast.danger.accent` | `red.600` | 危险强调 |

---

### 6.10 KPI

| Token | 引用 | 用途 |
|-------|------|------|
| `kpi.bg` | `surface.panel` | KPI 卡片背景 |
| `kpi.border` | `border.subtle` | KPI 卡片边框 |
| `kpi.radius` | `radius.lg` | KPI 卡片圆角 |
| `kpi.value.font-size-sm` | `font.size.kpi-sm` | KPI 值字号（小） |
| `kpi.value.font-size-md` | `font.size.kpi-md` | KPI 值字号 |
| `kpi.value.font-size-lg` | `font.size.kpi-lg` | KPI 值字号（大） |
| `kpi.value.weight` | `font.weight.semibold` | KPI 值字重 |
| `kpi.value.color` | `text.primary` | KPI 值颜色 |
| `kpi.label.font-size` | `font.size.sm` | KPI 标签字号 |
| `kpi.label.color` | `text.secondary` | KPI 标签颜色 |
| `kpi.meta.font-size` | `font.size.xs` | KPI 元信息字号 |
| `kpi.meta.color` | `text.muted` | KPI 元信息颜色 |
| `kpi.change.neutral` | `text.secondary` | 变化值（中性） |
| `kpi.change.market-up` | `market.up.fg` | 变化值（涨） |
| `kpi.change.market-down` | `market.down.fg` | 变化值（跌） |
| `kpi.change.risk-watch` | `risk.watch.fg` | 变化值（风险关注） |
| `kpi.change.risk-breach` | `risk.breach.fg` | 变化值（风险突破） |

---

### 6.11 Grid（数据表格）

#### 基础样式

| Token | 引用 | 用途 |
|-------|------|------|
| `grid.bg` | `surface.panel` | 表格背景 |
| `grid.header-bg` | `surface.raised` | 表头背景 |
| `grid.row-bg` | `transparent` | 行背景 |
| `grid.row-hover-bg` | `state.hover-bg` | 行 Hover |
| `grid.row-selected-bg` | `state.selected-soft-bg` | 行选中 |
| `grid.border` | `border.subtle` | 默认边框 |
| `grid.border-strong` | `border.default` | 强边框 |
| `grid.text` | `text.primary` | 单元格文字 |
| `grid.text-muted` | `text.muted` | 弱化文字 |
| `grid.header-text` | `text.secondary` | 表头文字 |
| `grid.focus-ring` | `state.focus-ring` | 焦点 ring |

#### 密度档位

| Token | Ultra Compact | Compact | Comfortable |
|-------|---------------|---------|-------------|
| `grid.density.*.row-height` | `26px` | `30px` | `36px` |
| `grid.density.*.cell-padding-x` | `8px` | `10px` | `12px` |
| `grid.density.*.font-size` | `12px` | `12px` | `13px` |

#### 列强调层级

| Token | 引用 | 用途 |
|-------|------|------|
| `grid.emphasis.decision-col-text` | `text.primary` | 判断列文字 |
| `grid.emphasis.context-col-text` | `text.secondary` | 上下文列文字 |
| `grid.emphasis.meta-col-text` | `text.muted` | 元信息列文字 |

---

### 6.12 Chart（图表）

#### 基础 UI

| Token | 值 | 用途 |
|-------|-----|------|
| `chart.bg` | `transparent` | 图表背景 |
| `chart.panel-bg` | `surface.panel` | 图表面板背景 |
| `chart.axis` | `neutral.500` → `#4A657B` | 坐标轴线 |
| `chart.axis-label` | `neutral.600` → `#6C8195` | 坐标轴标签 |
| `chart.grid-major` | `rgba(145,163,181,0.14)` | 主网格线 |
| `chart.grid-minor` | `rgba(145,163,181,0.08)` | 次网格线 |
| `chart.crosshair` | `rgba(183,196,209,0.28)` | 十字线 |
| `chart.selection-band` | `rgba(95,143,245,0.10)` | 选区 |
| `chart.tooltip.bg` | `surface.elevated` | Tooltip 背景 |
| `chart.tooltip.border` | `border.default` | Tooltip 边框 |
| `chart.tooltip.text` | `text.primary` | Tooltip 文字 |
| `chart.tooltip.shadow` | `shadow.md` | Tooltip 阴影 |
| `chart.legend.text` | `text.secondary` | 图例文字 |
| `chart.legend.inactive` | `text.muted` | 图例未激活 |

> 网格线一定要弱，tooltip 一定要稳。

#### Market Series

| Token | 值 | 用途 |
|-------|-----|------|
| `chart.series.market.price` | `blue.600` → `#82A9FF` | 价格线 |
| `chart.series.market.benchmark` | `neutral.700` → `#91A3B5` | 基准线 |
| `chart.series.market.volume` | `rgba(95,143,245,0.28)` | 成交量 |
| `chart.series.market.ma-short` | `amber.600` → `#D9A85B` | 短期均线 |
| `chart.series.market.ma-mid` | `cyan.500` → `#46B8D8` | 中期均线 |
| `chart.series.market.ma-long` | `purple.500` → `#B497E7` | 长期均线 |
| `chart.series.market.threshold` | `amber.500` → `#D0A04A` | 阈值线 |

> 不建议用太艳的彩虹色。均线应该是低饱和的专业色，不是鲜黄鲜紫。

#### Strategy / Research Series

| Token | 值 | 用途 |
|-------|-----|------|
| `chart.series.strategy.nav` | `blue.500` → `#5F8FF5` | 策略净值 |
| `chart.series.strategy.drawdown` | `red.600` → `#E06A6A` | 回撤 |
| `chart.series.strategy.exposure` | `cyan.500` → `#46B8D8` | 暴露度 |
| `chart.series.strategy.turnover` | `purple.500` → `#B497E7` | 换手率 |
| `chart.series.strategy.factor` | `amber.600` → `#D9A85B` | 因子 |
| `chart.series.strategy.signal-buy` | `market.up.fg` | 买入信号 |
| `chart.series.strategy.signal-sell` | `market.down.fg` | 卖出信号 |

> buy/sell marker 必须同时用形状区分，不能只靠颜色。

#### Monitoring Series

| Token | 值 | 用途 |
|-------|-----|------|
| `chart.series.monitoring.healthy` | `green.600` → `#58B77A` | 健康 |
| `chart.series.monitoring.degraded` | `amber.600` → `#D9A85B` | 降级 |
| `chart.series.monitoring.failed` | `red.600` → `#E06A6A` | 失败 |
| `chart.series.monitoring.queue` | `blue.500` → `#5F8FF5` | 队列 |
| `chart.series.monitoring.latency` | `orange.600` → `#E28D5D` | 延迟 |

---

### 6.13 Sidebar

| Token | 引用 | 用途 |
|-------|------|------|
| `sidebar.bg` | `surface.chrome` | 侧栏背景 |
| `sidebar.border-right` | `border.subtle` | 右侧边框 |
| `sidebar.item-text` | `text.secondary` | 菜单项文字 |
| `sidebar.item-text-active` | `text.primary` | 激活文字 |
| `sidebar.item-bg-hover` | `state.hover-bg` | Hover 背景 |
| `sidebar.item-bg-active` | `state.selected-soft-bg` | 激活背景 |
| `sidebar.item-indicator` | `blue.500` | 激活指示条 |
| `sidebar.section-label` | `text.muted` | 分组标签 |

---

### 6.14 Topbar

| Token | 引用 | 用途 |
|-------|------|------|
| `topbar.bg` | `surface.chrome` | 顶栏背景 |
| `topbar.border-bottom` | `border.subtle` | 底部边框 |
| `topbar.text` | `text.secondary` | 顶栏文字 |
| `topbar.text-strong` | `text.primary` | 强调文字 |
| `topbar.height` | `48px` | 高度 |

---

### 6.15 Inspector

| Token | 引用 | 用途 |
|-------|------|------|
| `inspector.bg` | `surface.panel` | 检查器背景 |
| `inspector.border-left` | `border.subtle` | 左侧边框 |
| `inspector.width-default` | `360px` | 默认宽度 |
| `inspector.width-wide` | `420px` | 宽模式宽度 |

---

## 7. Typography Scale

### 7.1 Display

| Token | 引用 | 用途 |
|-------|------|------|
| `typography.page-title.font-size` | `font.size.display-md` | 页面标题字号 |
| `typography.page-title.font-weight` | `font.weight.semibold` | 字重 |
| `typography.page-title.line-height` | `font.lineHeight.tight` | 行高 |
| `typography.page-title.tracking` | `font.tracking.tight` | 字间距 |
| `typography.page-title.color` | `text.primary` | 颜色 |
| `typography.section-title.font-size` | `font.size.xl` | 区块标题字号 |
| `typography.section-title.font-weight` | `font.weight.semibold` | 字重 |
| `typography.section-title.line-height` | `font.lineHeight.tight` | 行高 |
| `typography.section-title.color` | `text.primary` | 颜色 |

### 7.2 Body

| Token | 引用 | 用途 |
|-------|------|------|
| `typography.body.md.font-size` | `font.size.md` | 正文（紧凑） |
| `typography.body.md.font-weight` | `font.weight.regular` | 字重 |
| `typography.body.md.line-height` | `font.lineHeight.normal` | 行高 |
| `typography.body.md.color` | `text.primary` | 颜色 |
| `typography.body.sm.font-size` | `font.size.sm` | 正文（小） |
| `typography.body.sm.font-weight` | `font.weight.regular` | 字重 |
| `typography.body.sm.line-height` | `font.lineHeight.normal` | 行高 |
| `typography.body.sm.color` | `text.secondary` | 颜色 |

### 7.3 Mono

| Token | 引用 | 用途 |
|-------|------|------|
| `typography.mono.sm.font-family` | `font.family.mono` | 等宽字号（小） |
| `typography.mono.sm.font-size` | `font.size.sm` | |
| `typography.mono.sm.font-weight` | `font.weight.medium` | |
| `typography.mono.sm.line-height` | `font.lineHeight.normal` | |
| `typography.mono.md.font-family` | `font.family.mono` | 等宽字号 |
| `typography.mono.md.font-size` | `font.size.md` | |
| `typography.mono.md.font-weight` | `font.weight.medium` | |
| `typography.mono.md.line-height` | `font.lineHeight.normal` | |

---

## 8. Flash / Live Update

实时刷新不建议太"交易所化"。

| Token | 值 | 用途 |
|-------|-----|------|
| `flash.up` | `rgba(216,92,92,0.18)` | 涨闪烁 |
| `flash.down` | `rgba(67,163,111,0.18)` | 跌闪烁 |
| `flash.neutral` | `rgba(95,143,245,0.10)` | 中性闪烁 |
| `flash.fade-duration` | `900ms` | 衰减时长 |

> 短暂衰减，不做大面积闪动。

---

## 9. Design Rules

### 9.1 色彩预算

| 类别 | 屏幕占比 |
|------|---------|
| Neutral（Surface + Text + Border） | 88–92% |
| Accent（Interaction + Highlight） | 6–10% |
| Strong Alert（Market + Risk） | 2–4% |

### 9.2 硬性规则

1. **业务域隔离** — market / risk / execution / system / data / model 不能共用同一组 generic `success/warning/error`
2. **双重表达** — 重要含义不能只靠颜色，必须配合 icon / 文字 / 形状 / 位置
3. **图表区分** — 图表必须使用形状/线型/marker 区分，不能只靠颜色
4. **禁止 glow** — 不使用发光作为主要强调手段
5. **禁止纯黑** — 不使用纯黑作为主 surface
6. **单高饱和** — 同一局部模块内不使用超过一个高饱和 accent
7. **数字右对齐** — 主数值列必须右对齐，使用等宽数字
8. **风险持久** — danger/risk 反馈不能仅靠瞬态 toast

### 9.3 配色禁忌

| 禁止 | 原因 |
|------|------|
| 过亮主蓝 | 变成互联网 dashboard 风，不是专业量化风 |
| 纯黑背景 | 对比生硬、层级难控、更累眼 |
| 大面积高饱和红绿 | 像零售交易 app，不像研究交易工作台 |
| 灰度层级过少 | 中性色层级不足撑不住复杂页面 |
| 所有语义共用 success/warning/error | 量化系统必须按业务域拆状态 |

---

## 10. 实现说明

### 10.1 色彩格式

- **设计文档**：HEX（本文档）
- **CSS 实现**：OKLCH（由工具链自动转换）
- **转换策略**：构建时脚本读取本文档，生成 OKLCH 值写入 CSS

### 10.2 CSS 文件映射

| 文档层级 | CSS 文件 | 说明 |
|----------|---------|------|
| Primitive | `src/styles/tokens/primitives.css` | 色彩原语 |
| Semantic Core | `src/styles/tokens/semantic-core.css` | 通用语义 |
| Domain: Market | `src/styles/tokens/semantic-market.css` | 市场语义 |
| Domain: Risk | `src/styles/tokens/semantic-risk.css` | 风险语义 |
| Domain: Execution | `src/styles/tokens/semantic-execution.css` | 执行语义（新增） |
| Domain: System | `src/styles/tokens/semantic-system.css` | 系统语义（新增） |
| Domain: Data | `src/styles/tokens/semantic-data.css` | 数据新鲜度（新增） |
| Domain: Model | `src/styles/tokens/semantic-model.css` | 模型语义（新增） |
| Component: Chart | `src/styles/tokens/charts.css` | 图表 |
| Component: Grid | `src/styles/tokens/grid.css` | 表格 |
| Component: Others | `src/styles/tokens/components.css` | 其他组件（新增） |
| Typography | `src/styles/tokens/typography.css` | 排版 |
| Motion | `src/styles/tokens/motion.css` | 动效 |

### 10.3 v1 → v2 关键变更

| 变更项 | v1 | v2 |
|--------|-----|-----|
| Neutral 灰阶 | 12 级（0-11） | 14 级（0-950） |
| 色相数量 | 6 | 8（新增 cyan、orange） |
| 域分离 | Market / Risk / Status / Signal | Market / Risk / Execution / System / Data / Model |
| Market 模式 | 仅 CN（红涨绿跌） | CN + Global 可切换 |
| Status 通用语义 | `status.success/warning/error/pending` | 拆分为 System / Data / Model 独立域 |
| Surface 层级 | 5 级 | 7 级（+chrome / raised） |
| Text 层级 | 3 级 | 7 级（+tertiary / disabled / inverse / link） |
| 组件 token | 无独立定义 | 15 个组件域完整定义 |
| 字体族 | Inter + JetBrains Mono | Inter + IBM Plex Sans + IBM Plex Mono + JetBrains Mono |

---

## 相关文档

- [视觉设计原则](./2026-03-26-ditto-visual-principles.md) — 12 条顶层视觉决策框架
- [产品设计方案](./2026-03-24-ditto-app-product-design.md) — 产品定位、页面规格、交互约定
- [技术选型清单](./2026-03-24-ditto-app-techstack.md) — 前端工具链、依赖管理
- [实施管线](./2026-03-25-ditto-app-design-implementation-pipeline.md) — Token 实施流程
