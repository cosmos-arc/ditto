# V1 配色方案采纳 — 实施计划

## Context

`docs/plans/2026-04-03-color-system-v1-design.md` 已定稿四通道角色分离方案。所有设计决策已确认：
- Neutral spine 253° + brand primitives 整体迁移到 255-258°
- Light mode 收敛到同一条 253° neutral spine
- Brass 首批消耗面限定为"身份层"4 类触点
- Surface tokens 改用 `var(--neutral-*)` 引用链

本计划将 V1 设计稿落地到 spec token CSS + 16 个原型 HTML。

---

## 实施步骤

### Step 0: Domain bg 提取（纯 DRY 重构，零视觉变化）

**文件**: [tokens-domain.css](docs/designs/specs/prototypes/shared/tokens-domain.css)

在 `:root` 顶部新增 5 个中间变量：

```css
--domain-bg-green:   oklch(0.2280 0.0238 162);
--domain-bg-amber:   oklch(0.2229 0.0212 76.17);
--domain-bg-orange:  oklch(0.2165 0.0265 47.45);
--domain-bg-red:     oklch(0.2242 0.0365 8.74);
--domain-bg-cyan:    oklch(0.2160 0.0237 225.57);
```

将所有 `oklch(0.2280 0.0238 162.00 / 0.2)` 等重复值替换为：
```css
oklch(from var(--domain-bg-green) l c h / 0.20)
```

影响：21 处 bg 值（dark mode）+ 12 处（light mode 需单独处理，light mode bg 值与 dark 不同）。

**注意**：light mode 的 domain bg 使用的是不同的 L/C 值（如 `oklch(0.700 0.120 162 / 0.15)`），不是简单改 alpha。light mode 需单独定义一套 light domain-bg 变量，或保持现有直接写法。建议 V1 只重构 dark mode 的重复，light mode 的 bg 值本身就较统一，后续再优化。

---

### Step 1: 更新 neutral primitive scale

**文件**: [tokens-base.css](docs/designs/specs/prototypes/shared/tokens-base.css) 第 9-23 行

将 15 级 neutral primitive 替换为 V1 候选值（hue 统一到 253，chroma 降低）：

| Token | 当前 (L, C, H) | V1 (L, C, H) |
|-------|---------------|--------------|
| --neutral-0 | 0.1665, 0.0124, 254.17 | 0.166, 0.010, 253 |
| --neutral-25 | 0.1844, 0.0146, 253.21 | 0.184, 0.011, 253 |
| --neutral-50 | 0.1974, 0.0169, 252.56 | 0.198, 0.012, 253 |
| --neutral-75 | 0.2146, 0.0190, 252.07 | 0.215, 0.012, 253 |
| --neutral-100 | 0.2396, 0.0233, 251.45 | 0.240, 0.013, 253 |
| --neutral-150 | 0.2601, 0.0252, 251.20 | 0.261, 0.014, 253 |
| --neutral-200 | 0.3025, 0.0303, 246.97 | 0.303, 0.015, 253 |
| --neutral-300 | 0.3418, 0.0330, 248.82 | 0.342, 0.013, 253 |
| --neutral-400 | 0.4193, 0.0421, 241.39 | 0.420, 0.012, 253 |
| --neutral-500 | 0.4942, 0.0477, 243.51 | 0.495, 0.011, 253 |
| --neutral-600 | 0.5937, 0.0393, 247.20 | 0.594, 0.009, 253 |
| --neutral-700 | 0.7074, 0.0333, 248.30 | 0.707, 0.008, 253 |
| --neutral-800 | 0.8143, 0.0232, 248.11 | 0.814, 0.006, 253 |
| --neutral-900 | 0.9205, 0.0146, 244.73 | 0.920, 0.004, 253 |
| --neutral-950 | 0.9777, 0.0051, 247.88 | 0.978, 0.002, 253 |

**Light mode**: 新增 `[data-theme="light"]` block 在 tokens-base.css 中，定义完整的 15 级 light neutral scale（V1 设计稿 Section 5 已给出全部值）。

---

### Step 2: 更新 brand primitive scale

**文件**: [tokens-base.css](docs/designs/specs/prototypes/shared/tokens-base.css) 第 26-30 行

整体迁移到 hue 255-258 区间：

| Token | 当前 (L, C, H) | V1 (L, C, H) |
|-------|---------------|--------------|
| --brand-300 | 0.8194, 0.0897, 266.29 | 0.820, 0.090, 258 |
| --brand-400 | 0.7420, 0.1322, 264.83 | 0.760, 0.130, 257 |
| --brand-500 | 0.6642, 0.1605, 263.63 | 0.700, 0.165, 255 |
| --brand-600 | 0.5842, 0.1443, 262.74 | 0.620, 0.150, 255 |
| --brand-700 | 0.4767, 0.1321, 262.01 | 0.530, 0.130, 256 |

**Light mode**: 在 `[data-theme="light"]` 中新增 brand-300~700（V1 设计稿已给出）。

**影响分析**：
- `--text-link` = `var(--brand-500)` → 自动跟随 ✓
- `--brand-accent` = `var(--brand-500)` → 自动跟随 ✓
- `--agent-running-fg` = `var(--brand-500)` → 自动跟随 ✓
- layout-base.css 中的 `var(--brand-500)` 引用 → 自动跟随 ✓

---

### Step 3: 更新 semantic surface / text / border

**文件**: [tokens-semantic.css](docs/designs/specs/prototypes/shared/tokens-semantic.css)

#### 3a. Surface tokens — 改用 var() 引用

```css
--surface-app:            var(--neutral-0);       /* was oklch(0.155 0.0124 254.17) */
--surface-panel-base:     var(--neutral-25);       /* was oklch(0.185 0.0146 253.21) */
--surface-panel-elevated: var(--neutral-75);       /* was oklch(0.215 0.0190 252.07) */
--surface-strip:          oklch(0.176 0.004 253);  /* NEW: 不对应任何现有 primitive，独立定义 */
--surface-overlay:        oklch(0.255 0.006 253);
--surface-modal:          oklch(0.290 0.007 253);
```

**注意 surface-strip**：V1 定义 L=0.176，低于 neutral-25 (L=0.184)。不映射到现有 primitive，需独立值。

#### 3b. Text tokens — 更新 lightness

```css
--text-primary:     oklch(0.925 0.004 253);
--text-secondary:   oklch(0.655 0.007 253);
--text-tertiary:    oklch(0.555 0.007 253);
--text-quaternary:  oklch(0.490 0.006 253);
--text-disabled:    oklch(0.415 0.005 253);
--text-inverse:     var(--neutral-0);
--text-data-stale:  oklch(0.490 0.006 253);   /* 跟 quaternary 同值？需确认 */
```

#### 3c. Border tokens

```css
--border-subtle:  oklch(0.255 0.006 253);
--border-default: oklch(0.325 0.008 253);
--border-strong:  oklch(0.425 0.010 253);
```

#### 3d. Brand accent — 改用相对色

```css
--brand-accent:           var(--brand-500);
--brand-accent-hover:     var(--brand-400);
--brand-accent-subtle:    oklch(from var(--brand-500) l c h / 0.10);
```

#### 3e. Scrollbar / Code — 改用 var() 引用

```css
--scrollbar-track:       var(--neutral-0);
--scrollbar-thumb:       var(--neutral-200);
--scrollbar-thumb-hover: var(--neutral-300);
--code-bg:               var(--neutral-0);
--code-text:             var(--neutral-800);
--code-border:           var(--neutral-100);
```

#### 3f. Light mode

更新 `[data-theme="light"]` 中的全部 surface / text / border / brand / code 值。

---

### Step 4: 更新 interaction tokens

**文件**: [tokens-interaction.css](docs/designs/specs/prototypes/shared/tokens-interaction.css)

将硬编码的旧 brand hue 263 值改为引用 `var(--brand-500)` 或使用 `oklch(from var(--brand-500) ...)`：

| Token | 当前 | V1 |
|-------|------|-----|
| --interaction-focus-ring | oklch(0.6642 0.1605 263.63 / 0.50) | oklch(from var(--brand-500) l c h / 0.50) |
| --interaction-focus-border | oklch(0.6642 0.1605 263.63 / 0.70) | oklch(from var(--brand-500) l c h / 0.70) |
| --interaction-selected-bg | oklch(0.6642 0.1605 263.63 / 0.12) | oklch(from var(--brand-500) l c h / 0.12) |
| --interaction-selected-border | oklch(0.6642 0.1605 263.63 / 0.25) | oklch(from var(--brand-500) l c h / 0.25) |

这样 interaction 层自动跟随 brand primitive 变化，未来不再需要手动同步。

---

### Step 5: 新增 Signature Brass tokens

**文件**: [tokens-semantic.css](docs/designs/specs/prototypes/shared/tokens-semantic.css)

在 `:root` 中新增（放在 brand-accent 之后）：

```css
/* Signature Brass - dark */
--brand-signature-fg:     oklch(0.760 0.055 74);
--brand-signature-muted:  oklch(0.660 0.040 74);
--brand-signature-line:   oklch(0.620 0.040 74);
--brand-signature-subtle: oklch(0.760 0.055 74 / 0.08);
```

在 `[data-theme="light"]` 中新增：

```css
--brand-signature-fg:     oklch(0.520 0.060 72);
--brand-signature-muted:  oklch(0.470 0.050 72);
--brand-signature-line:   oklch(0.440 0.045 72);
--brand-signature-subtle: oklch(0.520 0.060 72 / 0.10);
```

---

### Step 6: 修复原型中的硬编码值

#### 6a. page-ai-overview.html — 硬编码 brand 值

第 71-72 行有：
```css
--ai-accent-subtle: oklch(0.6642 0.1605 263.63 / 0.08);
--ai-accent-strong: oklch(0.6642 0.1605 263.63 / 0.20);
```

改为引用：
```css
--ai-accent-subtle: oklch(from var(--brand-accent) l c h / 0.08);
--ai-accent-strong: oklch(from var(--brand-accent) l c h / 0.20);
```

#### 6b. page-instrument-hub.html — JS fallback 值

第 2873-2880 行的 JS mock data 中有硬编码 oklch 值。这些是 chart line colors（MA5/MA10/MA20/MA60 等），应更新到新 brand 值或 token 引用。

#### 6c. page-cross-market.html — 8 处硬编码 oklch

需逐个审计是否需要更新。

#### 6d. prototype-toggles.css — fallback 默认值

8 处 hex fallback 值（`#141414` 等）暂不处理，它们只在独立打开时才生效，加载了 token CSS 后会被覆盖。

---

### Step 7: Brass 首批消耗面落地

在各原型 HTML 的 `<style>` 块中，将以下元素从 `brand-accent` 切换为 `brand-signature-*`：

**1. Shell header hairline**
```css
/* 各页面 .shell-header::after */
/* 当前: border-bottom: 1px solid var(--brand-accent) */
/* 改为: border-bottom: 1px solid var(--brand-signature-line) */
```

**2. Header title 装饰线**
```css
/* .header-title::after */
/* 当前: background: var(--brand-accent) */
/* 改为: background: var(--brand-signature-line) */
```

**3. 非语义型 empty state icon 边界**
```css
/* .state-empty-icon 边框/背景 */
/* 改为: border-color: var(--brand-signature-muted) */
```

**4. Workspace / style label 文案**
```css
/* shell identity / workspace label */
/* 改为: color: var(--brand-signature-fg) */
```

**不改的部分**（确认清单）：
- active tab 下划线 → 保持 `brand-accent`
- .btn-primary / overlay-btn-primary → 保持 `brand-accent`
- 图表主线 / sparkline → 保持 `brand-accent`
- interaction focus / selected → 保持 `brand-accent`
- 所有 domain 状态色 → 不动

---

## 涉及文件清单

| 文件 | 改动类型 | 风险 |
|------|---------|------|
| shared/tokens-base.css | 更新 15 neutral + 5 brand + 新增 light mode neutral + light mode brand | 低 |
| shared/tokens-semantic.css | 更新 surface/text/border + 新增 4 brass + 改用 var() 引用 + 更新 light mode | 中-高（text） |
| shared/tokens-interaction.css | 4 个 token 改为 var() 引用 | 低 |
| shared/tokens-domain.css | 新增 5 domain-bg 中间变量 + 21 处引用替换 | 低（DRY） |
| page-ai-overview.html | 2 处硬编码 brand 值改为 var() 引用 | 低 |
| page-instrument-hub.html | JS fallback 值更新 | 低 |
| page-cross-market.html | 8 处硬编码 oklch 审计 + 更新 | 中 |
| 全部 16 个原型 HTML | brass 首批消耗面（4 类元素） | 中 |

---

## 验证

### 每个 Step 完成后
- 浏览器打开 page-home.html（最简单）+ page-instrument-hub.html（最复杂）
- 截图对比前后变化

### 文本层级专项验证（Step 3 后）
- 在 trading-overview / instrument-hub / ai-copilot 上验证 text-tertiary 是否过亮
- 密集表格中 secondary / tertiary 区分度是否足够
- 如区分度不足，考虑将 secondary 提到 L=0.700+ 以维持 0.145 间距

### Theme toggle 验证
- 每个 step 后切 dark/light 验证无断裂

### Brass 共存验证（Step 7 后）
- 确认 brass hairline 与 blue selected tab 同画面不冲突
- 确认 brass 不进入任何语义状态位置

### 最终
- 16 页面全量截图对比
- 确认无残留旧 hue 值（grep 263.63 / 266.29 / 264.83 等）
