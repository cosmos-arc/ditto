# 像素级差距审计报告

> 日期：2026-04-10 | 对比：原型 HTML (localhost:8765) vs React 实现 (localhost:5173)
> 页面：Home (首页) | viewport: 1536x790

---

## P0 — 架构/结构性差距（还原度 ~40%）

### 1. Shell Grid 布局：三栏 vs 两栏

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| Grid 列 | `56px 1fr 320px` (Rail + Main + Sidebar) | `56px 1fr` (Rail + Main) | **缺少 Sidebar 第三栏** |
| Grid 行 | `68px auto 1fr` (Header + Pulse + Main) | `68px 1fr 1.5rem` (Header + Main + StatusBar) | **缺少 Pulse Strip 行** |
| Grid Areas | `rail header header / rail pulse pulse / rail main sidebar` | 无 grid-areas | **完全不同的区域定义** |

**影响**：实现端没有 Sidebar（320px 上下文面板），Home 页变成单栏布局。Pulse Strip 不在 Grid 中独立占行。

### 2. 缺少 Ambient-top 品牌光带

| 属性 | 原型 | 实现 |
|------|------|------|
| `.ambient-top` | `position: absolute; top: 0; height: 1.5px; background: linear-gradient(90deg, transparent → brand-accent 18% → transparent); z-index: 2` | **不存在** |

**影响**：页面顶部缺少品牌色渐变光带，视觉上缺少"高级感"的标志性元素。

### 3. Noise Layer 差异

| 属性 | 原型 | 实现 |
|------|------|------|
| 高度 | `100vh` (通过 `inset: 0`) | 未知/可能不正确 |
| z-index 层叠 | `shell > * { position: relative; z-index: 1 }` + noise `z-index: 0` | 未确认 |

---

## P1 — Shell 组件差距

### 4. Rail（左侧导航）

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| padding | `8px 0` (py-space-2) | `0px` (**--spacing-2 → 8px，但实际 computed 为 0**) | **padding-top/bottom 丢失** |
| gap | `4px` | `4px` | ✅ |
| Logo | `32x32px, font-size: 14px, font-weight: 600, letter-spacing: -0.02em` | `h-8 w-8 (32x32), text-2xl (20px), font-bold (700)` | **字号过大（20px vs 14px），字重过粗（700 vs 600），缺少 letter-spacing** |
| Item 尺寸 | `36x36px, border-radius: 8px` | `h-9 w-9 (36x36), rounded-md (8px)` | ✅ |
| Active indicator | `left: -8px, width: 3px, height: 20px, brand-accent bg, box-shadow glow` | `left: 0 (offset -8px via -translate-x-2), w-[3px], h-5 (20px)` | ✅ 大致正确 |
| Active bg | `brand-accent-subtle (oklch 0.64 0.12 235 / 0.10)` | `bg-[var(--color-brand-50)] (oklch 95% 0.06 235)` | **颜色差距大：brand-50 太亮（95% L vs 64% L with 10% alpha）** |
| Icon SVG size | `18x18` | `18x18` | ✅ |

### 5. Header

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| padding | `0 16px` | `0 16px` | ✅ |
| gap | `16px` | `16px` | ✅ |
| 背景 | `surface-frosted (oklch 0.155 0.005 253 / 0.8) + backdrop-blur(12px)` | `bg-(--color-surface-frosted) backdrop-blur-(--blur-frosted)` | ✅ |
| 标题字号 | `16px (font-size-16)` | **computed: 13px** | **严重差距：tailwind 的 text-[var(--text-lg)] 未生效，解析为 13px** |
| 标题字重 | `600` | `600` | ✅ |
| 标题 brand 下划线 | `::after { bottom: -4px; width: 40%; height: 2px; bg: linear-gradient(accent → signature → transparent) }` | 有类似实现 | 需确认颜色 |
| 搜索框 padding | `6px 12px` | `px-spacing-2 (8px)` | **差距** |
| 搜索框 border-radius | `var(--radius-6)` | `rounded-md (8px)` | ✅ |
| Avatar | `28px, bg: brand-accent-subtle, color: brand-accent, font-size: 12px, font-weight: 500` | `h-8 w-8 (32px), bg: accent, color: accent-fg, font-xs (10px)` | **尺寸差（32 vs 28），背景色用错（accent vs accent-subtle），字号差** |
| Header 底部渐变线 | `::after { height: 1px; bg: linear-gradient → signature-line 25% → transparent }` | 有实现 `via-[color-mix(...)]` | ✅ |

### 6. Pulse Strip

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| height | `calc(var(--density-strip-height) - 4px) = 28px` | `var(--density-strip-height) = 32px` | **4px 差距** |
| padding | `0 16px` | `0px (px-4 = 16px 在 computed 中)` | ⚠️ computed 显示 `0px` |
| gap | `16px` | `16px` | ✅ |
| font-size | `10px` | `10px` | ✅ |
| color | `text-tertiary (oklch 0.55 0.01 253)` | `text-(--color-foreground-tertiary)` | ✅ |
| pulse-value font | `font-family-numeric, weight: 400, color: text-secondary` | `font-data, text-secondary` | ✅ |
| status-dot | `6px, rounded-full, bg: system-healthy-fg, animation: dot-pulse 3s` | `size-1.5 (6px), rounded-full, animate-pulse` | ⚠️ animate-pulse 是 scale，不是 opacity pulse |
| separator | `1px × 10px, bg: border-subtle` | `h-2.5 (10px) w-px, bg: border-subtle` | ✅ |
| 品牌光晕 | `border-bottom: color-mix(accent 8%, border-subtle) + box-shadow: accent 6%` | 在 globals.css 中通过 `[data-slot="pulse-strip"]` 实现 | ✅ |
| pulse-item hover | `border-radius: radius-4; padding: 2px 4px; margin: -2px -4px; hover bg: hover-subtle` | **无 hover 效果** | **缺少交互反馈** |

---

## P1 — Decision Banner 差距

### 7. Banner Grid

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| Grid | `5fr 4fr 3fr` | `5fr 4fr 3fr` | ✅ |
| padding | `12px 16px` | **computed: 0px** | **严重：padding 丢失** |
| gap | `16px` | `16px` | ✅ |
| border-left | `2px solid color-mix(accent 35%, transparent)` | `1.6px solid color-mix(accent 35%, transparent)` | ⚠️ 略窄 |

### 8. Banner Primary 列（左侧指标）

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| metric-label | `12px, text-tertiary, uppercase, letter-spacing: 0.04em` | **computed: 13px, 无 uppercase** | **字号差 + 缺 uppercase** |
| metric-value | `font-numeric, 24px (font-size-24), semibold, letter-spacing: -0.02em` | 未知/未匹配 | **需确认** |
| metric-value color | `positive → market-up-fg` | 通过 Metric variant="equity" | 需确认 |
| metric-sub | `12px, text-secondary` | 未知 | 需确认 |
| sparkline | `64×20px, polyline + gradient fill` | Metric variant="equity" | 需确认 |

### 9. Banner Judgment 列（中间判断）

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| border-left | `1px solid border-subtle` | `1px solid border-subtle` | ✅ |
| padding-left | `16px` | `16px` | ✅ |
| gap | `12px` | `12px` | ✅ |
| judgment-text | `14px, semibold, text-primary, line-height: 1.6` | **10px (font-size-10!), color: text-tertiary** | **严重：字号差距巨大（10px vs 14px），颜色错误** |
| KPI row | `杠杆率 1.2x / 回撤 -3.8%` | 有 metrics 数组 | ✅ |
| status-label | `10px, text-tertiary` | `10px, text-tertiary` | ✅ |
| status-value | `font-numeric, 12px, medium, text-secondary` | 通过 Metric variant="strip" | 需确认 |

### 10. Banner Actions 列（右侧操作）

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| border-left | `1px solid border-subtle` | `1px solid border-subtle` | ✅ |
| routing-label | `"下一步" label, font-size: 10px, text-tertiary` | **不存在** | **缺少"下一步"标签** |
| CTA primary | `transparent bg, accent color/text, accent border` | `Button variant="default"` (filled accent bg) | **严重：样式完全不同！原型是 outlined，实现是 filled** |
| CTA secondary | `transparent, text-tertiary, border-subtle, opacity 0.7` | `Button variant="outline"` | ⚠️ 需确认 |
| CTA ghost | `无` | `Button variant="ghost"` | — |
| CTA 间距 | `gap: 8px` | `gap: 8px` | ✅ |

---

## P1 — Priority Queue 差距

### 11. Panel 结构

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| panel bg | `surface-panel-base, border: 1px border-subtle, radius-8` | Panel component | 需确认 |
| panel-header padding | `8px 12px` | 需确认 | — |
| panel-title | `12px, medium, text-primary` | PanelHeader title | 需确认 |
| panel-count | `font-numeric, 12px, text-tertiary, bg: surface-strip, padding: 0 6px, radius-4, height: 18px` | `count` prop | 需确认 |

### 12. Queue Item

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| 优先级条 | `w-0.5 (2px?) 色条: P1红 / P2橙` | `w-0.5` | ✅ |
| item padding | 需从 layout-base 确认 | `py-1.5 (6px)` | — |
| title | `font-size-12, medium, text-primary` | `text-xs (10px), font-medium, foreground` | **字号差距（10px vs 12px）** |
| tag | `inline-flex, padding: 1px 8px, radius-4, font-size-10, font-weight-medium` | `px-1.5 (6px), text-[10px], rounded-sm` | **padding 差（6px vs 8px）** |
| reason | `font-size-12, text-secondary, line-height: 1.5` | `text-xs (10px), foreground-tertiary` | **字号差（10px vs 12px）+ 颜色错（tertiary vs secondary）** |
| footer source | `font-size-10, text-tertiary, font-feature-settings: tnum` | `text-xs (10px), foreground-muted` | ⚠️ 字号对了但颜色可能不同（muted vs tertiary） |
| hover 效果 | `hover: bg interaction-hover-subtle, negative margin expansion` | `hover: bg interaction-hover-subtle` | **缺少 negative margin expansion** |

---

## P1 — Sidebar 差距（最严重）

### 13. Sidebar 整体缺失

| 属性 | 原型 | 实现 |
|------|------|------|
| Sidebar | `grid-area: sidebar; width: 320px; border-left: 1px border-subtle; overflow-y: auto` | **完全不存在** |

Sidebar 包含以下在原型中存在但实现中缺失的区块：
- **市场脉搏**：沪深300 + IVIX + 涨跌比 + 北向资金（带 sparkline）
- **全局预警**：4 条预警列表
- **数据健康**：5 个数据源状态
- **研究进展**：3 条研究动态
- **Agent 洞察**：3 条关联分析

**影响**：Home 页 50%+ 的信息密度丢失。

---

## P2 — 二级面板/区域差距

### 14. Main Secondary 区域（研究动态 + Agent 洞察）

| 属性 | 原型 | 实现 |
|------|------|------|
| grid | `1fr 1fr (两列等分)` | **缺失/不确定** |
| 研究动态 | 独立 panel，3 条研究 item | 有实现但需确认布局 |
| Agent 洞察 | 独立 panel，3 条 finding item | 有实现但需确认布局 |

### 15. Workspace Placeholder

| 属性 | 原型 | 实现 |
|------|------|------|
| 存在 | ✅ 虚线框 + 🧩 图标 + "自定义工作区 — 即将推出" | **不确定** |

---

## P2 — Token 层面差距

### 16. Token 命名映射不一致

| 原型 Token | 实现 Token | 问题 |
|------------|-----------|------|
| `--surface-app` | `--color-surface-0` / `--color-surface-app` | ✅ 有别名 |
| `--text-primary` | `--color-foreground` / `--color-foreground-primary` | ✅ 有别名 |
| `--text-secondary` | `--color-foreground-secondary` | ✅ |
| `--text-tertiary` | `--color-foreground-tertiary` | ✅ |
| `--border-subtle` | `--color-border-subtle` | ✅ |
| `--brand-accent` | `--color-accent` / `--color-brand-accent` | ✅ 有别名 |
| `--brand-accent-subtle` | `--color-brand-50` (错误映射！) | **❌ brand-50 是亮色 95% L，不是 subtle 10% alpha** |
| `--space-16` | `var(--space-16) → var(--spacing-4) → 16px` | ✅ |
| `--font-size-16` | `var(--text-lg) → 16px` | ✅ 但使用方式可能不正确 |
| `--radius-8` | `var(--radius-md) → 8px` | ✅ |

### 17. 关键 Token 值差异

| Token | 原型 | 实现 | 差距 |
|-------|------|------|------|
| active rail bg | `oklch(0.64 0.12 235 / 0.10)` | `oklch(95% 0.06 235)` | **巨大差距** |
| avatar bg | `brand-accent-subtle (oklch 0.64 0.12 235 / 0.10)` | `accent (oklch 60% 0.18 235)` | **太亮** |

---

## P3 — 微交互/动画差距

### 18. 缺失的动画

| 动画 | 原型 | 实现 |
|------|------|------|
| status-dot pulse | `dot-pulse 3s ease-in-out infinite (opacity 1→0.6→1)` | `animate-pulse (scale animation)` | **效果不同** |
| value-flash | `opacity 0.85 + translateY 0.5px → 1/0` | globals.css 有定义 | ✅ |
| task-breathe | `opacity 1→0.88→1` | globals.css 有定义 | ✅ |
| reveal-up | `opacity 0 + translateY 4px → 1/0` | ScrollReveal component | ✅ |
| pulse-item hover | `border-radius + negative margin + bg` | **无** | **缺少** |
| queue-item active | `bg: hover-strong` | globals.css 有 | ✅ |
| CTA active | `scale(0.97)` | globals.css 有 | ✅ |

### 19. 缺失的品牌光效

| 光效 | 原型 | 实现 |
|------|------|------|
| ambient-top | 顶部 1.5px 渐变光带 | **缺失** |
| ambient-rail | Rail 右侧 1px 竖向渐变 | **缺失** |
| rail active indicator glow | `box-shadow: 0 0 6px brand-signature-glow` | `shadow-[0_0_6px_var(--color-accent)]` | ⚠️ 用了 accent 而非 signature-glow |

---

## 汇总统计

### 按严重度统计

| 级别 | 数量 | 主要问题 |
|------|------|---------|
| **P0 结构性** | 3 | Shell 三栏→两栏，Sidebar 缺失，Ambient 缺失 |
| **P1 组件级** | 10 | Banner padding 丢失，Banner text 10px vs 14px，CTA outlined vs filled，Avatar 样式错，Queue 字号/颜色错，Header 标题 13px vs 16px |
| **P2 区域级** | 3 | Secondary 布局不确定，Workspace placeholder 缺失，Token 映射错 |
| **P3 微交互** | 4 | 动画效果差异，品牌光效缺失 |

### 估计还原度

| 区域 | 还原度 |
|------|--------|
| Shell Grid | 30%（缺 sidebar 三栏） |
| Rail | 80%（Logo 字号、active bg 有差距） |
| Header | 75%（标题字号、avatar 样式有差距） |
| Pulse Strip | 85%（高度差、hover 缺失） |
| Decision Banner | 50%（padding 丢失、文字 10px vs 14px、CTA 样式错） |
| Priority Queue | 70%（item 字号/颜色有差距） |
| Sidebar | **0%**（完全缺失） |
| 整体 | **~40%** |

### 修复优先级建议

1. **Shell 三栏布局** — 恢复 Sidebar 为 grid 第三栏
2. **Ambient-top + Ambient-rail** — 添加品牌光效层
3. **Decision Banner padding** — 修复 `py-3 px-4` 丢失
4. **Decision Banner text** — judgment-text 14px semibold primary（非 10px tertiary）
5. **CTA 按钮** — 改为 outlined 而非 filled
6. **Header 标题字号** — 确保 `text-lg` (16px) 生效
7. **Avatar** — 尺寸 28px、背景 accent-subtle
8. **Rail active bg** — 使用 `color-mix(accent 10%, transparent)` 而非 `brand-50`
9. **Queue item 字号/颜色** — title 12px, reason 12px text-secondary
10. **Pulse strip 高度** — `calc(var(--density-strip-height) - 4px)`
