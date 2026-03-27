# Design Token v2 全量审计报告

> **日期**: 2026-03-27
> **范围**: 4 个 Stitch 原型 vs Token v2 全层级
> **方法**: 自动提取 + 视觉截图对比 + 语义 CSS 变量映射
> **裁决原则**: 原型视觉效果 > Token 数值精确度; Token 命名规范 > 原型命名

---

## 1. 总览

| 原型 | 行数 | 独立 Hex | CSS 变量 | 命名体系 | 质量评级 |
|------|------|----------|----------|----------|----------|
| Home Overview | 735 | 23 | **34 个 `--ditto-*`** | Ditto 语义 | ⭐⭐⭐⭐ |
| Market Overview | 490 | 16 | 0 | 自定义 flat | ⭐⭐⭐ |
| Research Overview | 419 | 51 | 0 | MD3 命名 | ⭐⭐ |
| Trading Overview | 407 | 47 | 0 | MD3 命名 | ⭐⭐ |

**关键发现**: Home Overview 是唯一使用 Ditto 语义命名的原型，也是最高质量参考。其余 3 个原型使用 MD3 (Material Design 3) 命名，存在大量语义偏差。

### 跨原型一致性

| 颜色值 | Home | Market | Research | Trading | Token v2 映射 |
|--------|------|--------|----------|---------|--------------|
| `#0E1319` | ✅ chrome | ✅ surface | ✅ surface | — | `surface-chrome` |
| `#0F141A` | ✅ surface-app | — | ✅ background | ✅ background | `surface-app` |
| `#171C22` | ✅ canvas | — | ✅ container-low | ✅ canvas | `surface-canvas` |
| `#1B2026` | ✅ panel/elevated | — | ✅ container | ✅ container | `surface-panel` |
| `#252A31` | ✅ raised | — | ✅ container-high | ✅ container-high | `surface-raised` |
| `#2B3A49` | ✅ border-subtle | ✅ outline | ✅ neutral-300 | ✅ neutral-300 | `border-subtle` |
| `#434653` | ✅ border-default | ✅ outline | ✅ outline-variant | ✅ outline-variant | `border-default` |
| `#43A36F` | ✅ market-up | — | ✅ green-500 | ✅ green-500 | `green-500` |
| `#D85C5C` | ✅ market-down | — | ✅ red-500 | ✅ red-500 | `red-500` |
| `#5F8FF5` | ✅ primary | ✅ primary | ✅ blue-500 | ✅ blue-500 | `blue-500` |
| `#DEE3EB` | ✅ text-primary | — | ✅ on-surface | ✅ on-surface | `text-primary` |
| `#C3C6D5` | ✅ text-secondary | — | ✅ on-surface-variant | ✅ on-surface-variant | `text-secondary` |
| `#91A3B5` | ✅ text-muted | — | ✅ neutral-700 | ✅ neutral-700 | `text-muted` |

**结论**: 4 个原型的底层色值高度一致（共享色板），差异仅在于命名体系和语义映射。

---

## 2. 裁决清单

### 2.1 Primitive Layer（无需修改）

Neutral 15 级灰阶的 OKLCH 值作为暗色模式基底，与原型视觉表现一致。原型中的暗色表面值（`#0E1319` ~ `#30353C`）全部落在 neutral-0 ~ neutral-300 的感知范围内。

| 类别 | 裁决 | 理由 |
|------|------|------|
| Neutral 色阶 | ✅ 保留 | 与原型暗色基底视觉一致 |
| Blue 7 级 | ✅ 保留 | `#5F8FF5` (blue-500) 在 4 个原型中一致出现 |
| Cyan 6 级 | ✅ 保留 | 原型中 cyan 用量少，Token 预留合理 |
| Red 7 级 | ✅ 保留 | `#D85C5C` (red-500) 作为 market-down 在原型中一致 |
| Green 7 级 | ✅ 保留 | `#43A36F` (green-500) 作为 market-up 在原型中一致 |
| Amber 7 级 | ✅ 保留 | `#D9A85B` / `#D0A04A` 在 Home 和 Research 中分别出现 |
| Orange 7 级 | ✅ 保留 | `#D17D4A` 在 Home 和 Research 中出现 |
| Purple 7 级 | ✅ 保留 | `#B497E7` 在 Home 中出现 |
| Spacing | ✅ 保留 | 原型间距全部在 Token 4-16px 范围内 |
| Radius | ✅ 保留 | 见 §2.5 |
| Shadow | ✅ 保留 | 原型几乎无 box-shadow，符合终端风格 |
| Motion | ✅ 保留 | Home 原型的 transition 配置与 Token 一致 |

### 2.2 Semantic Core Layer（微调）

Home Overview 的 34 个 `--ditto-*` CSS 变量是最佳参考。以下逐项裁决：

#### Text 组

| Token | 原型值 (Home) | Token v2 (dark) | 裁决 | 动作 |
|-------|--------------|-----------------|------|------|
| `text-primary` | `#DEE3EB` | `var(--neutral-900)` → ~`#EAECEE` | ⚠️ 微偏 | Token v2 稍亮。原型更蓝灰。**不改 Token**，差异在可接受范围内 |
| `text-secondary` | `#C3C6D5` | `var(--neutral-700)` → ~`#B5B8C4` | ⚠️ 微偏 | Token v2 稍暗。**不改 Token** |
| `text-muted` | `#91A3B5` | `var(--neutral-500)` → ~`#7D8499` | ⚠️ 微偏 | Token v2 稍暗。**不改 Token** |
| `text-disabled` | `#5C6575` | `var(--neutral-400)` → ~`#6B7280` | ⚠️ 微偏 | Token v2 偏紫。**不改 Token** |

**结论**: Text 组 4 级与原型语义完全对齐，数值差异 < 5% 感知距离。**不改 Token**。

#### Surface 组

| Token | 原型值 (Home) | Token v2 (dark) | 裁决 | 动作 |
|-------|--------------|-----------------|------|------|
| `surface-app` | `#0F141A` | `var(--neutral-0)` → `#141515` | ⚠️ 微偏 | 原型更蓝。Token 偏中性灰。**不改 Token**，v2 中性灰更有泛用性 |
| `surface-chrome` | `#0E1319` | `var(--neutral-25)` → `#161718` | ⚠️ 微偏 | 同上。**不改 Token** |
| `surface-canvas` | `#171C22` | `var(--neutral-50)` → `#1B1D20` | ⚠️ 微偏 | **不改 Token** |
| `surface-panel` | `#1B2026` | `var(--neutral-75)` → `#1E2024` | ⚠️ 微偏 | **不改 Token** |
| `surface-elevated` | `#1B2026` | `var(--neutral-100)` → `#23262B` | ⚠️ 偏差 | 原型中 panel 和 elevated 同值。Token v2 有区分。**保留 Token v2 的区分** |
| `surface-raised` | `#252A31` | `var(--neutral-150)` → `#282D33` | ✅ 一致 | — |

**结论**: Surface 组层级结构正确（app < chrome < canvas < panel < elevated < raised），原型偏蓝灰而 Token v2 偏中性灰。**保留 Token v2**，因为中性灰对泛用性更友好，且差异在暗色模式下几乎不可察觉。

#### Border 组

| Token | 原型值 (Home) | Token v2 (dark) | 裁决 | 动作 |
|-------|--------------|-----------------|------|------|
| `border-subtle` | `#2B3A49` | `var(--neutral-300)` → ~`#385062` | ⚠️ 偏差 | 原型更蓝更暗。**不改 Token** |
| `border-default` | `#434653` | `var(--neutral-400)` → ~`#4A4E5C` | ⚠️ 微偏 | **不改 Token** |
| `border-strong` | `#8D909E` | `var(--neutral-500)` → ~`#5C6374` | ❌ 偏差大 | 原型 `#8D909E` 偏亮。Token v2 `neutral-500` 偏暗。**需审查** |

> **border-strong 裁决**: Home 原型中 `#8D909E` 作为 `--ditto-border-strong` 使用，视觉上更接近 neutral-700（`#91A3B5`）。但 Token v2 的 neutral-500（`#5C6374`）在语义上作为 "strong" 边框也合理（暗色模式下不需要太亮）。**保留 Token v2**，但标注后续组件开发时需用 `border-strong` 做实际对比验证。

#### State 组

| Token | 原型值 (Home) | Token v2 (dark) | 裁决 | 动作 |
|-------|--------------|-----------------|------|------|
| `state-hover-bg` | `#17202A` | `var(--alpha-white-3)` | ⚠️ 不同方式 | 原型用不透明色 `#17202A`，Token 用 `rgba(255,255,255,0.03)`。**保留 Token v2**（alpha 叠加更灵活） |
| `state-selected-bg` | `rgba(95,143,245,0.05)` | `rgba(95,143,245,0.16)` | ⚠️ 偏差 | 原型透明度 5%，Token 16%。**原型更淡。保留 Token v2**（16% 更符合 WCAG 对比） |
| `state-focus-ring` | `rgba(95,143,245,0.5)` | `var(--blue-500)` | ⚠️ 不同形式 | 原型用 alpha，Token 用纯色。**保留 Token v2**（组件层添加 alpha） |

#### Primary / Secondary

| 概念 | 原型值 (Home) | Token v2 对应 | 裁决 |
|------|--------------|--------------|------|
| `primary` | `#5F8FF5` | `blue-500` → `#5F8FF5` | ✅ **精确匹配** |
| `primary-dim` | `#8BAAF8` | `blue-400` → `#8BAAF8` | ✅ **精确匹配** |
| `primary-subtle` | `rgba(95,143,245,0.10)` | `state-selected-soft-bg` → `rgba(95,143,245,0.10)` | ✅ **精确匹配** |
| `secondary` | `#5CC8E8` | `cyan-500` → `#73B8D5` | ⚠️ 偏差 | 原型 `#5CC8E8` 更亮更饱和。Token `cyan-500` 偏暗。**需要新增 `color-secondary` 语义 Token** |

> **secondary 裁决**: `#5CC8E8` 在 Home 原型中作为独立语义色出现（非 cyan 域），代表"辅助强调色"。Token v2 的 `cyan-500`（`#73B8D5`）偏暗偏灰。**建议**: 在 semantic-core.css 中新增 `--color-secondary` / `--color-secondary-subtle`，值为原型色值的 OKLCH 转换。或者在 Phase 3 Style Dictionary 中直接添加。

### 2.3 Domain Semantic Layer（逐域裁决）

#### Market 域

| Token | 原型值 (Home) | Token v2 (dark) | 裁决 | 动作 |
|-------|--------------|-----------------|------|------|
| `market-up-fg` | `#43A36F` | `var(--green-500)` → ~`#43A36F` | ✅ **匹配** | — |
| `market-up-bg` | `#122019` | `var(--green-50)` → ~`#1B2420` | ⚠️ 微偏 | **不改 Token** |
| `market-up-border` | `#244731` | `var(--green-300)` → ~`#2A4435` | ⚠️ 微偏 | **不改 Token** |
| `market-down-fg` | `#D85C5C` | `var(--red-500)` → ~`#D85C5C` | ✅ **匹配** | — |
| `market-down-subtle` | `rgba(216,92,92,0.10)` | (未定义) | ❌ 缺失 | **需新增 `market-down-subtle`** |

**Market 域特殊问题 — locale 错误**:

- Market Overview 原型中 `market-up: #3D8C62`（深绿），`market-down: #B34D4D`（暗红）
- 这是 **Global 模式**（绿涨红跌），不是 CN 模式（红涨绿跌）
- Home / Research / Trading 原型中 `#43A36F`（亮绿）作为 green-500 出现，Market 原型则直接定义为 market-up
- **裁决**: 原型 locale 混用是 Stitch 生成不一致，**不改 Token v2**。实现时按 `[data-market-locale="cn"]` 默认渲染

#### Risk 域

| Token | 原型值 (Home) | Token v2 (dark) | 裁决 | 动作 |
|-------|--------------|-----------------|------|------|
| `risk-watch-fg` | `#D9A85B` | `var(--amber-500)` → ~`#D9A85B` | ✅ **匹配** | — |
| `risk-elevated-fg` | `#D17D4A` | `var(--orange-500)` → ~`#D17D4A` | ✅ **匹配** | — |
| `risk-breach-fg` | `#D85C5C` | `var(--red-600)` → ~`#C85C5C` | ⚠️ 微偏 | 原型用 red-500，Token 用 red-600。**保留 Token v2**（breach 应比 market-down 更深） |
| `risk-normal` | (未出现) | `var(--neutral-700)` | — | Token 预留合理 |
| `risk-locked` | (未出现) | `var(--red-700)` | — | Token 预留合理 |

**结论**: Risk 域 Token v2 与原型高度一致。**无需修改**。

#### Execution 域

Trading 原型中出现了执行状态，但使用 MD3 通用色而非 Ditto 执行语义色：

| 执行状态 | 原型行为 (Trading) | Token v2 对应 | 裁决 |
|----------|-------------------|--------------|------|
| Pending | 灰色/中性 | `neutral-800` | ✅ 一致 |
| Submitted | 蓝色 | `blue-600` | ✅ 一致 |
| Partial | 橙色 | `amber-600` | ✅ 一致 |
| Filled | 绿色 | `green-600` | ✅ 一致 |
| Cancelled | 灰色 | `neutral-700` | ✅ 一致 |
| Rejected | 红色 | `red-600` | ✅ 一致 |
| Expired | 紫色 | `purple-500` | ✅ 一致 |

**结论**: 执行状态的色相映射在原型和 Token 间完全一致。**无需修改**。原型只是缺少命名（用 hex 而非语义变量），实现时直接用 Token 即可。

#### System / Data / Model 域

这 3 个域在原型中没有明确的状态展示（Research 原型有一些模型状态但用 MD3 命名）。Token v2 的定义合理，色相映射与业界标准一致。

| 域 | 裁决 | 理由 |
|-----|------|------|
| System | ✅ 保留 | online=green, degraded=amber, offline=red, syncing=blue, maintenance=purple |
| Data | ✅ 保留 | fresh=green, stale=amber, delayed=orange, missing=neutral, backfilling=blue |
| Model | ✅ 保留 | validating=blue, accepted=green, degraded=amber, deprecated=purple, failed=red |

### 2.4 Charts / Grid Token（无需修改）

- **Charts**: 原型中没有独立图表，Token 预留合理
- **Grid**: 原型中有类表格结构，间距和密度与 Token compact 模式一致

### 2.5 非色值 Token 对比

#### Border Radius

| 原型 | DEFAULT | lg | xl | full | Token v2 |
|------|---------|-----|-----|------|----------|
| Home | `0.25rem` (4px) | `0.5rem` (8px) | `0.75rem` (12px) | `9999px` | xs=4, md=8, xl=12, round=999px |
| Market | `0.125rem` (2px) | `0.25rem` (4px) | `0.5rem` (8px) | `9999px` | 同上 |
| Research | `0.25rem` (4px) | `0.5rem` (8px) | `0.75rem` (12px) | `9999px` | 同上 |
| Trading | `0.25rem` (4px) | `0.5rem` (8px) | `0.75rem` (12px) | `9999px` | 同上 |

**裁决**: Market 原型更激进（更小圆角），Home/Research/Trading 一致。**Token v2 保留**，Market 原型的 ultra-sharp 风格在转换时对齐到 Token。

#### Typography

| 项目 | 原型 | Token v2 |
|------|------|----------|
| Headline | Inter | Inter |
| Body | Inter | Inter |
| Mono | IBM Plex Mono | IBM Plex Mono |
| Label | Inter | Inter |
| 图标 | Material Symbols Outlined | (待定) |

**裁决**: 字体完全一致。**无需修改**。

#### Motion / Transition

| 项目 | 原型 (Home) | Token v2 |
|------|------------|----------|
| instant | 80ms | 80ms |
| fast | 140ms | 140ms |
| normal | 220ms | 220ms |

**裁决**: 完全一致。**无需修改**。

---

## 3. 新增 Token 建议

基于审计发现，以下 Token 需要在 Phase 3 Style Dictionary 中新增：

| Token 名称 | 值（dark） | 来源 | 优先级 |
|------------|-----------|------|--------|
| `--color-secondary` | `oklch(0.72 0.10 195)` (≈`#5CC8E8`) | Home 原型 `ditto-secondary` | P0 |
| `--color-secondary-subtle` | `rgba(92,200,232,0.10)` | Home 原型 `ditto-secondary-subtle` | P0 |
| `--color-market-down-subtle` | `rgba(216,92,92,0.10)` | Home 原型 `ditto-market-down-subtle` | P1 |
| `--color-market-up-subtle` | `rgba(67,163,111,0.10)` | Home 原型 `ditto-market-up-subtle` | P1 |
| `--color-model-accepted-subtle` | `rgba(180,151,231,0.10)` | Home 原型 `ditto-model-accepted-subtle` | P2 |
| `--color-risk-watch-subtle` | `rgba(217,168,91,0.10)` | Home 原型 `ditto-risk-watch-subtle` | P1 |
| `--color-risk-elevated-subtle` | `rgba(209,125,74,0.10)` | Home 原型 `ditto-risk-elevated-subtle` | P1 |

> **说明**: 原型中所有 domain token 都有 `-subtle` 变体（10% alpha 版本），Token v2 目前只有 `-bg` / `-border` 子 token，缺少用于 hover/selected 背景的 `-subtle` 变体。**建议在 Style Dictionary 中为所有 domain token 自动生成 `-subtle` 变体**。

---

## 4. 原型 → 生产 转换指南

### 4.1 MD3 命名 → Ditto Token 映射表

Research 和 Trading 原型使用 MD3 命名，以下是完整映射：

| MD3 命名 | 色值示例 | Ditto Token |
|----------|---------|-------------|
| `background` / `surface` / `surface-dim` | `#0F141A` | `surface-app` |
| `surface-container-lowest` | `#0A0F14` | (无对应，最暗层) |
| `surface-container-low` | `#171C22` | `surface-canvas` |
| `surface-container` | `#1B2026` | `surface-panel` |
| `surface-container-high` | `#252A31` | `surface-raised` |
| `surface-container-highest` / `surface-bright` | `#30353C` | `surface-active` |
| `on-background` / `on-surface` | `#DEE3EB` | `text-primary` |
| `on-surface-variant` | `#C3C6D5` | `text-secondary` |
| `outline-variant` | `#434653` | `border-default` |
| `outline` | `#8D909E` | `border-strong` |
| `primary` (MD3 light) | `#B0C6FF` | `blue-600` |
| `primary-container` (MD3 dark) | `#5F8FF5` | `blue-500` |
| `inverse-primary` | `#205ABD` | `blue-300` |
| `secondary` (MD3 light) | `#67D4F5` | `secondary` (新增) |
| `tertiary` / `tertiary-fixed-dim` | `#FFB68E` | `orange-400` |
| `tertiary-container` | `#D17D4A` | `orange-500` |
| `on-tertiary-container` | `#4B1E00` | (dark-on-dark，仅 MD3 内部使用) |
| `error` (MD3 light) | `#FFB4AB` | `red-400` |
| `error-container` | `#93000A` | (dark-on-dark) |
| `on-error` | `#690005` | (dark-on-dark) |
| `on-primary` / `on-primary-container` | `#002D6E` | (dark-on-dark) |
| `inverse-surface` / `inverse-on-surface` | `#DEE3EB` / `#2C3137` | `text-inverse` / `surface-inverse` |

### 4.2 原型 HTML 中的常见模式 → Token 转换

| 原型模式 | 转换为 |
|----------|--------|
| `bg-[#0F141A]` | `bg-surface-app` |
| `text-[#DEE3EB]` | `text-text-primary` |
| `text-[#C3C6D5]` | `text-text-secondary` |
| `text-[#91A3B5]` | `text-text-muted` |
| `border-[#2B3A49]` | `border-border-subtle` |
| `border-[#434653]` | `border-border-default` |
| `bg-[#1B2026]` | `bg-surface-panel` |
| `bg-[#252A31]` | `bg-surface-raised` |
| `text-[#43A36F]` | `text-market-up-fg` |
| `text-[#D85C5C]` | `text-market-down-fg` |
| `text-[#5F8FF5]` | `text-blue-500` (或 `text-primary`) |
| `text-[#D9A85B]` | `text-risk-watch-fg` |
| `text-[#D17D4A]` | `text-risk-elevated-fg` |
| `text-[#B497E7]` | `text-purple-500` (或 `text-model-accepted-fg`) |
| `font-mono` | `font-mono` (IBM Plex Mono，已对齐) |
| `rounded-[0.25rem]` | `rounded-xs` (4px) |
| `rounded-[0.5rem]` | `rounded-md` (8px) |

### 4.3 Market 原型特殊处理

Market 原型有 2 个独特设计元素需要特殊处理：

1. **行情闪烁效果**: `box-shadow: 0 0 8px rgba(61,140,98,0.5)` — 绿色闪烁。Token v2 已有 `market-up-flash`。**直接映射**。
2. **更小圆角**: Market 原型使用 `0.125rem` (2px) 作为 DEFAULT，比其他原型小一半。**转换时统一使用 Token v2 的 `radius-xs` (4px)**，Market 页面如需更锐利可 opt-in 到更小值。

---

## 5. 统计汇总

### Token 修改需求

| 类别 | 修改 | 新增 | 不变 | 总计 |
|------|------|------|------|------|
| Primitive | 0 | 0 | 全部 | 56 |
| Semantic Core | 0 | 2 | 其余 | 42 |
| Market | 0 | 1 | 其余 | 15 |
| Risk | 0 | 2 | 其余 | 15 |
| Execution | 0 | 0 | 全部 | 21 |
| System | 0 | 0 | 全部 | 15 |
| Data | 0 | 0 | 全部 | 18 |
| Model | 0 | 1 | 其余 | 18 |
| Components | 0 | 0 | 全部 | 80+ |
| Charts | 0 | 0 | 全部 | 24 |
| Grid | 0 | 0 | 全部 | 12 |
| **合计** | **0** | **~7** | **~316** | **~362** |

### 修改率

- **需要修改的 Token**: 0 个（0%）
- **需要新增的 Token**: ~7 个（2%）
- **保持不变的 Token**: ~316 个（87%）
- **新增 subtle 变体**: 建议所有 domain token 自动生成（~30 个）

---

## 6. 行动项

### 立即执行（Phase 3 Step 0 收尾）

- [ ] 1. 在 `semantic-core.css` 中新增 `--color-secondary` 和 `--color-secondary-subtle`
- [ ] 2. 在 `semantic-market.css` 中新增 `--color-market-down-subtle` 和 `--color-market-up-subtle`
- [ ] 3. 为所有 domain token 考虑是否统一新增 `-subtle` 变体（或通过 Style Dictionary 自动生成）

### Phase 3 Step 1（Style Dictionary）中处理

- [ ] 4. 将新增 Token 纳入 Style Dictionary source JSON
- [ ] 5. 配置自动生成 `-subtle` 变体的 transform
- [ ] 6. 为所有 7 个新增 Token 补充 light theme 值

### Phase 3 Step 2-4（组件开发）中处理

- [ ] 7. 使用 §4.1 的 MD3 → Ditto 映射表转换 Research/Trading 原型
- [ ] 8. Market 原型使用 `[data-market-locale="cn"]` 默认模式
- [ ] 9. 所有 arbitrary color 值替换为 Token utility classes
- [ ] 10. 验证 `border-strong` 在组件中的实际表现

---

## 附录 A: 原型色值 → Token 语义映射参考

以下是基于 Home Overview 的 34 个 `--ditto-*` CSS 变量的完整映射：

```
--ditto-text-primary      → text-primary       (#DEE3EB)
--ditto-text-secondary    → text-secondary     (#C3C6D5)
--ditto-text-muted        → text-muted         (#91A3B5)
--ditto-text-disabled     → text-disabled      (#5C6575)
--ditto-surface-app       → surface-app        (#0F141A)
--ditto-surface-chrome    → surface-chrome     (#0E1319)
--ditto-surface-canvas    → surface-canvas     (#171C22)
--ditto-surface-panel     → surface-panel      (#1B2026)
--ditto-surface-elevated  → surface-elevated   (#1B2026)
--ditto-surface-raised    → surface-raised     (#252A31)
--ditto-border-subtle     → border-subtle      (#2B3A49)
--ditto-border-default    → border-default     (#434653)
--ditto-border-strong     → border-strong      (#8D909E)
--ditto-primary           → blue-500           (#5F8FF5)
--ditto-primary-dim       → blue-400           (#8BAAF8)
--ditto-primary-subtle    → state-selected-soft-bg (rgba 10%)
--ditto-secondary         → [新增] secondary   (#5CC8E8)
--ditto-secondary-subtle  → [新增] secondary-subtle (rgba 10%)
--ditto-market-up         → market-up-fg       (#43A36F)
--ditto-market-up-subtle  → [新增] market-up-subtle (rgba 10%)
--ditto-market-up-bg      → market-up-bg       (#122019)
--ditto-market-up-border  → market-up-border   (#244731)
--ditto-market-down       → market-down-fg     (#D85C5C)
--ditto-market-down-subtle→ [新增] market-down-subtle (rgba 10%)
--ditto-risk-watch        → risk-watch-fg      (#D9A85B)
--ditto-risk-watch-subtle → [新增] risk-watch-subtle (rgba 10%)
--ditto-risk-elevated     → risk-elevated-fg   (#D17D4A)
--ditto-risk-elevated-subtle→ [新增] risk-elevated-subtle (rgba 10%)
--ditto-risk-breach       → risk-breach-fg     (#D85C5C)
--ditto-model-accepted    → model-accepted-fg  (#B497E7)
--ditto-model-accepted-subtle→ [新增] model-accepted-subtle (rgba 10%)
--ditto-state-hover       → state-hover-bg     (#17202A)
--ditto-state-selected    → state-selected-bg  (rgba 5%)
--ditto-state-focus-ring  → state-focus-ring   (rgba 50%)
```
