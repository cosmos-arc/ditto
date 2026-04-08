# Lapis 配色审查 — 实施计划

> **日期**: 2026-04-07
> **审查文档**: [2026-04-07-lapis-color-review.md](2026-04-07-lapis-color-review.md)
> **分支**: `feat/prototype-three-zone-architecture`

---

## 概述

基于 Lapis 配色审查的 8 项决策，本计划覆盖：
- **Prototype Token 文件**（7 个 CSS + 1 个 JS）
- **Runtime Token 文件**（5 个 CSS）
- **HTML 原型文件**（6 个 HTML 的 sparkline 数据）
- **Spec 文档**（3 个 MD）

共 8 项决策，拆为 **11 个原子任务**。

---

## 技术方案

### 命名约定
- Prototype 文件路径前缀: `docs/designs/specs/prototypes/`
- Runtime 文件路径前缀: `src/styles/tokens/`

### 关键原则
1. **Prototype 先行** — prototype 是设计源，runtime 后同步
2. **批量 hue 替换** — tokens-style.css 39 处 hue 260→253 用 `replace_all`
3. **Sparkline JS 架构** — 新增 `series` 属性支持 token 映射，保留 `stroke` 兼容
4. **每步可验证** — 在浏览器打开 prototype HTML 验证视觉

---

## Phase A: Prototype Foundation（P0）

### Task 1: Lapis chroma 微调 `[S]`
- **文件**: `docs/designs/specs/prototypes/shared/tokens-base.css`
- **变更**:
  - Line 26: `--brand-300: oklch(0.830 0.050 235)` → `oklch(0.830 0.065 235)`
  - Line 27: `--brand-400: oklch(0.760 0.080 235)` → `oklch(0.760 0.090 235)`
  - Line 133: `--brand-300: oklch(0.660 0.050 235)` → `oklch(0.660 0.065 235)` (light)
  - Line 134: `--brand-400: oklch(0.610 0.080 235)` → `oklch(0.610 0.090 235)` (light)
- **验收**: 打开任意 prototype 页面，品牌 accent 浅色标签应更有蓝色辨识度

### Task 2: tokens-style.css Neutral hue 260→253 `[M]`
- **文件**: `docs/designs/specs/prototypes/tokens-style.css`
- **变更**:
  - Line 4 注释: `hue-260` → `hue-253`
  - Dark mode (lines 14-31, 39, 75-82): **21 处** oklchroma hue 260 → 253
  - Light mode (lines 112-115, 120-124, 127-129, 145-147, 150-152): **18 处** oklchroma hue 260 → 253
  - **总计 39 处 hue 替换**
  - 注意: Line 18 `oklch(0.260 0.008 260)` 中 `0.260` 是 lightness，不是 hue，只改最后的 260
- **验收**: 页面整体色调从微紫偏移到微蓝，与 Lapis 235 更协调

### Task 3: tokens-style.css Domain 色调同步 `[S]`
- **文件**: `docs/designs/specs/prototypes/tokens-style.css`
- **变更**（与 Task 2 同文件，建议连续编辑）:
  - Line 40: `--market-strong-fg: oklch(0.720 0.140 172)` → `oklch(0.700 0.140 155)`
  - Line 49: `--system-healthy-fg: oklch(0.680 0.120 175)` → `oklch(0.680 0.120 155)`
  - Line 50: `--system-healthy-bg: oklch(0.680 0.120 175 / 0.10)` → `oklch(0.680 0.120 155 / 0.10)`
  - Line 57: `--execution-filled-fg: oklch(0.680 0.120 175)` → `oklch(0.680 0.120 155)`
- **验收**: 绿色系指标从 teal 偏移到纯绿，与 Lapis 蓝色区分更明显

---

## Phase B: Prototype Domain（P1）

### Task 4: tokens-domain.css 市场色 Down 175→155 `[S]`
- **文件**: `docs/designs/specs/prototypes/shared/tokens-domain.css`
- **变更**:
  - Line 20: `--market-down-fg: oklch(0.680 0.120 175)` → `oklch(0.680 0.120 155)`
  - Line 21: `--market-down-bg: oklch(0.680 0.120 175 / 0.10)` → `oklch(0.680 0.120 155 / 0.10)`
  - Line 22: `--market-down-subtle: oklch(0.680 0.120 175 / 0.08)` → `oklch(0.680 0.120 155 / 0.08)`
  - Light mode (lines 99-100): 同样 175 → 155
  - Intl mode (lines 133-135): 同样 175 → 155
- **验收**: 所有"跌"指标从 teal-绿变为纯绿

### Task 5: tokens-interaction.css 硬编码修复 `[S]`
- **文件**: `docs/designs/specs/prototypes/shared/tokens-interaction.css`
- **变更**:
  - Line 32: `--feedback-banner-warning-bg: oklch(0.7341 0.1177 79.66 / 0.1)` → `oklch(from var(--amber-500) l c h / 0.10)`
  - Line 34: `--feedback-banner-critical-bg: oklch(0.6317 0.1567 22.64 / 0.12)` → `oklch(from var(--red-600) l c h / 0.12)`
- **验收**: Banner 颜色通过 token 引用，与 theme 切换联动

### Task 6: Runtime token 同步 `[M]`
- **文件** (5 个):
  1. `src/styles/tokens/01-primitives.css` — neutral hue 254→253 (lines 3-15, 12 处); brand scale 扩展为 5 级 (50/200/300/400/500/600/700) 对齐 prototype
  2. `src/styles/tokens/02-semantic.css` — surface/text/border hue 254→253 (~12 处); accent 改为引用 brand-500; brass hue 75→74
  3. `src/styles/tokens/04-data-viz.css` — chart-5/6 改亮度变体; bond hue 235→210; data-freshness hue 254→253
  4. `src/styles/tokens/06-interaction.css` — toast-info 改 neutral gray; focus-ring/progress 改引用 brand-500
  5. `src/styles/tokens/07-domain.css` — risk-info 改 neutral; neutral hue 254→253; market-down 确认已为 155
- **验收**: `bun run check` 通过

---

## Phase C: Sparkline 硬编码修复（P0）

### Task 7: Sparkline JS — 支持 series 属性 `[S]`
- **文件**: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- **变更**:
  - Sparkline.render (line 98-100): 新增 `series` 属性映射:
    ```javascript
    var seriesMap = {
      up:      cssVar('--chart-series-up'),
      down:    cssVar('--chart-series-down'),
      neutral: cssVar('--chart-series-neutral'),
      accent:  cssVar('--brand-accent'),
      warning: cssVar('--amber-500'),
    };
    var stroke = seriesMap[cfg.series] || cfg.stroke || cssVar('--chart-series-up');
    ```
  - ConfidenceBar.color (lines 422-424): 改用 token 引用
  - FlowBar.palette (lines 461-465): 改用 token 引用
  - HeatGrid palette (lines 253-257): 已用 cssVar，但 fallback 值需更新对齐
- **验收**: 所有 JS 渲染的颜色通过 token 引用

### Task 8: HTML sparkline 数据 — 硬编码清理 `[L]`
- **文件** (6 个 HTML):
  - `page-home.html` — 3 处 stroke
  - `page-markets-screener.html` — 14+7 处 stroke
  - `page-risk-center.html` — 1+3 处 stroke
  - `page-research.html` — 3+1 处 stroke
  - `page-agent-console.html` — 3 处 stroke
  - `page-strategy-studio.html` — 1 处 stroke
- **变更**: 将 `"stroke": "oklch(...)"` 替换为 `"series": "up"/"down"/"neutral"/"accent"/"warning"`
  - 涨势 sparkline → `"series": "up"` (跟随 CN 惯例，红涨)
  - 跌势 sparkline → `"series": "down"` (绿跌)
  - 中性 → `"series": "neutral"`
  - 品牌相关 → `"series": "accent"`
- **验收**: 所有 sparkline 颜色通过 token 解析，支持 theme 切换

---

## Phase D: Enhancement（P2）

### Task 9: Brass 3 触点 CSS `[M]`
- **文件**:
  - `docs/designs/specs/prototypes/tokens-style.css` — 新增 Brass Rail token
  - `docs/designs/specs/prototypes/shared/tokens-shell.css` — Rail 图标 Brass 微光点样式
  - 全部 16 个 HTML prototype 页面 — 标题下划线改为三段渐变
- **变更**:
  1. tokens-style.css: 新增 `--brand-signature-glow: oklch(from var(--brand-signature-fg) l c h / 0.60)`
  2. tokens-shell.css: `.nav-item--active::after` 新增 Brass 微光点
  3. 各 HTML: `.header-title::after` 渐变改为 `linear-gradient(90deg, var(--brand-accent) 30%, var(--brand-signature-fg) 60%, transparent 100%)`
- **验收**: Rail 活跃图标下方有 Brass 微光点；页面标题有 Lapis→Brass 渐变流动

### Task 10: Spec 文档更新 `[M]`
- **文件** (3 个):
  1. `docs/designs/decisions/2026-03-28-key-design-decisions.md` — 更新决策 #1 (hue 260→253)、#4 (Lapis chroma)、新增市场色/风险色/图表色板决策
  2. `docs/plans/2026-04-03-color-system-v1-design.md` — 更新 token 候选值（neutral hue、brand chroma、market-down hue、chart palette）
  3. `docs/research/2026-04-05-accent-color-exploration.md` — 追加 chroma 微调决策记录
- **验收**: 文档与代码一致

---

## 依赖关系

```
Task 1 (Lapis chroma) ─┐
Task 2 (Neutral hue)   ─┼→ 可并行
Task 3 (Domain sync)   ─┘
         │
         ▼
Task 4 (Market down)  ── 依赖 Task 2/3 完成后验证
Task 5 (Interaction)   ── 独立
Task 6 (Runtime sync)  ── 依赖 Task 1-5 全部完成
         │
         ▼
Task 7 (JS series)    ── 依赖 Task 4 (market-down token 更新)
Task 8 (HTML data)    ── 依赖 Task 7 (JS 支持新属性)
         │
         ▼
Task 9 (Brass)        ── 独立
Task 10 (Spec docs)   ── 依赖 Task 1-8 全部完成后总结
```

---

## 验收总检查

完成所有 Task 后：

1. **视觉验证**: 在浏览器逐一打开 16 个 prototype HTML，检查：
   - 中性灰整体偏蓝调（非紫调）
   - 品牌 accent 浅色级有辨识度
   - 市场涨跌色红绿分明
   - 无硬编码颜色残留
   - Brass 出现在 Rail + 标题

2. **Runtime 验证**: `bun run check` 全部通过

3. **Theme 切换**: Light/Dark 模式切换后颜色正确

4. **市场惯例**: 无西方惯例残留（绿涨红跌）
